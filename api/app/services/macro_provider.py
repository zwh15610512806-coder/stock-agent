from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.config import get_settings
from app.schemas.macro import MacroSourceStatus, MacroTimeseriesResponse, MacroTimeseriesSeries
from app.schemas.macro_xray import (
    MacroXrayPeriod,
    MacroXrayPoint,
    MacroXrayResponse,
    MacroXraySample,
    MacroXrayTarget,
    MacroXrayTargetsResponse,
    MacroXrayUniverse,
)
from app.services.macro import MacroDataService
from app.services.macro_xray import MacroXrayService


class MacroProvider(Protocol):
    async def timeseries(
        self,
        *,
        series_ids: list[str],
        start: str | None,
        end: str | None,
        max_points: int,
    ) -> Any:
        ...

    async def xray(
        self,
        *,
        universe_type: str,
        universe_code: str,
        scope: str,
        quarters: int,
        lookback: int,
        period: str = "latest",
    ) -> Any:
        ...

    async def targets(
        self,
        *,
        universe_type: str,
        lookback: int,
        target_source: str,
    ) -> Any:
        ...


class DangInvestMacroProvider:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.danginvest_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.danginvest_timeout_seconds
        self.transport = transport

    async def timeseries(
        self,
        *,
        series_ids: list[str],
        start: str | None,
        end: str | None,
        max_points: int,
    ) -> MacroTimeseriesResponse:
        query: dict[str, str] = {
            "series_ids": ",".join(series_ids),
            "max_points": str(max_points),
        }
        if start:
            query["start"] = start
        if end:
            query["end"] = end
        payload = await self._get_json("/api/market/macro-timeseries", query)
        return self._timeseries_response(payload, requested_ids=series_ids)

    async def xray(
        self,
        *,
        universe_type: str,
        universe_code: str,
        scope: str,
        quarters: int,
        lookback: int,
        period: str = "latest",
    ) -> MacroXrayResponse:
        query: dict[str, str] = {
            "universe_type": universe_type,
            "universe_code": universe_code,
            "scope": scope,
            "quarters": str(quarters),
            "lookback": str(lookback),
        }
        if period and period != "latest":
            query["period"] = period
        payload = await self._get_json("/api/market/macro-xray", query)
        return self._xray_response(payload, fallback_universe_type=universe_type, fallback_universe_code=universe_code, fallback_scope=scope)

    async def targets(
        self,
        *,
        universe_type: str,
        lookback: int,
        target_source: str,
    ) -> MacroXrayTargetsResponse:
        query = {
            "universe_type": universe_type,
            "lookback": str(lookback),
            "target_source": target_source,
        }
        payload = await self._get_json("/api/market/macro-xray/targets", query)
        return self._targets_response(payload, universe_type=universe_type)

    async def _get_json(self, path: str, query: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=self.transport,
            trust_env=False,
        ) as client:
            response = await client.get(path, params=query)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("DangInvest returned non-object JSON")
            return payload

    def _timeseries_response(self, payload: dict[str, Any], *, requested_ids: list[str]) -> MacroTimeseriesResponse:
        raw_series = payload.get("series") if isinstance(payload.get("series"), list) else []
        series = [self._timeseries_series(item) for item in raw_series if isinstance(item, dict)]
        returned = {item.series_id for item in series}
        for series_id in requested_ids:
            if series_id not in returned:
                series.append(
                    MacroTimeseriesSeries(
                        series_id=series_id,
                        name=series_id,
                        category="unknown",
                        frequency="D",
                        unit="num",
                        source="danginvest",
                        status="unavailable",
                        methodology="DangInvest returned no points for this series.",
                        points=[],
                    )
                )
        return MacroTimeseriesResponse(
            ts=_parse_ts(payload.get("ts")),
            start=str(payload.get("start") or ""),
            end=str(payload.get("end") or ""),
            series=series,
            source_status=[_source_status("danginvest_macro_timeseries", "live", "macro-timeseries")],
            disclaimer="优先使用 DangInvest 公开可访问接口；接口不可用时由 hybrid provider 回退公开源。",
        )

    def _timeseries_series(self, item: dict[str, Any]) -> MacroTimeseriesSeries:
        status = "live" if item.get("points") else "unavailable"
        return MacroTimeseriesSeries(
            series_id=str(item.get("series_id") or item.get("id") or ""),
            name=str(item.get("name") or item.get("series_id") or ""),
            category=str(item.get("category") or "unknown"),
            frequency=str(item.get("frequency") or "D"),
            unit=str(item.get("unit") or ""),
            source="danginvest",
            status=status,
            methodology=str(item.get("description") or "DangInvest macro-timeseries."),
            is_derived=bool(item.get("is_derived", False)),
            description=str(item.get("description") or ""),
            points=item.get("points") or [],
        )

    def _xray_response(
        self,
        payload: dict[str, Any],
        *,
        fallback_universe_type: str,
        fallback_universe_code: str,
        fallback_scope: str,
    ) -> MacroXrayResponse:
        raw_period = payload.get("period") if isinstance(payload.get("period"), dict) else {}
        raw_sample = payload.get("sample") if isinstance(payload.get("sample"), dict) else {}
        raw_universe = payload.get("universe") if isinstance(payload.get("universe"), dict) else {}
        points = [_xray_point(point) for point in payload.get("points", []) if isinstance(point, dict)]
        latest = _xray_point(payload["latest"]) if isinstance(payload.get("latest"), dict) else (points[-1] if points else None)
        universe_type = str(raw_universe.get("type") or fallback_universe_type)
        universe_code = str(raw_universe.get("code") or fallback_universe_code)
        universe_name = str(raw_universe.get("name") or universe_code)
        period_label = str(raw_period.get("label") or raw_period.get("periodEnd") or (latest.period if latest else ""))
        universe_payload = {
            **raw_universe,
            "type": universe_type,
            "code": universe_code,
            "name": universe_name,
            "scope": str(raw_period.get("sectorScope") or fallback_scope),
        }
        period_payload = {
            **raw_period,
            "latest": period_label or None,
            "quarters": len(points),
            "lookback": int(raw_period.get("lookbackYears") or 0),
        }
        sample_payload = {
            **raw_sample,
            "count": int(raw_sample.get("count") or 0),
            "coverage": float(raw_sample.get("coverage") or 0.0),
            "source": str(raw_sample.get("method") or "danginvest"),
        }
        response = MacroXrayResponse(
            ts=_parse_ts(payload.get("ts")),
            status="live" if latest or points else "unavailable",
            index=payload.get("index") or universe_code,
            universe=MacroXrayUniverse(**universe_payload),
            period=MacroXrayPeriod(**period_payload),
            sample=MacroXraySample(**sample_payload),
            latest=latest,
            points=points,
            nominalGdp=payload.get("nominalGdp") or [],
            crossIndex=payload.get("crossIndex") or [],
            insights=payload.get("insights") or [],
            diagnostics=payload.get("diagnostics") or [],
            source_status=[_source_status("danginvest_macro_xray", "live", "macro-xray")],
            methodology=str(raw_sample.get("method") or "DangInvest X-Ray compatible payload."),
        )
        return response

    def _targets_response(self, payload: dict[str, Any], *, universe_type: str) -> MacroXrayTargetsResponse:
        raw_targets = payload.get("targets") if isinstance(payload.get("targets"), list) else payload.get("items")
        targets = [_target(item) for item in (raw_targets or []) if isinstance(item, dict)]
        return MacroXrayTargetsResponse(
            ts=_parse_ts(payload.get("ts")),
            status="live" if targets else "unavailable",
            items=targets,
            targets=targets,
            source_status=[_source_status("danginvest_macro_xray_targets", "live" if targets else "unavailable", "macro-xray/targets")],
            methodology=f"DangInvest targets compatible payload for {payload.get('universeType') or universe_type}.",
        )


