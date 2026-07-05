import json
from datetime import UTC, datetime

import httpx
import pytest

from app.schemas.ai import AiReportRequest, StockInsightRequest
from app.schemas.market import CandleSnapshot, QuoteSnapshot
from app.schemas.portfolio import PortfolioPosition
from app.services.ai_reports import DeepSeekReportService
from app.services.stock_insights import StockInsightService


@pytest.mark.asyncio
async def test_deepseek_report_returns_unavailable_without_key() -> None:
    service = DeepSeekReportService(api_key="")

    report = await service.generate(
        AiReportRequest(
            symbol="600519.SH",
            market="CN",
            horizon="中短线波段",
            risk_profile="稳健",
            quote=None,
            candles=[],
            portfolio_positions=[],
        )
    )

    assert report.status == "unavailable"
    assert "DEEPSEEK_API_KEY" in report.summary
    assert report.metadata["analysis_skill"] == "standard"
    assert report.disclaimer == "仅供研究参考，不构成任何证券买卖建议。"


def test_deepseek_prompt_uses_serenity_skill_when_enabled() -> None:
    service = DeepSeekReportService(api_key="test-key")

    prompt = service._build_prompt(
        AiReportRequest(
            symbol="600519.SH",
            market="CN",
            analysis_skill="serenity",
            horizon="中短线波段",
            risk_profile="稳健",
            quote=None,
            candles=[],
            portfolio_positions=[],
        )
    )

    assert "serenity-skill" in prompt
    assert "横向网页 PPT" in prompt
    assert '"analysis_skill": "serenity"' in prompt


@pytest.mark.asyncio
async def test_deepseek_report_metadata_marks_serenity_skill_without_key() -> None:
    service = DeepSeekReportService(api_key="")

    report = await service.generate(
        AiReportRequest(
            symbol="600519.SH",
            market="CN",
            analysis_skill="serenity",
            horizon="中短线波段",
            risk_profile="稳健",
            quote=None,
            candles=[],
            portfolio_positions=[],
        )
    )

    assert report.status == "unavailable"
    assert report.metadata["analysis_skill"] == "serenity"
    assert report.metadata["skill_label"] == "serenity-skill"


class FakeInsightMarketService:
    async def _fetch_quote_without_sample(self, symbol: str) -> QuoteSnapshot:
        assert symbol == "600519.SH"
        return QuoteSnapshot(
            symbol="600519.SH",
            name="贵州茅台",
            market="CN",
            price=1200,
            change=12,
            change_pct=1,
            volume=100000,
            turnover=120000000,
            currency="CNY",
            source="test-quote",
            as_of=datetime(2026, 6, 28, tzinfo=UTC),
            delay_label="test delayed",
        )

    async def _fetch_primary_candles(self, symbol: str, period: str, limit: int) -> list[CandleSnapshot]:
        assert symbol == "600519.SH"
        assert period == "daily"
        assert limit == 30
        return [
            CandleSnapshot(
                symbol=symbol,
                date=f"2026-06-{day:02d}",
                open=1000 + day,
                high=1010 + day,
                low=990 + day,
                close=1005 + day,
                volume=10000 + day,
                source="test-candles",
                delay_label="test delayed",
            )
            for day in range(1, 31)
        ]


def _stock_position() -> PortfolioPosition:
    return PortfolioPosition(
        symbol="600519.SH",
        name="贵州茅台",
        market="CN",
        quantity=10,
        cost_price=1000,
        current_price=1200,
        currency="CNY",
    )


