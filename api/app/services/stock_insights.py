import json
from datetime import UTC, datetime
from typing import Any, Mapping

import httpx

from app.schemas.ai import StockInsightCitation, StockInsightRequest, StockInsightResponse
from app.schemas.market import CandleSnapshot, QuoteSnapshot
from app.services.market import _json_object_from_text, _responses_output_text
from app.services.portfolio import DISCLAIMER
from app.services.symbols import normalize_symbol


class StockInsightService:
    def __init__(
        self,
        api_key: str,
        api_base: str,
        model: str,
        timeout_seconds: float,
        market_service: Any,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.market_service = market_service
        self.transport = transport

    async def generate(self, request: StockInsightRequest) -> StockInsightResponse:
        symbol = normalize_symbol(request.position.symbol, request.position.market)
        as_of = datetime.now(UTC)
        quote, quote_warning = await self._safe_quote(symbol)
        candles, candles_warning = await self._safe_candles(symbol, request.horizon_days)
        data_warnings = [warning for warning in (quote_warning, candles_warning) if warning]

        if not self.api_key:
            return _local_market_response(
                request=request,
                symbol=symbol,
                as_of=as_of,
                quote=quote,
                candles=candles,
                data_warnings=[*data_warnings, "missing OPENAI_API_KEY/NEWS_SEARCH_API_KEY"],
            )

        try:
            payload = await self._fetch_web_context(request, symbol, quote, candles)
        except Exception as exc:
            return _local_market_response(
                request=request,
                symbol=symbol,
                as_of=as_of,
                quote=quote,
                candles=candles,
                data_warnings=[*data_warnings, f"web search failed: {_error_detail(exc)}"],
            )

        citations = _citations_from_payload(payload)
        if not citations:
            data_warnings.append("web search returned no usable citation URLs")
        return StockInsightResponse(
            status="completed" if not data_warnings else "partial",
            symbol=symbol,
            market=request.position.market,
            as_of=as_of,
            quote=quote,
            candles=candles,
            summary=_clean_text(payload.get("summary")) or "联网资料已返回，但模型没有给出摘要。",
            trend=_string_list(payload.get("trend")),
            financials=_string_list(payload.get("financials")),
            events=_string_list(payload.get("events")),
            risks=_string_list(payload.get("risks")),
            citations=citations,
            data_warnings=data_warnings,
            model=self.model,
            disclaimer=DISCLAIMER,
        )

    async def _safe_quote(self, symbol: str) -> tuple[QuoteSnapshot | None, str]:
        try:
            if hasattr(self.market_service, "_fetch_quote_without_sample"):
                quote = await self.market_service._fetch_quote_without_sample(symbol)
            else:
                quotes = await self.market_service.quotes([symbol])
                if not quotes:
                    raise RuntimeError("quote service returned no rows")
                quote = quotes[0]
            if str(quote.source).strip().lower() == "sample fallback":
                raise RuntimeError("sample fallback quote rejected")
            return quote, ""
        except Exception as exc:
            return None, f"quote unavailable: {_error_detail(exc)}"

    async def _safe_candles(self, symbol: str, horizon_days: int) -> tuple[list[CandleSnapshot], str]:
        try:
            if hasattr(self.market_service, "_fetch_primary_candles"):
                candles = await self.market_service._fetch_primary_candles(symbol, "daily", horizon_days)
            else:
                candles = await self.market_service.candles(symbol, "daily", horizon_days)
            real = [item for item in candles if str(item.source).strip().lower() != "sample fallback"]
            if not real:
                raise RuntimeError("no real candles returned")
            return real[-horizon_days:], ""
        except Exception as exc:
            return [], f"candles unavailable: {_error_detail(exc)}"

    async def _fetch_web_context(
        self,
        request: StockInsightRequest,
        symbol: str,
        quote: QuoteSnapshot | None,
        candles: list[CandleSnapshot],
    ) -> Mapping[str, object]:
        payload = {
            "model": self.model,
            "tools": [{"type": "web_search"}],
            "tool_choice": "required",
            "input": _build_stock_insight_prompt(request, symbol, quote, candles),
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport, trust_env=False) as client:
            response = await client.post(
                f"{self.api_base}/responses",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
        text = _responses_output_text(response.json())
        if not text:
            raise RuntimeError("model web search returned no text")
        return _json_object_from_text(text)


def _local_market_response(
    *,
    request: StockInsightRequest,
    symbol: str,
    as_of: datetime,
    quote: QuoteSnapshot | None,
    candles: list[CandleSnapshot],
    data_warnings: list[str],
) -> StockInsightResponse:
    position = request.position
    name = _clean_text(position.name) or symbol
    price = quote.price if quote else position.current_price
    change_text = _raw_change_text(position) or (_format_percent(quote.change_pct) if quote else "")
    warnings = _dedupe_warnings(data_warnings)
    risks = ["未启用联网搜索时，本地分析不包含新闻、公告、研报或财报核验。"]
    trend: list[str] = []

    if _is_missing_position_fields(position):
        warnings.append("position quantity/cost missing; unable to calculate holding PnL")
        risks.append("截图缺少真实持仓数量或成本价，无法判断仓位盈亏和组合风险贡献。")

    if change_text:
        trend.append(f"截图涨幅 {change_text}" if _raw_change_text(position) else f"行情涨跌幅 {change_text}")

    if len(candles) >= 2:
        first = candles[0].close
        last = candles[-1].close
        if first:
            pct = (last - first) / first * 100
            trend.append(f"{len(candles)}个交易日收盘价由{first:.2f}变为{last:.2f}，区间涨跌幅{pct:.2f}%。")
    elif not candles:
        trend.append("暂无真实K线，趋势判断仅基于截图或当前行情字段。")

    if quote:
        trend.append(f"行情源：{quote.source}，时间：{quote.as_of.isoformat()}。")
    else:
        risks.append("实时行情源暂不可用，最新价可能仅来自截图或用户录入。")

    price_text = f"{price:.2f}" if isinstance(price, (int, float)) else "--"
    summary_parts = [f"本地行情分析：{name}（{symbol}）当前可用最新价 {price_text}"]
    if change_text:
        summary_parts.append(f"涨跌幅 {change_text}")
    summary = "，".join(summary_parts) + "。未启用或未完成联网搜索，暂不生成新闻、公告、财报引用。"

    return StockInsightResponse(
        status="partial",
        symbol=symbol,
        market=position.market,
        as_of=as_of,
        quote=quote,
        candles=candles,
        summary=summary,
        trend=trend,
        financials=[],
        events=[],
        risks=risks,
        citations=[],
        data_warnings=_dedupe_warnings(warnings),
        model="local-market",
        disclaimer=DISCLAIMER,
    )


def _build_stock_insight_prompt(
    request: StockInsightRequest,
    symbol: str,
    quote: QuoteSnapshot | None,
    candles: list[CandleSnapshot],
) -> str:
    context = {
        "symbol": symbol,
        "name": request.position.name,
        "market": request.position.market,
        "horizon_days": request.horizon_days,
        "position": request.position.model_dump(mode="json"),
        "quote": quote.model_dump(mode="json") if quote else None,
        "candles": [item.model_dump(mode="json") for item in candles[-request.horizon_days :]],
        "now_beijing": (datetime.now(UTC)).isoformat(),
    }
    return (
        "你是谨慎的证券研究助手。请联网搜索这只股票最近30天走势、最新财报、公告和重要事件。"
        "严格只输出 JSON，不要 Markdown，不要解释文本，不要给确定性买卖指令。"
        "每条财报/公告/事件必须尽量附可验证 URL。"
        "输出结构：{\"summary\":\"一句话摘要\",\"trend\":[\"走势要点\"],"
        "\"financials\":[\"财报要点\"],\"events\":[\"公告或事件\"],\"risks\":[\"风险\"],"
        "\"citations\":[{\"title\":\"来源标题\",\"url\":\"https://...\",\"source\":\"媒体或公告源\","
        "\"published_at\":\"ISO 8601 或 null\"}]}。"
        "\n上下文："
        + json.dumps(context, ensure_ascii=False)
    )


def _citations_from_payload(payload: Mapping[str, object]) -> list[StockInsightCitation]:
    rows = payload.get("citations")
    if not isinstance(rows, list):
        return []
    citations: list[StockInsightCitation] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        title = _clean_text(row.get("title"))
        url = _clean_text(row.get("url"))
        if not title or not url:
            continue
        citations.append(
            StockInsightCitation(
                title=title[:120],
                url=url,
                source=_clean_text(row.get("source")),
                published_at=row.get("published_at") or None,
            )
        )
    return citations


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_text(item) for item in value if _clean_text(item)]


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _raw_change_text(position: Any) -> str:
    raw_fields = getattr(position, "raw_fields", None) or {}
    if not isinstance(raw_fields, Mapping):
        return ""
    for key in ("涨幅", "涨跌幅", "change_pct"):
        value = _clean_text(raw_fields.get(key))
        if value:
            return value
    return ""


def _format_percent(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{numeric:+.2f}%"


def _is_missing_position_fields(position: Any) -> bool:
    raw_fields = getattr(position, "raw_fields", None) or {}
    raw_type = _clean_text(raw_fields.get("识别类型")) if isinstance(raw_fields, Mapping) else ""
    source = _clean_text(getattr(position, "source", ""))
    return source == "ocr-watchlist" or raw_type == "自选/行情列表" or float(getattr(position, "quantity", 0) or 0) <= 0


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    deduped: list[str] = []
    for warning in warnings:
        if warning and warning not in deduped:
            deduped.append(warning)
    return deduped


def _error_detail(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__
