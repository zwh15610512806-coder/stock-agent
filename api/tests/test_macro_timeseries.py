from datetime import UTC, datetime


class FakeTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return self.rows


class TimeseriesAkShare:
    def macro_china_money_supply(self) -> FakeTable:
        return FakeTable(
            [
                {"month": "2026-01", "m1_yoy": 4.0, "m2_yoy": 7.0},
                {"month": "2026-02", "m1_yoy": 4.8, "m2_yoy": 7.1},
                {"month": "2026-03", "m1_yoy": 5.2, "m2_yoy": 7.4},
                {"month": "2026-04", "m1_yoy": 5.7, "m2_yoy": 7.6},
            ]
        )

    def bond_zh_us_rate(self) -> FakeTable:
        return FakeTable(
            [
                {"date": "2026-03-31", "china_10y": 1.8, "us_10y": 4.1},
                {"date": "2026-04-30", "china_10y": 1.9, "us_10y": 4.3},
            ]
        )


async def test_macro_timeseries_returns_filtered_danginvest_style_series(tmp_path) -> None:
    from app.services.macro import MacroDataService
    from app.services.market_cache import MarketSnapshotCache

    service = MacroDataService(
        akshare_module=TimeseriesAkShare(),
        snapshot_cache=MarketSnapshotCache(tmp_path / "macro_cache.sqlite3"),
    )

    response = await service.timeseries(
        series_ids=["cn.money.m1_yoy", "cn.money.m2_yoy", "cn.money.m1_minus_m2_yoy"],
        start="2026-02-01",
        end="2026-04-30",
        max_points=2,
    )

    assert response.start == "2026-02-01"
    assert response.end == "2026-04-30"
    assert [series.series_id for series in response.series] == [
        "cn.money.m1_yoy",
        "cn.money.m2_yoy",
        "cn.money.m1_minus_m2_yoy",
    ]
    assert response.series[0].points[0].date == "2026-03-01"
    assert response.series[0].points[-1].date == "2026-04-01"
    assert response.series[0].points[-1].value == 5.7
    assert response.series[2].is_derived is True
    assert response.series[2].points[-1].value == -1.9
    assert all(series.status == "live" for series in response.series)
    assert response.source_status[0].name == "macro_china_money_supply"


async def test_macro_timeseries_derives_cn_us_10y_spread(tmp_path) -> None:
    from app.services.macro import MacroDataService
    from app.services.market_cache import MarketSnapshotCache

    service = MacroDataService(
        akshare_module=TimeseriesAkShare(),
        snapshot_cache=MarketSnapshotCache(tmp_path / "macro_cache.sqlite3"),
    )

    response = await service.timeseries(
        series_ids=["cn.rate.cn10y", "us.rate.us10y", "cn.rate.cn_us_10y_spread"],
        start="2026-03-01",
        end="2026-04-30",
        max_points=10,
    )

    spread = next(series for series in response.series if series.series_id == "cn.rate.cn_us_10y_spread")
    assert spread.is_derived is True
    assert spread.points[-1].date == "2026-04-30"
    assert spread.points[-1].value == -2.4
    assert spread.methodology


async def test_macro_timeseries_marks_missing_public_source_unavailable_without_fake_points(tmp_path) -> None:
    from app.services.macro import MacroDataService
    from app.services.market_cache import MarketSnapshotCache

    service = MacroDataService(
        akshare_module=TimeseriesAkShare(),
        snapshot_cache=MarketSnapshotCache(tmp_path / "macro_cache.sqlite3"),
    )

    response = await service.timeseries(
        series_ids=["cn.real_estate.loan_yoy"],
        start="2026-01-01",
        end="2026-04-30",
        max_points=10,
    )

    assert response.series[0].series_id == "cn.real_estate.loan_yoy"
    assert response.series[0].status == "unavailable"
    assert response.series[0].points == []
    assert response.series[0].source == "unavailable"
    assert response.source_status[0].status == "unavailable"
    assert response.ts.replace(tzinfo=UTC) <= datetime.now(UTC)
