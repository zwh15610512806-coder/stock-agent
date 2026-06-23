from app.services.symbols import display_name_for_symbol, normalize_symbol, yahoo_symbol


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
