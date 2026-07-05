from app.services.symbols import currency_for_market, display_name_for_symbol, infer_market, yahoo_symbol


def test_overseas_index_metadata_uses_chinese_labels_and_yahoo_symbols() -> None:
    assert display_name_for_symbol("DJI") == "道琼斯工业指数"
    assert display_name_for_symbol("SPX") == "标普500指数"
    assert display_name_for_symbol("NDX") == "纳斯达克100指数"
    assert display_name_for_symbol("KS11") == "韩国综合指数"
    assert display_name_for_symbol("N225") == "日经225指数"

    assert infer_market("KS11") == "KR"
    assert infer_market("N225") == "JP"
    assert currency_for_market("KR") == "KRW"
    assert currency_for_market("JP") == "JPY"

    assert yahoo_symbol("KS11") == "^KS11"
    assert yahoo_symbol("N225") == "^N225"