class PublicMacroProvider:
    def __init__(
        self,
        *,
        macro_service: MacroDataService | None = None,
        xray_service: MacroXrayService | None = None,
    ) -> None:
        self.macro_service = macro_service or MacroDataService()
        self.xray_service = xray_service or MacroXrayService(macro_service=self.macro_service)

    async def timeseries(
        self,
        *,
        series_ids: list[str],
        start: str | None,
        end: str | None,
        max_points: int,
    ) -> MacroTimeseriesResponse:
        return await self.macro_service.timeseries(series_ids=series_ids, start=start, end=end, max_points=max_points)

    async def xray(
        self,
        *,
        universe_type: str,
        universe_code: str,
        scope: str,
        quarters: int,
        lookback: int,
        period: str = "latest",
    ) -> MacroXrayResponse:
        return await self.xray_service.xray(
            universe_type=universe_type,
            universe_code=universe_code,
            scope=scope,
            period=period,
            quarters=quarters,
            lookback=lookback,
        )

    async def targets(
        self,
        *,
        universe_type: str,
        lookback: int,
        target_source: str,
    ) -> MacroXrayTargetsResponse:
        return await self.xray_service.targets(universe_type=universe_type, lookback=lookback, target_source=target_source)


class HybridMacroProvider:
    def __init__(self, *, primary: Any, fallback: Any) -> None:
        self.primary = primary
        self.fallback = fallback

    async def timeseries(self, **kwargs: Any) -> Any:
        return await self._call("timeseries", **kwargs)

    async def xray(self, **kwargs: Any) -> Any:
        return await self._call("xray", **kwargs)

    async def targets(self, **kwargs: Any) -> Any:
        return await self._call("targets", **kwargs)

    async def _call(self, method: str, **kwargs: Any) -> Any:
        try:
            return await getattr(self.primary, method)(**kwargs)
        except Exception:
            return await getattr(self.fallback, method)(**kwargs)


