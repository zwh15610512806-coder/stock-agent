from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import ai, etfs, macro, market, ocr, portfolio, sources, stocks, symbols
from app.services.ai_reports import DeepSeekReportService
from app.services.market import MarketDataService
from app.services.ocr import DoubaoVisionOcrService, TencentOcrService


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
    app.state.market_service = MarketDataService(cache_ttl_seconds=settings.market_cache_ttl_seconds)
    app.state.ai_report_service = DeepSeekReportService(
        api_key=settings.deepseek_api_key,
        api_base=settings.deepseek_api_base,
        model=settings.deepseek_model,
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
