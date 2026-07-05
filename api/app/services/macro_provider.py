from __future__ import annotations

import json
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
from app.services.macro_xray import INDEX_TARGETS, MacroXrayService


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
        if universe_type == "index":
            return self._index_targets_response(lookback=lookback)
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
        sample_count = int(raw_sample.get("count") or 0)
        current_constituent_count = int(raw_sample.get("currentConstituentCount") or 0)
        sample_coverage = _coverage_value(raw_sample.get("coverage"))
        if sample_coverage <= 0 and current_constituent_count > 0:
            sample_coverage = sample_count / current_constituent_count
        sample_payload = {
            **raw_sample,
            "count": sample_count,
            "coverage": sample_coverage,
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
            nominalGdp=_xray_points_from_payload(payload.get("nominalGdp")),
            crossIndex=_xray_points_from_payload(payload.get("crossIndex")),
            insights=_insights_from_payload(payload.get("insights")),
            diagnostics=_diagnostics_from_payload(payload.get("diagnostics")),
            source_status=[_source_status("danginvest_macro_xray", "live", "macro-xray")],
            methodology=str(raw_sample.get("method") or "DangInvest X-Ray compatible payload."),
        )
        return response

    def _index_targets_response(self, *, lookback: int) -> MacroXrayTargetsResponse:
        targets = [
            MacroXrayTarget(
                id=f"index:{code}",
                type="index",
                code=code,
                name=name,
                source="static-index-targets",
                status="live",
            )
            for code, name in INDEX_TARGETS.items()
        ]
        return MacroXrayTargetsResponse(
            ts=datetime.now(UTC),
            status="live",
            items=targets,
            targets=targets,
            source_status=[
                MacroSourceStatus(
                    name="danginvest_macro_xray_index_targets",
                    status="live",
                    source="static-index-targets",
                    detail=f"static index targets for DangInvest X-Ray, lookback={lookback}",
                    as_of=datetime.now(UTC),
                )
            ],
            methodology="DangInvest does not expose dynamic index targets; static broad-index presets are used.",
        )

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


def _coverage_value(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, dict):
        numbers = [float(item) for item in value.values() if isinstance(item, int | float)]
        return sum(numbers) / len(numbers) if numbers else 0.0
    return 0.0


def _xray_points_from_payload(value: Any) -> list[MacroXrayPoint]:
    if isinstance(value, list):
        return [_xray_point(item) for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    if isinstance(value.get("points"), list):
        unit = value.get("unit")
        return [
            _xray_point({**item, "unit": unit} if unit is not None else item)
            for item in value["points"]
            if isinstance(item, dict)
        ]
    points: list[MacroXrayPoint] = []
    for key, item in value.items():
        if isinstance(item, dict):
            points.append(_xray_point({**item, "series": str(key)}))
    return points


def _insights_from_payload(value: Any) -> list[dict[str, str]]:
    if isinstance(value, list):
        insights: list[dict[str, str]] = []
        for item in value:
            if isinstance(item, dict):
                insights.append(
                    {
                        "level": str(item.get("level") or item.get("severity") or item.get("tone") or "info"),
                        "title": str(item.get("title") or item.get("label") or item.get("headline") or "Insight"),
                        "detail": str(item.get("detail") or item.get("text") or item.get("summary") or ""),
                    }
                )
        return insights
    if not isinstance(value, dict):
        return []

    insights = []
    headline = value.get("headline")
    if headline:
        facts = value.get("facts") if isinstance(value.get("facts"), list) else []
        detail = value.get("realEstateReadthrough") or value.get("equityStyleReadthrough") or "；".join(map(str, facts[:3]))
        insights.append({"level": str(value.get("tone") or "info"), "title": str(headline), "detail": str(detail or "")})
    diagnoses = value.get("diagnoses")
    if isinstance(diagnoses, list):
        for item in diagnoses:
            if isinstance(item, dict):
                insights.append(
                    {
                        "level": str(item.get("severity") or "info"),
                        "title": str(item.get("label") or item.get("id") or "Diagnosis"),
                        "detail": str(item.get("text") or ""),
                    }
                )
    return insights


def _diagnostics_from_payload(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value]
    if not isinstance(value, dict):
        return []
    diagnostics: list[str] = []
    for key in ("requestedQuarters", "fetchedRows", "parsedRows", "targetRows", "returnedPoints"):
        if key in value:
            diagnostics.append(f"{key}: {value[key]}")
    filters = value.get("filters")
    if isinstance(filters, dict):
        compact = {key: filters.get(key) for key in ("universeType", "universeCode", "sectorScope", "periodEnd", "asOfDate") if key in filters}
        if compact:
            diagnostics.append(f"filters: {json.dumps(compact, ensure_ascii=False, sort_keys=True)}")
    selected = value.get("selectedVariant")
    if isinstance(selected, dict):
        compact = {key: selected.get(key) for key in ("calcVersion", "sampleMethod", "latestPeriod", "latestAsOfDate") if key in selected}
        if compact:
            diagnostics.append(f"selectedVariant: {json.dumps(compact, ensure_ascii=False, sort_keys=True)}")
    return diagnostics or [json.dumps(value, ensure_ascii=False, sort_keys=True)]


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
