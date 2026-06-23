import base64
import json
import re
from typing import Any

import httpx

from app.schemas.market import MarketCode
from app.schemas.portfolio import PortfolioPosition
from app.services.symbols import currency_for_market, infer_market, normalize_symbol

SYMBOL_RE = re.compile(r"(?P<symbol>\d{5}\.HK|\d{6}|[A-Z]{1,5})", re.IGNORECASE)
QUANTITY_RE = re.compile(r"(?:持仓数量|持仓|数量|可用)\s*(?P<value>[\d,]+(?:\.\d+)?)")
COST_RE = re.compile(r"(?:成本价|持仓成本|买入均价|成本)\s*(?P<value>[\d,]+(?:\.\d+)?)")
PRICE_RE = re.compile(r"(?:当前价|最新价|现价|市价)\s*(?P<value>[\d,]+(?:\.\d+)?)")

DOUBAO_SYSTEM_PROMPT = (
    "你是券商持仓截图识别助手。只提取股票持仓行，不要给投资建议。"
    "必须只返回 JSON，不要 Markdown，不要解释。"
)

DOUBAO_USER_PROMPT = (
    "请从截图中识别股票持仓。重点识别：股票代码、股票名称、市场、持仓数量、成本价、现价。"
    "返回格式必须严格为："
    '{"positions":[{"symbol":"600519.SH","name":"贵州茅台","market":"CN",'
    '"quantity":10,"cost_price":1000,"current_price":1200,"currency":"CNY"}]}。'
    "market 只能是 CN/HK/US；A股代码请补 .SH/.SZ/.BJ，港股请补 5 位代码 .HK。"
    "没有现价时用成本价。没有识别到持仓时返回 {\"positions\":[]}。"
)


def parse_position_text_lines(lines: list[str]) -> list[PortfolioPosition]:
    positions: list[PortfolioPosition] = []
    for raw_line in lines:
        line = " ".join(raw_line.replace("，", " ").replace(":", " ").replace("：", " ").split())
        symbol_match = SYMBOL_RE.search(line)
        if not symbol_match:
            continue
        raw_symbol = symbol_match.group("symbol").upper()
        market: MarketCode | None = None
        if raw_symbol.endswith(".HK") or (raw_symbol.isdigit() and len(raw_symbol) == 5):
            market = "HK"
        elif raw_symbol.isdigit() and len(raw_symbol) == 6:
            market = "CN"
        symbol = normalize_symbol(raw_symbol, market)
        inferred_market = infer_market(symbol)
        name = line[: symbol_match.start()].strip(" ,，") or symbol
        quantity = _match_number(QUANTITY_RE, line)
        cost_price = _match_number(COST_RE, line)
        current_price = _match_number(PRICE_RE, line)
        if quantity is None or cost_price is None or current_price is None:
            numbers = _numbers_after_symbol(line[symbol_match.end() :])
            if quantity is None and numbers:
                quantity = numbers[0]
            if cost_price is None and len(numbers) >= 2:
                cost_price = numbers[1]
            if current_price is None and len(numbers) >= 3:
                current_price = numbers[2]
        if quantity is None or cost_price is None:
            continue
        positions.append(
            PortfolioPosition(
                symbol=symbol,
                name=name,
                market=inferred_market,
                quantity=quantity,
                cost_price=cost_price,
                current_price=current_price if current_price is not None else cost_price,
                currency=currency_for_market(inferred_market),
            )
        )
    return positions


def parse_ai_position_payload(content: str) -> list[PortfolioPosition]:
    data = _loads_json_payload(content)
    if data is None:
        return parse_position_text_lines([content])
    raw_positions = _extract_position_items(data)
    if not isinstance(raw_positions, list):
        return []
    positions: list[PortfolioPosition] = []
    for item in raw_positions:
        if not isinstance(item, dict):
            continue
        position = _position_from_ai_item(item)
        if position is not None:
            positions.append(position)
    return positions


