from app.services.symbols import display_name_for_symbol, normalize_symbol, search_static_symbols, yahoo_symbol


class FakeTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return self.rows


class FakeAkShare:
    def __init__(self) -> None:
        self.calls = 0

    def stock_info_a_code_name(self) -> FakeTable:
        self.calls += 1
        return FakeTable(
            [
                {"code": "601318", "name": "中国平安"},
                {"code": "688001", "name": "华兴源创"},
            ]
        )


def test_normalizes_cn_hk_and_us_symbols() -> None:
    assert normalize_symbol("600519", "CN") == "600519.SH"
    assert normalize_symbol("000001", "CN") == "000001.SZ"
    assert normalize_symbol("00700", "HK") == "00700.HK"
    assert normalize_symbol("AAPL", "US") == "AAPL"


def test_keeps_explicit_market_suffix_uppercase() -> None:
    assert normalize_symbol("00700.hk", None) == "00700.HK"
    assert normalize_symbol("msft", "US") == "MSFT"


def test_keeps_alphabetic_hk_index_symbols_unpadded() -> None:
    assert normalize_symbol("hsi.hk", None) == "HSI.HK"
    assert normalize_symbol("hstech.hk", None) == "HSTECH.HK"


def test_hang_seng_tech_index_has_display_name_and_yahoo_symbol() -> None:
    assert display_name_for_symbol("HSTECH.HK") == "恒生科技指数"
    assert yahoo_symbol("HSTECH.HK") == "^HSTECH"


def test_search_static_symbols_includes_cached_full_a_share_pool() -> None:
    fake_akshare = FakeAkShare()

    first = search_static_symbols("中国平安", {"CN"}, akshare_module=fake_akshare)
    second = search_static_symbols("688001", {"CN"}, akshare_module=fake_akshare)

    assert any(item.symbol == "601318.SH" and item.name == "中国平安" for item in first)
    assert any(item.symbol == "688001.SH" and item.exchange == "SH" for item in second)
    assert fake_akshare.calls == 1
