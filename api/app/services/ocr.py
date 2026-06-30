import base64
import json
import re
from typing import Any

import httpx

from app.schemas.market import MarketCode
from app.schemas.portfolio import PortfolioPosition
from app.services.symbols import currency_for_market, infer_market, normalize_symbol

SYMBOL_RE = re.compile(r"(?P<symbol>\d{5}\.HK|\d{6}(?:\.(?:SH|SZ|BJ))?|\b[A-Z]{1,5}\b)")
QUANTITY_RE = re.compile(r"(?:持仓数量|持仓|数量|可用)\s*(?P<value>[\d,]+(?:\.\d+)?)")
COST_RE = re.compile(r"(?:成本价|持仓成本|买入均价|成本)\s*(?P<value>[\d,]+(?:\.\d+)?)")
PRICE_RE = re.compile(r"(?:当前价|最新价|现价|市价)\s*(?P<value>[\d,]+(?:\.\d+)?)")
HOLDING_FIELD_RE = re.compile(r"(持仓|可用|成本|市值|盈亏|股份余额|证券代码|股票代码|成本价|现价|数量)")
SECURITY_HINT_RE = re.compile(r"(证券|股票|代码|名称|持仓)")

DOUBAO_SYSTEM_PROMPT = (
    "你是券商持仓截图识别助手。只提取股票持仓行，不要给投资建议。"
    "必须只返回 JSON，不要 Markdown，不要解释。"
)

DOUBAO_USER_PROMPT = (
    "请从截图中的券商持仓表格识别股票持仓，并把表格行转换为 positions JSON。"
    "重点识别：股票代码、股票名称、市场、持仓数量、可用数量、成本价、现价、成本金额、参考市值、浮动盈亏、盈亏比例。"
    "返回格式必须严格为："
    '{"positions":[{"symbol":"600519.SH","name":"贵州茅台","market":"CN",'
    '"quantity":10,"available_quantity":8,"cost_price":1000,"current_price":1200,'
    '"market_value":12000,"pnl":2000,"pnl_pct":0.2,"currency":"CNY"}]}。'
    "market 只能是 CN/HK/US；A股代码请补 .SH/.SZ/.BJ，港股请补 5 位代码 .HK。"
    "数量、成本价、现价必须去掉逗号、人民币符号和单位文本，只输出数字。"
    "没有现价但有市值时用 市值/数量 推导现价；没有成本价但有成本金额时用 成本金额/数量 推导成本价。"
    "无法识别的字段不要解释，保留原字段语义。没有识别到持仓时返回 {\"positions\":[]}。"
)

