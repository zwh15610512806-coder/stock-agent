from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from app.config import get_settings
from app.schemas.sources import SourcesStatusResponse
from app.services.sources import build_sources_status

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("/status", response_model=SourcesStatusResponse)
async def status(request: Request) -> SourcesStatusResponse:
    settings = getattr(request.app.state, "sources_settings", None) or getattr(request.app.state, "settings", None) or get_settings()
    return build_sources_status(settings=settings, cache_path=_cache_path_from_state(request.app.state))


def _cache_path_from_state(state: Any) -> str | Path | None:
    explicit_path = getattr(state, "sources_cache_path", None)
    if explicit_path is not None:
        return explicit_path
    market_service = getattr(state, "market_service", None)
    snapshot_cache = getattr(market_service, "snapshot_cache", None)
    return getattr(snapshot_cache, "db_path", None)
