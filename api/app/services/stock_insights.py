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
        if not self.api_key:
            return StockInsightResponse(
                status="unavailable",
                symbol=symbol,
                market=request.position.market,
                as_of=as_of,
                summary="联网 AI 分析未配置：请设置 OPENAI_API_KEY 或 NEWS_SEARCH_API_KEY 后再使用单股联网分析。",
                model=self.model,
                data_warnings=["missing OPENAI_API_KEY/NEWS_SEARCH_API_KEY"],
                disclaimer=DISCLAIMER,
            )

        quote, quote_warning = await self._safe_quote(symbol)
        candles, candles_warning = await self._safe_candles(symbol, request.horizon_days)
        data_warnings = [warning for warning in (quote_warning, candles_warning) if warning]

        try:
            payload = await self._fetch_web_context(request, symbol, quote, candles)
        except Exception as exc:
            return StockInsightResponse(
                status="failed" if not data_warnings else "partial",
                symbol=symbol,
                market=request.position.market,
                as_of=as_of,
                quote=quote,
                candles=candles,
                summary=f"联网 AI 分析失败：{_error_detail(exc)}",
                risks=["联网搜索或模型服务暂不可用时，不要依据缺失报告做交易判断。"],
                data_warnings=[*data_warnings, f"web search failed: {_error_detail(exc)}"],
                model=self.model,
                disclaimer=DISCLAIMER,
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


def _error_detail(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__