POSITION_CONTAINER_KEYS = (
    "positions",
    "portfolio_positions",
    "items",
    "data",
    "result",
    "results",
    "records",
    "rows",
    "table",
    "持仓",
    "持仓列表",
    "持仓明细",
    "股票持仓",
    "持仓数据",
    "表格",
    "明细",
    "识别结果",
)
SYMBOL_KEYS = ("symbol", "code", "ticker", "股票代码", "证券代码", "代码", "证券/代码", "证券编号")
NAME_KEYS = ("name", "股票名称", "证券名称", "名称", "证券简称", "股票简称")
MARKET_KEYS = ("market", "市场", "交易市场", "交易所", "市场类型")
QUANTITY_KEYS = ("quantity", "shares", "amount", "持仓数量", "持仓", "数量", "股份余额", "股票余额")
AVAILABLE_QUANTITY_KEYS = ("available_quantity", "available", "sellable_quantity", "可用数量", "可用", "可卖数量", "可用股份")
COST_PRICE_KEYS = ("cost_price", "cost", "avg_cost", "成本价", "成本", "持仓成本", "买入均价", "参考成本价", "成本均价")
COST_VALUE_KEYS = ("cost_value", "cost_amount", "成本金额", "持仓成本金额", "参考成本", "成本市值")
CURRENT_PRICE_KEYS = ("current_price", "price", "last_price", "现价", "当前价", "最新价", "市价", "参考价", "最新市价")
MARKET_VALUE_KEYS = ("market_value", "市值", "参考市值", "最新市值", "持仓市值", "证券市值")
PNL_KEYS = ("pnl", "profit_loss", "floating_pnl", "浮动盈亏", "持仓盈亏", "盈亏", "参考盈亏", "收益")
PNL_PCT_KEYS = ("pnl_pct", "profit_loss_pct", "收益率", "盈亏比例", "盈亏率", "参考盈亏比例", "持仓盈亏比例")
CURRENCY_KEYS = ("currency", "币种")
SOURCE_KEYS = ("source", "来源")
MAPPED_POSITION_KEYS = frozenset(
    SYMBOL_KEYS
    + NAME_KEYS
    + MARKET_KEYS
    + QUANTITY_KEYS
    + AVAILABLE_QUANTITY_KEYS
    + COST_PRICE_KEYS
    + COST_VALUE_KEYS
    + CURRENT_PRICE_KEYS
    + MARKET_VALUE_KEYS
    + PNL_KEYS
    + PNL_PCT_KEYS
    + CURRENCY_KEYS
    + SOURCE_KEYS
)
NAME_IGNORE_TOKENS = {
    "同花顺",
    "同花顺APP",
    "同花顺自选",
    "资产",
    "持仓",
    "持仓股",
    "自选股",
    "汇总持仓",
    "可用",
    "成本",
    "现价",
    "最新",
    "涨幅",
    "市价",
    "市值",
    "参考市值",
    "盈亏",
    "收益",
    "数量",
    "证券",
    "代码",
    "名称",
    "首页",
    "行情",
    "交易",
    "资讯",
    "理财",
    "资金",
    "分析",
}


def parse_position_text_lines(lines: list[str]) -> list[PortfolioPosition]:
    positions: list[PortfolioPosition] = []
    seen: set[str] = set()
    for position in _watchlist_positions_from_lines(lines):
        if position.symbol in seen:
            continue
        seen.add(position.symbol)
        positions.append(position)
    for raw_line in [*lines, *_fragmented_line_candidates(lines)]:
        position = _position_from_text_line(raw_line)
        if position is None or position.symbol in seen:
            continue
        seen.add(position.symbol)
        positions.append(position)
    return positions


def has_watchlist_fallback_positions(positions: list[PortfolioPosition]) -> bool:
    return any(_position_raw_fields(position).get("识别类型") == "自选/行情列表" for position in positions)


def no_position_message(lines: list[str]) -> str:
    text = "\n".join(line.strip() for line in lines if line.strip())
    if text and not SECURITY_HINT_RE.search(text) and not SYMBOL_RE.search(text):
        return "AI识别到的内容不像券商持仓页：未看到证券代码、持仓数量、成本价等字段。请上传券商“持仓/资产持仓”页面截图。"
    if text and not HOLDING_FIELD_RE.search(text):
        return "AI识别到了文字，但缺少持仓数量、成本价等必要字段。请上传包含证券代码、持仓数量、成本价的持仓明细截图。"
    return "AI 已返回识别结果，但未提取到可用持仓行。"


def watchlist_position_message(positions: list[PortfolioPosition]) -> str:
    count = sum(1 for position in positions if _position_raw_fields(position).get("识别类型") == "自选/行情列表")
    if count <= 0:
        return ""
    return f"已从自选/行情列表识别 {count} 只股票；截图缺少持仓数量和成本价，已按数量 0、成本价等于最新价导入，请在表格中补充真实持仓。"


def _position_raw_fields(position: Any) -> dict[str, str]:
    if isinstance(position, PortfolioPosition):
        return position.raw_fields
    if isinstance(position, dict):
        raw_fields = position.get("raw_fields")
        return raw_fields if isinstance(raw_fields, dict) else {}
    return {}