def macro_provider_for_settings(
    *,
    macro_service: MacroDataService | None = None,
    xray_service: MacroXrayService | None = None,
) -> MacroProvider:
    settings = get_settings()
    public = PublicMacroProvider(macro_service=macro_service, xray_service=xray_service)
    provider = settings.macro_data_provider.lower().strip()
    if provider == "public":
        return public
    danginvest = DangInvestMacroProvider(base_url=settings.danginvest_base_url, timeout_seconds=settings.danginvest_timeout_seconds)
    if provider == "danginvest":
        return danginvest
    return HybridMacroProvider(primary=danginvest, fallback=public)


def _xray_point(item: dict[str, Any]) -> MacroXrayPoint:
    payload = {
        **item,
        "period": str(item.get("period") or item.get("periodLabel") or item.get("periodEnd") or ""),
        "date": str(item.get("date") or item.get("periodEnd") or item.get("asOfDate") or ""),
    }
    return MacroXrayPoint(**payload)


def _target(item: dict[str, Any]) -> MacroXrayTarget:
    name = str(item.get("name") or item.get("label") or item.get("shortLabel") or item.get("code") or "")
    target_type = str(item.get("type") or "")
    code = str(item.get("code") or name)
    payload = {
        **item,
        "id": str(item.get("id") or f"{target_type}:{code}"),
        "type": target_type,
        "code": code,
        "name": name,
        "source": str(item.get("source") or "danginvest"),
        "status": str(item.get("status") or "live"),
    }
    return MacroXrayTarget(**payload)


def _source_status(name: str, status: str, source: str) -> MacroSourceStatus:
    return MacroSourceStatus(
        name=name,
        status=status,
        source="danginvest" if status == "live" else source,
        detail=source,
        as_of=datetime.now(UTC),
    )


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, int | float):
        seconds = float(value) / 1000 if value > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, tz=UTC)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(UTC)
    return datetime.now(UTC)
