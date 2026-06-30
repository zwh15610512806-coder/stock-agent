import os
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.schemas.sources import FreeDataSource, SourceCacheStatus, SourceKeyStatus, SourcesStatusResponse
from app.services.runtime_paths import runtime_cache_path

SOURCES_DISCLAIMER = (
    "Free public market data may be delayed, incomplete, unavailable, or rate limited. "
    "Configuration status only checks local settings and does not validate credentials with external services."
)


def build_sources_status(settings: Any | None = None, cache_path: str | Path | None = None) -> SourcesStatusResponse:
    current_settings = settings or get_settings()
    cache_dir = _cache_directory(cache_path or _default_market_cache_path())
    return SourcesStatusResponse(
        key_status=[
            _key_status("DeepSeek", _has_value(getattr(current_settings, "deepseek_api_key", "")), "deepseek_api_key"),
            _key_status(
                "Volcengine OCR",
                _has_value(getattr(current_settings, "volcengine_api_key", "")),
                "volcengine_api_key",
            ),
            _key_status(
                "Tencent OCR",
                _has_value(getattr(current_settings, "tencentcloud_secret_id", ""))
                and _has_value(getattr(current_settings, "tencentcloud_secret_key", "")),
                "tencentcloud_secret_id/tencentcloud_secret_key",
            ),
        ],
        cache=_cache_status(cache_dir),
        free_data_sources=_free_data_sources(),
        disclaimer=SOURCES_DISCLAIMER,
    )


def _key_status(name: str, configured: bool, setting_names: str) -> SourceKeyStatus:
    detail = "configured" if configured else f"missing {setting_names}"
    return SourceKeyStatus(name=name, configured=configured, detail=detail)


def _cache_status(cache_dir: Path) -> SourceCacheStatus:
    exists = cache_dir.exists()
    writable = cache_dir.is_dir() and os.access(cache_dir, os.W_OK)
    if writable:
        detail = "cache directory is writable"
    elif exists:
        detail = "cache directory exists but is not writable"
    else:
        detail = "cache directory does not exist"
    return SourceCacheStatus(path=str(cache_dir), exists=exists, writable=writable, detail=detail)


def _cache_directory(path: str | Path) -> Path:
    resolved = Path(path)
    if resolved.suffix:
        return resolved.parent
    return resolved


def _default_market_cache_path() -> Path:
    return runtime_cache_path(Path(__file__).resolve().parents[3], "market_cache.sqlite3")


def _free_data_sources() -> list[FreeDataSource]:
    return [
        FreeDataSource(
            name="Tencent delayed quotes",
            category="quotes",
            source="tencent-free-delayed",
            detail="Public delayed quote endpoint used for CN/HK symbols when available.",
        ),
        FreeDataSource(
            name="Yahoo Finance delayed fallback",
            category="quotes/candles",
            source="Yahoo Finance/free delayed fallback",
            detail="Public delayed quote and chart fallback for US and selected index symbols.",
        ),
        FreeDataSource(
            name="AkShare Eastmoney",
            category="quotes/candles/dashboard",
            source="akshare-eastmoney-free",
            detail="Free AkShare/Eastmoney datasets used for A-share quotes, candles, and dashboard data.",
        ),
        FreeDataSource(
            name="Legulegu market activity",
            category="dashboard",
            source="legulegu-market-activity",
            detail="Free market activity data used for A-share breadth where available.",
        ),
        FreeDataSource(
            name="CLS telegraph",
            category="news",
            source="cls-telegraph",
            detail="Free market news feed used by the dashboard when available.",
        ),
    ]


def _has_value(value: object) -> bool:
    return bool(str(value or "").strip())