def parse_ai_position_payload(content: str) -> list[PortfolioPosition]:
    data = _loads_json_payload(content)
    if data is not None:
        raw_positions = _extract_position_items(data)
        positions = _positions_from_items(raw_positions)
        if positions:
            return positions

        payload_text = "\n".join(_text_values_from_payload(data))
        positions = _positions_from_markdown_tables(payload_text)
        if positions:
            return positions
        positions = parse_position_text_lines(_content_text_lines(payload_text))
        if positions:
            return positions

    positions = _positions_from_markdown_tables(content)
    if positions:
        return positions
    return parse_position_text_lines(_content_text_lines(content))


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
    for key in POSITION_CONTAINER_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _extract_position_items(value)
            if nested is not None:
                return nested
    return None


def _positions_from_items(raw_positions: list[Any] | None) -> list[PortfolioPosition]:
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


def _position_from_ai_item(item: dict[str, Any]) -> PortfolioPosition | None:
    raw_symbol = str(_first_present(item, SYMBOL_KEYS) or "").strip().upper()
    if not raw_symbol:
        return None
    market_hint = _normalize_market_hint(_first_present(item, MARKET_KEYS))
    if market_hint is None and raw_symbol.isdigit():
        market_hint = "HK" if len(raw_symbol) <= 5 else "CN"
    symbol = normalize_symbol(raw_symbol, market_hint)
    market = infer_market(symbol)
    quantity = _safe_float(_first_present(item, QUANTITY_KEYS))
    available_quantity = _safe_float(_first_present(item, AVAILABLE_QUANTITY_KEYS))
    cost_price = _safe_float(_first_present(item, COST_PRICE_KEYS))
    current_price = _safe_float(_first_present(item, CURRENT_PRICE_KEYS))
    cost_value = _safe_float(_first_present(item, COST_VALUE_KEYS))
    market_value = _safe_float(_first_present(item, MARKET_VALUE_KEYS))
    pnl = _safe_float(_first_present(item, PNL_KEYS))
    pnl_pct = _safe_ratio(_first_present(item, PNL_PCT_KEYS))
    if quantity and quantity > 0:
        if cost_price is None and cost_value is not None:
            cost_price = round(cost_value / quantity, 4)
        if current_price is None and market_value is not None:
            current_price = round(market_value / quantity, 4)
    if quantity is None or cost_price is None:
        return None
    return PortfolioPosition(
        symbol=symbol,
        name=str(_first_present(item, NAME_KEYS) or symbol).strip() or symbol,
        market=market,
        quantity=quantity,
        cost_price=cost_price,
        current_price=current_price if current_price is not None else cost_price,
        currency=str(_first_present(item, CURRENCY_KEYS) or currency_for_market(market)).strip().upper(),
        available_quantity=available_quantity,
        market_value=market_value,
        cost_value=cost_value,
        pnl=pnl,
        pnl_pct=pnl_pct,
        source=str(_first_present(item, SOURCE_KEYS) or "ocr").strip() or "ocr",
        raw_fields=_raw_fields_from_item(item),
    )


