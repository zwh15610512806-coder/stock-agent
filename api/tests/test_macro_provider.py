from datetime import UTC

import httpx


async def test_danginvest_provider_normalizes_timeseries_payload() -> None:
    from app.services.macro_provider import DangInvestMacroProvider

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/market/macro-timeseries"
        return httpx.Response(
            200,
            json={
                "ts": 1782818979434,
                "start": "2026-01-01",
                "end": "2026-06-30",
                "series": [
                    {
                        "series_id": "cn.money.m1_minus_m2_yoy",
                        "name": "M1-M2剪刀差",
                        "category": "money",
                        "frequency": "M",
                        "unit": "ppt",
                        "is_derived": True,
                        "description": "Derived",
                        "points": [
                            {"date": "2026-05-31", "point_date": "2026-05-31", "release_date": "2026-06-15", "value": -3.4}
                        ],
                    }
                ],
            },
        )

    provider = DangInvestMacroProvider(
        base_url="https://dang-invest.test",
        transport=httpx.MockTransport(handler),
    )

    response = await provider.timeseries(
        series_ids=["cn.money.m1_minus_m2_yoy"],
        start="2026-01-01",
        end="2026-06-30",
        max_points=40,
    )

    assert response.start == "2026-01-01"
    assert response.end == "2026-06-30"
    assert response.ts.tzinfo is not None
    assert response.ts.replace(tzinfo=UTC).year == 2026
    assert response.series[0].series_id == "cn.money.m1_minus_m2_yoy"
    assert response.series[0].status == "live"
    assert response.series[0].source == "danginvest"
    assert response.series[0].points[0].value == -3.4
    assert response.source_status[0].name == "danginvest_macro_timeseries"


async def test_danginvest_provider_normalizes_xray_and_targets_payloads() -> None:
    from app.services.macro_provider import DangInvestMacroProvider

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/macro-xray/targets"):
            return httpx.Response(
                200,
                json={
                    "ts": 1782818979434,
                    "universeType": "etf",
                    "lookbackYears": 6,
                    "targets": [
                        {
                            "type": "etf",
                            "code": "512200.SH",
                            "label": "南方中证全指房地产ETF",
                            "shortLabel": "南方中证",
                            "source": "中证全指房地产指数",
                            "sampleCount": 77,
                            "latestPeriod": "2026-03-31",
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "ts": 1782818979434,
                "index": {"code": "000300.SH", "name": "沪深300指数"},
                "universe": {"type": "index", "code": "000300.SH", "name": "沪深300指数"},
                "period": {"periodEnd": "2026-03-31", "label": "2026 Q1", "lookbackYears": 6, "sectorScope": "non_financial"},
                "sample": {"count": 233, "currentConstituentCount": 248, "method": "fixed_sample_v3"},
                "latest": {
                    "periodEnd": "2026-03-31",
                    "periodLabel": "2026 Q1",
                    "revenueYoy": 0.042,
                    "profitYoy": -0.018,
                    "inventoryYoy": 0.031,
                    "cashConversionRatio": 1.18,
                    "equipmentRenewalRatio": 0.64,
                },
                "points": [
                    {
                        "periodEnd": "2026-03-31",
                        "periodLabel": "2026 Q1",
                        "revenueYoy": 0.042,
                        "profitYoy": -0.018,
                        "inventoryYoy": 0.031,
                        "cashConversionRatio": 1.18,
                        "equipmentRenewalRatio": 0.64,
                    }
                ],
                "diagnostics": [],
            },
        )

    provider = DangInvestMacroProvider(
        base_url="https://dang-invest.test",
        transport=httpx.MockTransport(handler),
    )

    xray = await provider.xray(universe_type="index", universe_code="000300.SH", scope="non_financial", quarters=40, lookback=6)
    targets = await provider.targets(universe_type="etf", lookback=6, target_source="stock_basic_full_v1")

    assert xray.status == "live"
    assert xray.universe.code == "000300.SH"
    assert xray.period.latest == "2026 Q1"
    assert xray.sample.count == 233
    assert xray.latest is not None
    assert xray.latest.period == "2026 Q1"
    assert xray.latest.equipmentRenewalRatio == 0.64
    assert xray.points[0].date == "2026-03-31"
    assert xray.source_status[0].source == "danginvest"
    assert targets.items[0].code == "512200.SH"
    assert targets.targets[0].name == "南方中证全指房地产ETF"


async def test_hybrid_macro_provider_falls_back_to_public_provider() -> None:
    from app.services.macro_provider import HybridMacroProvider

    class BrokenProvider:
        async def timeseries(self, **kwargs):
            raise RuntimeError("upstream down")

    class PublicProvider:
        async def timeseries(self, **kwargs):
            return {"status": "fallback", "kwargs": kwargs}

    provider = HybridMacroProvider(primary=BrokenProvider(), fallback=PublicProvider())

    response = await provider.timeseries(series_ids=["cn.ppi.yoy"], start=None, end=None, max_points=10)

    assert response["status"] == "fallback"
    assert response["kwargs"]["series_ids"] == ["cn.ppi.yoy"]
