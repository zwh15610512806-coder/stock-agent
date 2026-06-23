import asyncio

from app.services.market import MarketDataService, _parse_tencent_quote_line


class FakeTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return self.rows


class FakeAkShare:
    def stock_zh_a_spot_em(self) -> FakeTable:
        return FakeTable(
            [
                {
                    "代码": "600519",
                    "名称": "贵州茅台",
                    "最新价": 1200.5,
                    "涨跌额": 10.5,
                    "涨跌幅": 0.88,
                    "成交量": 10000,
                    "成交额": 12005000,
                }
            ]
        )

    def stock_hk_spot_em(self) -> FakeTable:
        return FakeTable(
            [
                {
                    "代码": "00700",
                    "名称": "腾讯控股",
                    "最新价": 390.2,
                    "涨跌额": -2.1,
                    "涨跌幅": -0.54,
                    "成交量": 20000,
                    "成交额": 7804000,
                }
            ]
        )

    def stock_zh_a_hist(
        self,
        symbol: str,
        period: str,
        start_date: str,
        end_date: str,
        adjust: str,
    ) -> FakeTable:
        assert symbol == "600519"
        assert period == "daily"
        assert adjust == ""
        assert start_date
        assert end_date
        return FakeTable(
            [
                {
                    "日期": "2026-06-18",
                    "开盘": 1190.0,
                    "最高": 1210.0,
                    "最低": 1185.0,
                    "收盘": 1200.0,
                    "成交量": 10000,
                },
                {
                    "日期": "2026-06-19",
                    "开盘": 1200.0,
                    "最高": 1220.0,
                    "最低": 1195.0,
                    "收盘": 1215.0,
                    "成交量": 11000,
                },
            ]
        )


class ProxyAwareAkShare(FakeAkShare):
    def __init__(self) -> None:
        self.proxy_seen: tuple[str | None, str | None] | None = None

    def stock_zh_a_spot_em(self) -> FakeTable:
        import os

        self.proxy_seen = (os.environ.get("HTTP_PROXY"), os.environ.get("HTTPS_PROXY"))
        return super().stock_zh_a_spot_em()


async def test_cn_and_hk_quotes_prefer_akshare_provider() -> None:
    service = MarketDataService(akshare_module=FakeAkShare())

    quotes = await service.quotes(["600519.SH", "00700.HK"])

    assert quotes[0].source == "akshare-eastmoney-free"
    assert quotes[0].name == "贵州茅台"
    assert quotes[0].price == 1200.5
    assert quotes[0].change_pct == 0.88
    assert quotes[1].source == "akshare-eastmoney-free"
    assert quotes[1].name == "腾讯控股"
    assert quotes[1].currency == "HKD"


async def test_cn_candles_prefer_akshare_provider() -> None:
    service = MarketDataService(akshare_module=FakeAkShare())

    candles = await service.candles("600519.SH", "daily", 20)

    assert len(candles) == 2
    assert candles[-1].source == "akshare-eastmoney-free"
    assert candles[-1].date == "2026-06-19"
    assert candles[-1].close == 1215.0


async def test_index_quote_uses_tencent_before_akshare() -> None:
    class IndexQuoteService(MarketDataService):
        def __init__(self) -> None:
            super().__init__()
            self.akshare_called = False

        def _fetch_akshare_quote_sync(self, symbol: str):
            self.akshare_called = True
            raise RuntimeError("akshare should not be first for market indices")

        async def _fetch_tencent_quote(self, symbol: str):
            return self._sample_quote(symbol).model_copy(update={"source": "tencent-free-delayed"})

    service = IndexQuoteService()

    quote = await service.quote("HSTECH.HK")

    assert quote.source == "tencent-free-delayed"
    assert service.akshare_called is False


async def test_index_candles_use_yahoo_before_akshare() -> None:
    class IndexCandleService(MarketDataService):
        def __init__(self) -> None:
            super().__init__()
            self.akshare_called = False

        def _fetch_akshare_candles_sync(self, symbol: str, period: str, limit: int):
            self.akshare_called = True
            raise RuntimeError("akshare should not be first for market indices")

        async def _fetch_yahoo_candles(self, symbol: str, period: str, limit: int):
            return [
                candle.model_copy(update={"source": "Yahoo Finance/free delayed fallback"})
                for candle in self._sample_candles(symbol, period, limit)
            ]

    service = IndexCandleService()

    candles = await service.candles("000001.SH", "daily", 20)

    assert candles[-1].source == "Yahoo Finance/free delayed fallback"
    assert service.akshare_called is False


async def test_quotes_fetch_symbols_concurrently() -> None:
    class SlowQuoteService(MarketDataService):
        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.max_active = 0

        async def _fetch_primary_quote(self, symbol: str):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return self._sample_quote(symbol)

    service = SlowQuoteService()

    quotes = await service.quotes(["AAPL", "MSFT", "NVDA"])

    assert [quote.symbol for quote in quotes] == ["AAPL", "MSFT", "NVDA"]
    assert service.max_active > 1


async def test_overview_fetches_market_batches_concurrently() -> None:
    class SlowOverviewService(MarketDataService):
        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.max_active = 0

        async def quotes(self, symbols: list[str]):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return [self._sample_quote(symbol) for symbol in symbols]

    service = SlowOverviewService()

    overview = await service.overview(["CN", "HK", "US"])

    assert [item.market for item in overview] == ["CN", "HK", "US"]
    assert service.max_active > 1


async def test_akshare_calls_ignore_proxy_environment(monkeypatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
    fake_akshare = ProxyAwareAkShare()
    service = MarketDataService(akshare_module=fake_akshare)

    await service.quote("600519.SH")

    assert fake_akshare.proxy_seen == (None, None)
    assert __import__("os").environ["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert __import__("os").environ["HTTPS_PROXY"] == "http://127.0.0.1:7890"


def test_real_akshare_quote_runs_in_worker_without_injected_module(monkeypatch) -> None:
    service = MarketDataService()
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_worker(operation: str, *args: str, timeout_seconds: float = 5.0):
        calls.append((operation, args))
        return service._sample_quote(args[0]).model_copy(update={"source": "worker-akshare"}).model_dump(mode="json")

    monkeypatch.setattr(service, "_run_akshare_worker_sync", fake_worker)

    quote = service._fetch_akshare_quote_sync("600519.SH")

    assert calls == [("quote", ("600519.SH",))]
    assert quote.source == "worker-akshare"


def test_parses_tencent_quote_line() -> None:
    line = (
        'v_sh600519="1~贵州茅台~600519~1215.00~1240.00~1235.00~57472~25106~32365~'
        '1215.00~123~1214.95~2~1214.88~1~1214.48~1~1214.40~1~1215.28~1~1215.96~1~'
        '1216.00~2~1218.00~1~1218.89~1~~20260618161404~-25.00~-2.02~1238.87~'
        '1211.22~1215.00/57472/7016713941~57472~701671~0.46";'
    )

    quote = _parse_tencent_quote_line("600519.SH", line)

    assert quote is not None
    assert quote.source == "tencent-free-delayed"
    assert quote.name == "贵州茅台"
    assert quote.price == 1215
    assert quote.change == -25
    assert quote.change_pct == -2.02
    assert quote.turnover == 701671000