def _first_present(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _raw_fields_from_item(item: dict[str, Any]) -> dict[str, str]:
    raw_fields: dict[str, str] = {}
    for key, value in item.items():
        key_text = str(key).strip()
        if not key_text or key_text in MAPPED_POSITION_KEYS or value in (None, ""):
            continue
        raw_fields[key_text] = str(value).strip()
    return raw_fields


def _normalize_market_hint(value: Any) -> MarketCode | None:
    raw = str(value or "").strip().upper()
    if raw in {"CN", "A", "A股", "沪深", "沪深A股", "沪A", "深A", "上海A股", "深圳A股", "上交所", "深交所", "科创板", "创业板", "北交所"}:
        return "CN"
    if raw in {"HK", "H", "港股"}:
        return "HK"
    if raw in {"US", "USA", "美股"}:
        return "US"
    return None


def _match_number(pattern: re.Pattern[str], line: str) -> float | None:
    match = pattern.search(line)
    return _safe_float(match.group("value")) if match else None


def _position_from_text_line(raw_line: str) -> PortfolioPosition | None:
    line = " ".join(raw_line.replace("，", " ").replace(":", " ").replace("：", " ").split())
    symbol_match = SYMBOL_RE.search(line)
    if not symbol_match:
        return None
    raw_symbol = symbol_match.group("symbol").upper()
    market: MarketCode | None = None
    if raw_symbol.endswith(".HK") or (raw_symbol.isdigit() and len(raw_symbol) == 5):
        market = "HK"
    elif raw_symbol.isdigit() and len(raw_symbol) == 6:
        market = "CN"
    symbol = normalize_symbol(raw_symbol, market)
    inferred_market = infer_market(symbol)
    name = _security_name_from_prefix(line[: symbol_match.start()]) or symbol
    quantity = _match_number(QUANTITY_RE, line)
    cost_price = _match_number(COST_RE, line)
    current_price = _match_number(PRICE_RE, line)
    available_quantity: float | None = None
    market_value: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    if quantity is None or cost_price is None or current_price is None:
        numbers = _numbers_after_symbol(line[symbol_match.end() :])
        if "可用" in line and len(numbers) >= 4:
            if quantity is None:
                quantity = numbers[0]
            available_quantity = numbers[1]
            if cost_price is None:
                cost_price = numbers[2]
            if current_price is None:
                current_price = numbers[3]
            if len(numbers) >= 5:
                market_value = numbers[4]
            if len(numbers) >= 6:
                pnl = numbers[5]
            if len(numbers) >= 7:
                pnl_pct = _ratio_from_number(numbers[6])
        elif quantity is None and numbers:
            quantity = numbers[0]
            if cost_price is None and len(numbers) >= 2:
                cost_price = numbers[1]
            if current_price is None and len(numbers) >= 3:
                current_price = numbers[2]
            if len(numbers) >= 4:
                market_value = numbers[3]
            if len(numbers) >= 5:
                pnl = numbers[4]
            if len(numbers) >= 6:
                pnl_pct = _ratio_from_number(numbers[5])
    if quantity is None or cost_price is None:
        return None
    return PortfolioPosition(
        symbol=symbol,
        name=name,
        market=inferred_market,
        quantity=quantity,
        cost_price=cost_price,
        current_price=current_price if current_price is not None else cost_price,
        currency=currency_for_market(inferred_market),
        available_quantity=available_quantity,
        market_value=market_value,
        pnl=pnl,
        pnl_pct=pnl_pct,
        source="ocr",
    )


def _watchlist_positions_from_lines(lines: list[str]) -> list[PortfolioPosition]:
    cleaned = [line.strip() for line in lines if line.strip()]
    positions: list[PortfolioPosition] = []
    seen: set[str] = set()
    for index, raw_name in enumerate(cleaned):
        name = _watchlist_name(raw_name)
        if not name:
            continue
        price = _single_price(cleaned[index + 1]) if index + 1 < len(cleaned) else None
        if price is None:
            continue
        change_pct_text = cleaned[index + 2].strip() if index + 2 < len(cleaned) and _looks_like_percent(cleaned[index + 2]) else ""
        symbol_text = _first_symbol_text(cleaned[index + 2 : index + 7])
        if symbol_text is None:
            continue
        symbol = normalize_symbol(symbol_text, "CN" if symbol_text.isdigit() and len(symbol_text) == 6 else None)
        if symbol in seen:
            continue
        market = infer_market(symbol)
        raw_fields = {"识别类型": "自选/行情列表"}
        if change_pct_text:
            raw_fields["涨幅"] = change_pct_text
        positions.append(
            PortfolioPosition(
                symbol=symbol,
                name=name,
                market=market,
                quantity=0,
                cost_price=price,
                current_price=price,
                currency=currency_for_market(market),
                source="ocr-watchlist",
                raw_fields=raw_fields,
            )
        )
        seen.add(symbol)
    return positions


def _watchlist_name(line: str) -> str:
    normalized = line.replace("，", " ").replace(",", " ").strip()
    if not normalized or SYMBOL_RE.search(normalized) or _looks_like_percent(normalized) or _single_price(normalized) is not None:
        return ""
    token = _security_name_from_prefix(normalized)
    if not token or token.upper() in NAME_IGNORE_TOKENS:
        return ""
    if len(token) > 12:
        return ""
    return token


def _single_price(line: str) -> float | None:
    stripped = line.strip().replace(",", "")
    if not re.fullmatch(r"\d{1,5}(?:\.\d{1,4})?", stripped):
        return None
    value = _safe_float(stripped)
    if value is None or value <= 0:
        return None
    return value


def _looks_like_percent(line: str) -> bool:
    return re.fullmatch(r"[+-]?\d{1,4}(?:\.\d+)?%[▼▲]?", line.strip()) is not None


def _first_symbol_text(lines: list[str]) -> str | None:
    for line in lines:
        match = SYMBOL_RE.search(line.strip().upper())
        if match:
            return match.group("symbol").upper()
    return None


def _fragmented_line_candidates(lines: list[str]) -> list[str]:
    cleaned = [line.strip() for line in lines if line.strip()]
    candidates: list[str] = []
    max_window = min(len(cleaned), 24)
    for size in range(max_window, 1, -1):
        for start in range(0, len(cleaned) - size + 1):
            end = start + size
            chunk = " ".join(cleaned[start:end])
            if SYMBOL_RE.search(chunk) and HOLDING_FIELD_RE.search(chunk):
                candidates.append(chunk)
    return candidates


def _security_name_from_prefix(prefix: str) -> str:
    normalized = prefix.replace("，", " ").replace(",", " ").strip()
    tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", normalized)
    for token in reversed(tokens):
        upper_token = token.upper()
        if upper_token in NAME_IGNORE_TOKENS or upper_token.endswith("APP"):
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            continue
        return token
    return ""


def _numbers_after_symbol(text: str) -> list[float]:
    values: list[float] = []
    for item in re.findall(r"[\d,]+(?:\.\d+)?", text):
        value = _safe_float(item)
        if value is not None:
            values.append(value)
    return values


def _safe_float(value: Any) -> float | None:
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("￥", "").replace("¥", "").strip()
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        if not match:
            value = cleaned
        else:
            multiplier = 1
            if "亿" in cleaned:
                multiplier = 100000000
            elif "万" in cleaned:
                multiplier = 10000
            value = float(match.group(0)) * multiplier
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_ratio(value: Any) -> float | None:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    if isinstance(value, str) and "%" in value:
        return round(parsed / 100, 6)
    return _ratio_from_number(parsed)


def _ratio_from_number(value: float) -> float:
    if abs(value) > 1:
        return round(value / 100, 6)
    return round(value, 6)


def _positions_from_markdown_tables(content: str) -> list[PortfolioPosition]:
    positions: list[PortfolioPosition] = []
    headers: list[str] | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or "|" not in line[1:]:
            headers = None
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or _is_markdown_separator_row(cells):
            continue
        if headers is None:
            if any(cell in SYMBOL_KEYS for cell in cells):
                headers = cells
            continue
        row = {headers[index]: cells[index] for index in range(min(len(headers), len(cells)))}
        position = _position_from_ai_item(row)
        if position is not None:
            positions.append(position)
    return positions


def _is_markdown_separator_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", cell.replace(" ", "")) for cell in cells)


def _content_text_lines(content: str) -> list[str]:
    return [line.strip() for line in content.splitlines() if line.strip()]


def _text_values_from_payload(data: Any) -> list[str]:
    if isinstance(data, str):
        return [data]
    if isinstance(data, list):
        values: list[str] = []
        for item in data:
            values.extend(_text_values_from_payload(item))
        return values
    if isinstance(data, dict):
        values = []
        for item in data.values():
            values.extend(_text_values_from_payload(item))
        return values
    return []


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
