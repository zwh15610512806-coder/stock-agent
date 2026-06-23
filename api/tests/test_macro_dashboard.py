from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return self.rows


class MacroAkShare:
    def macro_china_lpr(self) -> FakeTable:
        return FakeTable(
            [
                {"date": "2026-05-20", "lpr_1y": 3.0, "lpr_5y": 3.5},
                {"date": "2026-06-20", "lpr_1y": 2.95, "lpr_5y": 3.45},
            ]
        )

    def macro_china_cpi(self) -> FakeTable:
        return FakeTable([{"month": "2026-05", "cpi_yoy": "0.2%"}])

    def macro_china_gdp(self) -> FakeTable:
        return FakeTable([{"quarter": "2026Q1", "gdp_yoy": 5.4}])

    def macro_china_pmi(self) -> FakeTable:
        return FakeTable([{"month": "2026-05", "manufacturing_pmi": 49.5}])

    def macro_china_new_financial_credit(self) -> FakeTable:
        return FakeTable([{"month": "2026-05", "new_rmb_loans": 620000000000}])

    def bond_zh_us_rate(self) -> FakeTable:
        return FakeTable([{"date": "2026-06-23", "china_10y": 1.68, "us_10y": 4.37}])

    def currency_boc_sina(self) -> FakeTable:
        return FakeTable(
            [
                {"date": "2026-06-23", "currency": "USD", "boc_mid": 716.2},
                {"date": "2026-06-23", "currency": "EUR", "boc_mid": 828.35},
            ]
        )


async def test_macro_dashboard_uses_real_akshare_sources(tmp_path) -> None:
    from app.services.macro import MacroDataService
    from app.services.market_cache import MarketSnapshotCache

    service = MacroDataService(
        akshare_module=MacroAkShare(),
        snapshot_cache=MarketSnapshotCache(tmp_path / "macro_cache.sqlite3"),
    )

    dashboard = await service.dashboard()

    assert dashboard.cache_status == "live"
    assert dashboard.rates[0].name == "LPR 1Y"
    assert dashboard.rates[0].value == 2.95
    assert dashboard.rates[0].as_of == datetime(2026, 6, 20, tzinfo=UTC)
    assert dashboard.rates[1].name == "LPR 5Y"
    assert dashboard.rates[1].value == 3.45
    assert next(item for item in dashboard.indicators if item.name == "China CPI YoY").value == 0.2
    assert next(item for item in dashboard.indicators if item.name == "China GDP YoY").value == 5.4
    assert next(item for item in dashboard.indicators if item.name == "China Manufacturing PMI").value == 49.5
    assert next(item for item in dashboard.indicators if item.name == "China New RMB Loans").value == 620000000000
    assert next(item for item in dashboard.bond_yields if item.name == "China 10Y Government Bond Yield").value == 1.68
    assert next(item for item in dashboard.bond_yields if item.name == "US 10Y Treasury Yield").value == 4.37
    assert next(item for item in dashboard.fx_rates if item.name == "USD/CNY").value == 7.162
    assert all(status.status == "live" for status in dashboard.source_status)
    assert dashboard.disclaimer


async def test_macro_dashboard_marks_failed_source_unavailable_without_sample_data(tmp_path) -> None:
    from app.services.macro import MacroDataService
    from app.services.market_cache import MarketSnapshotCache

    class FailingCpiAkShare(MacroAkShare):
        def macro_china_cpi(self) -> FakeTable:
            raise RuntimeError("cpi source down")

    service = MacroDataService(
        akshare_module=FailingCpiAkShare(),
        snapshot_cache=MarketSnapshotCache(tmp_path / "macro_cache.sqlite3"),
    )

    dashboard = await service.dashboard()

    cpi = next(item for item in dashboard.indicators if item.name == "China CPI YoY")
    cpi_status = next(item for item in dashboard.source_status if item.name == "macro_china_cpi")
    assert dashboard.cache_status == "partial"
    assert cpi.value is None
    assert cpi.status == "unavailable"
    assert cpi_status.status == "unavailable"
    assert "cpi source down" in cpi_status.detail
    assert next(item for item in dashboard.indicators if item.name == "China GDP YoY").value == 5.4


def test_macro_dashboard_endpoint_contract(tmp_path) -> None:
    from app.routers import macro
    from app.services.macro import MacroDataService
    from app.services.market_cache import MarketSnapshotCache

    app = FastAPI()
    app.state.macro_service = MacroDataService(
        akshare_module=MacroAkShare(),
        snapshot_cache=MarketSnapshotCache(tmp_path / "macro_cache.sqlite3"),
    )
    app.include_router(macro.router)
    client = TestClient(app)

    response = client.get("/api/macro/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "as_of",
        "cache_status",
        "source_status",
        "rates",
        "indicators",
        "bond_yields",
        "fx_rates",
        "disclaimer",
    }
    assert body["rates"][0]["name"] == "LPR 1Y"
    assert body["fx_rates"][0]["name"] == "USD/CNY"
