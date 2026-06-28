from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import ai, compat, etfs, macro, market, ocr, portfolio, sources, stocks, symbols
from app.services.ai_reports import DeepSeekReportService
from app.services.market import MarketDataService
from app.services.ocr import DoubaoVisionOcrService, TencentOcrService
from app.services.stock_insights import StockInsightService


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.market_service = MarketDataService(
        cache_ttl_seconds=settings.market_cache_ttl_seconds,
        news_search_api_key=settings.news_search_api_key or settings.openai_api_key,
        news_search_api_base=settings.news_search_api_base,
        news_search_model=settings.news_search_model,
        news_search_timeout_seconds=settings.news_search_timeout_seconds,
        dashboard_source_timeout_seconds=settings.dashboard_source_timeout_seconds,
        dashboard_slow_source_timeout_seconds=settings.dashboard_slow_source_timeout_seconds,
        dashboard_optional_source_timeout_seconds=settings.dashboard_optional_source_timeout_seconds,
    )
    app.state.ai_report_service = DeepSeekReportService(
        api_key=settings.deepseek_api_key,
        api_base=settings.deepseek_api_base,
        model=settings.deepseek_model,
    )
    app.state.stock_insight_service = StockInsightService(
        api_key=settings.news_search_api_key or settings.openai_api_key,
        api_base=settings.news_search_api_base,
        model=settings.news_search_model,
        timeout_seconds=settings.news_search_timeout_seconds,
        market_service=app.state.market_service,
    )
    tencent_ocr_service = TencentOcrService(
        secret_id=settings.tencentcloud_secret_id,
        secret_key=settings.tencentcloud_secret_key,
        region=settings.tencentcloud_region,
        endpoint=settings.tencentcloud_ocr_endpoint,
    )
    app.state.ocr_service = DoubaoVisionOcrService(
        api_key=settings.volcengine_api_key,
        api_base=settings.volcengine_api_base,
        model=settings.volcengine_ocr_model,
        fallback=tencent_ocr_service,
    )

    app.include_router(market.router)
    app.include_router(compat.router)
    app.include_router(macro.router)
    app.include_router(symbols.router)
    app.include_router(stocks.router)
    app.include_router(etfs.router)
    app.include_router(portfolio.router)
    app.include_router(ocr.router)
    app.include_router(ai.router)
    app.include_router(sources.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
