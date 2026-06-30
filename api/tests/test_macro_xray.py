class FakeTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return self.rows


class XrayAkShare:
    def macro_china_industrial_production_yoy(self) -> FakeTable:
        return FakeTable(
            [
                {"month": "2025-07", "industrial_production_yoy": 4.2},
                {"month": "2025-10", "industrial_production_yoy": 5.1},
                {"month": "2026-01", "industrial_production_yoy": 5.5},
                {"month": "2026-04", "industrial_production_yoy": 6.0},
            ]
        )

    def macro_china_ppi(self) -> FakeTable:
        return FakeTable(
            [
                {"month": "2025-07", "ppi_yoy": -1.5},
                {"month": "2025-10", "ppi_yoy": -1.0},
                {"month": "2026-01", "ppi_yoy": -0.3},
                {"month": "2026-04", "ppi_yoy": 0.4},
            ]
        )

    def macro_china_money_supply(self) -> FakeTable:
        return FakeTable(
            [
                {"month": "2025-07", "m1_yoy": 3.0, "m2_yoy": 7.0},
                {"month": "2025-10", "m1_yoy": 4.2, "m2_yoy": 7.3},
                {"month": "2026-01", "m1_yoy": 5.0, "m2_yoy": 7.6},
                {"month": "2026-04", "m1_yoy": 5.9, "m2_yoy": 7.8},
            ]
        )

    def macro_china_shrzgm(self) -> FakeTable:
        return FakeTable(
            [
                {"month": "2025-07", "social_financing_yoy": 8.4},
                {"month": "2025-10", "social_financing_yoy": 8.8},
                {"month": "2026-01", "social_financing_yoy": 9.1},
                {"month": "2026-04", "social_financing_yoy": 9.4},
            ]
        )

    def stock_board_industry_name_em(self) -> FakeTable:
        return FakeTable(
            [
                {"板块名称": "半导体", "板块代码": "BK1036"},
                {"板块名称": "银行", "板块代码": "BK0475"},
            ]
        )


async def test_macro_xray_builds_public_proxy_for_default_csi300(tmp_path) -> None:
    from app.services.macro import MacroDataService
    from app.services.macro_xray import MacroXrayService
    from app.services.market_cache import MarketSnapshotCache

    macro_service = MacroDataService(
        akshare_module=XrayAkShare(),
        snapshot_cache=MarketSnapshotCache(tmp_path / "macro_cache.sqlite3"),
    )
    xray = MacroXrayService(macro_service=macro_service, akshare_module=XrayAkShare())

    response = await xray.xray(
        universe_type="index",
        universe_code="000300.SH",
        scope="non_financial",
        quarters=4,
        lookback=6,
    )

    assert response.status == "live"
    assert response.universe.type == "index"
    assert response.universe.code == "000300.SH"
    assert response.period.quarters == 4
    assert len(response.points) == 4
    assert response.latest is not None
    assert response.latest.revenueYoy is not None
    assert response.latest.profitYoy is not None
    assert response.latest.inventoryYoy is not None
    assert response.latest.cashConversionRatio is not None
    assert response.source_status
    assert "公开宏观源近似" in response.methodology


async def test_macro_xray_targets_returns_index_and_industry_targets(tmp_path) -> None:
    from app.services.macro import MacroDataService
    from app.services.macro_xray import MacroXrayService
    from app.services.market_cache import MarketSnapshotCache

    macro_service = MacroDataService(
        akshare_module=XrayAkShare(),
        snapshot_cache=MarketSnapshotCache(tmp_path / "macro_cache.sqlite3"),
    )
    xray = MacroXrayService(macro_service=macro_service, akshare_module=XrayAkShare())

    response = await xray.targets(universe_type="industry", lookback=6, target_source="stock_basic_full_v1")

    assert response.status == "live"
    assert any(item.code == "BK1036" and item.type == "industry" for item in response.items)
    assert all(item.source for item in response.items)
    assert response.methodology


async def test_macro_xray_marks_empty_public_sources_unavailable(tmp_path) -> None:
    from app.services.macro import MacroDataService
    from app.services.macro_xray import MacroXrayService
    from app.services.market_cache import MarketSnapshotCache

    class EmptyAkShare:
        def macro_china_industrial_production_yoy(self) -> FakeTable:
            return FakeTable([])

    macro_service = MacroDataService(
        akshare_module=EmptyAkShare(),
        snapshot_cache=MarketSnapshotCache(tmp_path / "macro_cache.sqlite3"),
    )
    xray = MacroXrayService(macro_service=macro_service, akshare_module=EmptyAkShare())

    response = await xray.xray(universe_type="index", universe_code="000300.SH", quarters=4)

    assert response.status == "unavailable"
    assert response.points == []
    assert response.latest is None
    assert response.diagnostics