def _loads_json_payload(content: str) -> Any | None:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        object_start = text.find("{")
        object_end = text.rfind("}")
        if object_start >= 0 and object_end > object_start:
            try:
                return json.loads(text[object_start : object_end + 1])
            except json.JSONDecodeError:
                return None
        array_start = text.find("[")
        array_end = text.rfind("]")
        if array_start >= 0 and array_end > array_start:
            try:
                return json.loads(text[array_start : array_end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _extract_position_items(data: Any) -> list[Any] | None:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return None
    for key in ("positions", "portfolio_positions", "items", "data", "持仓", "持仓列表", "持仓明细", "股票持仓"):
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _extract_position_items(value)
            if nested is not None:
                return nested
    return None


def _position_from_ai_item(item: dict[str, Any]) -> PortfolioPosition | None:
    raw_symbol = str(
        _first_present(item, ("symbol", "code", "ticker", "股票代码", "证券代码", "代码")) or ""
    ).strip().upper()
    if not raw_symbol:
        return None
    market_hint = _normalize_market_hint(_first_present(item, ("market", "市场", "交易市场")))
    if market_hint is None and raw_symbol.isdigit():
        market_hint = "HK" if len(raw_symbol) <= 5 else "CN"
    symbol = normalize_symbol(raw_symbol, market_hint)
    market = infer_market(symbol)
    quantity = _safe_float(_first_present(item, ("quantity", "shares", "amount", "持仓数量", "持仓", "数量", "可用")))
    cost_price = _safe_float(_first_present(item, ("cost_price", "cost", "avg_cost", "成本价", "成本", "持仓成本", "买入均价")))
    current_price = _safe_float(
        _first_present(item, ("current_price", "price", "last_price", "现价", "当前价", "最新价", "市价"))
    )
    if quantity is None or cost_price is None:
        return None
    return PortfolioPosition(
        symbol=symbol,
        name=str(_first_present(item, ("name", "股票名称", "证券名称", "名称")) or symbol).strip() or symbol,
        market=market,
        quantity=quantity,
        cost_price=cost_price,
        current_price=current_price if current_price is not None else cost_price,
        currency=str(_first_present(item, ("currency", "币种")) or currency_for_market(market)).strip().upper(),
    )


def _first_present(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_market_hint(value: Any) -> MarketCode | None:
    raw = str(value or "").strip().upper()
    if raw in {"CN", "A", "A股", "沪深", "沪深A股"}:
        return "CN"
    if raw in {"HK", "H", "港股"}:
        return "HK"
    if raw in {"US", "USA", "美股"}:
        return "US"
    return None


def _match_number(pattern: re.Pattern[str], line: str) -> float | None:
    match = pattern.search(line)
    return _safe_float(match.group("value")) if match else None


def _numbers_after_symbol(text: str) -> list[float]:
    values: list[float] = []
    for item in re.findall(r"[\d,]+(?:\.\d+)?", text):
        value = _safe_float(item)
        if value is not None:
            values.append(value)
    return values


def _safe_float(value: Any) -> float | None:
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        value = match.group(0) if match else cleaned
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class DoubaoVisionOcrService:
    def __init__(
        self,
        api_key: str,
        api_base: str,
        model: str,
        fallback: "TencentOcrService | None" = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.fallback = fallback
        self.transport = transport

    async def recognize_positions(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
    ) -> tuple[str, list[PortfolioPosition], list[str]]:
        if self.api_key:
            try:
                content = await self._recognize_with_doubao(image_bytes, mime_type)
                positions = parse_ai_position_payload(content)
                return "completed", positions, [content]
            except Exception:
                if self.fallback is None:
                    return "failed", [], []
        if self.fallback is None:
            return "unavailable", [], []
        status, lines = await self.fallback.recognize_lines(image_bytes)
        positions = parse_position_text_lines(lines)
        if not self.api_key and status != "completed":
            return "unavailable", [], lines
        return status, positions, lines

    async def _recognize_with_doubao(self, image_bytes: bytes, mime_type: str) -> str:
        image_url = f"data:{_normalize_image_mime_type(mime_type)};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": DOUBAO_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": DOUBAO_USER_PROMPT},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            "temperature": 0,
        }
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            response = await client.post(
                f"{self.api_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
        data = response.json()
        return str(data["choices"][0]["message"]["content"])


def _normalize_image_mime_type(value: str) -> str:
    normalized = value.strip().lower().split(";", 1)[0]
    if normalized in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
        return "image/jpeg" if normalized == "image/jpg" else normalized
    return "image/png"


class TencentOcrService:
    def __init__(
        self,
        secret_id: str,
        secret_key: str,
        region: str,
        endpoint: str,
    ) -> None:
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.region = region
        self.endpoint = endpoint

    async def recognize_lines(self, image_bytes: bytes) -> tuple[str, list[str]]:
        if not self.secret_id or not self.secret_key:
            return "unavailable", []
        try:
            return "completed", self._recognize_lines_sync(image_bytes)
        except Exception:
            return "failed", []

    def _recognize_lines_sync(self, image_bytes: bytes) -> list[str]:
        from tencentcloud.common import credential
        from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        from tencentcloud.ocr.v20181119 import ocr_client, models

        try:
            cred = credential.Credential(self.secret_id, self.secret_key)
            http_profile = HttpProfile()
            http_profile.endpoint = self.endpoint
            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile
            client = ocr_client.OcrClient(cred, self.region, client_profile)
            request = models.GeneralAccurateOCRRequest()
            request.from_json_string(json.dumps({"ImageBase64": base64.b64encode(image_bytes).decode("ascii")}))
            response = client.GeneralAccurateOCR(request)
        except TencentCloudSDKException as exc:
            raise RuntimeError(str(exc)) from exc
        return [item.DetectedText for item in getattr(response, "TextDetections", []) if getattr(item, "DetectedText", "")]