@pytest.mark.asyncio
async def test_stock_insight_uses_web_search_and_market_context() -> None:
    captured_payload: dict | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "output_text": json.dumps(
                    {
                        "summary": "近30日震荡上行，最新公告显示营收稳健。",
                        "trend": ["30日收盘价从1006升至1035", "成交量保持温和"],
                        "financials": ["最新财报收入同比增长"],
                        "events": ["披露年度股东大会公告"],
                        "risks": ["白酒需求波动"],
                        "citations": [
                            {
                                "title": "贵州茅台公告",
                                "url": "https://example.com/report",
                                "source": "交易所公告",
                                "published_at": "2026-06-20T00:00:00Z",
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            },
        )

    service = StockInsightService(
        api_key="test-key",
        api_base="https://api.openai.test/v1",
        model="gpt-4.1-mini",
        timeout_seconds=3,
        market_service=FakeInsightMarketService(),
        transport=httpx.MockTransport(handler),
    )

    result = await service.generate(StockInsightRequest(position=_stock_position(), horizon_days=30))

    assert captured_payload is not None
    assert captured_payload["tools"] == [{"type": "web_search"}]
    assert "600519.SH" in captured_payload["input"]
    assert result.status == "completed"
    assert result.quote is not None
    assert len(result.candles) == 30
    assert result.summary == "近30日震荡上行，最新公告显示营收稳健。"
    assert result.citations[0].url == "https://example.com/report"
    assert result.data_warnings == []


@pytest.mark.asyncio
async def test_stock_insight_returns_local_market_analysis_without_web_search_key() -> None:
    service = StockInsightService(
        api_key="",
        api_base="https://api.openai.test/v1",
        model="gpt-4.1-mini",
        timeout_seconds=3,
        market_service=FakeInsightMarketService(),
    )

    result = await service.generate(StockInsightRequest(position=_stock_position(), horizon_days=30))

    assert result.status == "partial"
    assert "本地行情分析" in result.summary
    assert result.quote is not None
    assert len(result.candles) == 30
    assert "missing OPENAI_API_KEY/NEWS_SEARCH_API_KEY" in result.data_warnings
    assert result.citations == []


@pytest.mark.asyncio
async def test_stock_insight_local_analysis_warns_for_ocr_watchlist_missing_position_fields() -> None:
    service = StockInsightService(
        api_key="",
        api_base="https://api.openai.test/v1",
        model="gpt-4.1-mini",
        timeout_seconds=3,
        market_service=FakeInsightMarketService(),
    )
    position = PortfolioPosition(
        symbol="600519.SH",
        name="贵州茅台",
        market="CN",
        quantity=0,
        cost_price=1200,
        current_price=1200,
        currency="CNY",
        source="ocr-watchlist",
        raw_fields={"涨幅": "+1.00%", "识别类型": "自选/行情列表"},
    )

    result = await service.generate(StockInsightRequest(position=position, horizon_days=30))

    assert result.status == "partial"
    assert any("position quantity/cost missing" in warning for warning in result.data_warnings)
    assert any("截图涨幅 +1.00%" in item for item in result.trend)


@pytest.mark.asyncio
async def test_stock_insight_marks_partial_when_market_data_fails_but_search_succeeds() -> None:
    class BrokenMarketService:
        async def _fetch_quote_without_sample(self, symbol: str) -> QuoteSnapshot:
            raise RuntimeError("quote down")

        async def _fetch_primary_candles(self, symbol: str, period: str, limit: int) -> list[CandleSnapshot]:
            raise RuntimeError("candles down")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "output_text": json.dumps(
                    {
                        "summary": "联网资料已返回，但行情源暂不可用。",
                        "trend": [],
                        "financials": ["财报摘要"],
                        "events": [],
                        "risks": ["行情源缺失"],
                        "citations": [{"title": "财报", "url": "https://example.com/finance", "source": "公告"}],
                    },
                    ensure_ascii=False,
                )
            },
        )

    service = StockInsightService(
        api_key="test-key",
        api_base="https://api.openai.test/v1",
        model="gpt-4.1-mini",
        timeout_seconds=3,
        market_service=BrokenMarketService(),
        transport=httpx.MockTransport(handler),
    )

    result = await service.generate(StockInsightRequest(position=_stock_position(), horizon_days=30))

    assert result.status == "partial"
    assert result.quote is None
    assert result.candles == []
    assert any("quote down" in warning for warning in result.data_warnings)


@pytest.mark.asyncio
async def test_stock_insight_falls_back_to_local_market_analysis_when_web_search_fails() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "search down"})

    service = StockInsightService(
        api_key="test-key",
        api_base="https://api.openai.test/v1",
        model="gpt-4.1-mini",
        timeout_seconds=3,
        market_service=FakeInsightMarketService(),
        transport=httpx.MockTransport(handler),
    )

    result = await service.generate(StockInsightRequest(position=_stock_position(), horizon_days=30))

    assert result.status == "partial"
    assert "本地行情分析" in result.summary
    assert result.quote is not None
    assert len(result.candles) == 30
    assert any("web search failed" in warning for warning in result.data_warnings)
    assert result.citations == []
