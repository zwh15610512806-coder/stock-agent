from app.schemas.market import MarketCode, SymbolSearchResult


STATIC_SYMBOLS: list[SymbolSearchResult] = [
    SymbolSearchResult(symbol="000001.SH", name="上证指数", market="CN", currency="CNY"),
    SymbolSearchResult(symbol="399001.SZ", name="深证成指", market="CN", currency="CNY"),
    SymbolSearchResult(symbol="399006.SZ", name="创业板指", market="CN", currency="CNY"),
    SymbolSearchResult(symbol="HSTECH.HK", name="恒生科技指数", market="HK", currency="HKD"),
    SymbolSearchResult(symbol="HSCEI.HK", name="恒生国企", market="HK", currency="HKD"),
    SymbolSearchResult(symbol="HSI.HK", name="恒生指数", market="HK", currency="HKD"),
    SymbolSearchResult(symbol="600519.SH", name="贵州茅台", market="CN", currency="CNY"),
    SymbolSearchResult(symbol="000858.SZ", name="五粮液", market="CN", currency="CNY"),
    SymbolSearchResult(symbol="300750.SZ", name="宁德时代", market="CN", currency="CNY"),
    SymbolSearchResult(symbol="00700.HK", name="腾讯控股", market="HK", currency="HKD"),
    SymbolSearchResult(symbol="09988.HK", name="阿里巴巴-W", market="HK", currency="HKD"),
    SymbolSearchResult(symbol="03690.HK", name="美团-W", market="HK", currency="HKD"),
    SymbolSearchResult(symbol="AAPL", name="Apple", market="US", currency="USD"),
    SymbolSearchResult(symbol="MSFT", name="Microsoft", market="US", currency="USD"),
    SymbolSearchResult(symbol="NVDA", name="NVIDIA", market="US", currency="USD"),
    SymbolSearchResult(symbol="TSLA", name="Tesla", market="US", currency="USD"),
]


def normalize_symbol(value: str, market: MarketCode | None = None) -> str:
    raw = value.strip().upper()
    if not raw:
        return raw
    if raw.endswith(".SS"):
        return raw.removesuffix(".SS") + ".SH"
    if raw.endswith((".SH", ".SZ", ".BJ", ".HK")):
        if raw.endswith(".HK"):
            code = raw.removesuffix(".HK")
            return f"{code.zfill(5) if code.isdigit() else code}.HK"
        return raw
    if market == "HK":
        return raw.zfill(5) + ".HK" if raw.isdigit() else raw
    if market == "US":
        return raw
    if market == "CN" and raw.isdigit():
        return _normalize_cn_code(raw)
    if raw.isdigit() and len(raw) == 5:
        return raw + ".HK"
    return raw


def infer_market(symbol: str) -> MarketCode:
    normalized = normalize_symbol(symbol, None)
    if normalized.endswith(".HK"):
        return "HK"
    if normalized.endswith((".SH", ".SZ", ".BJ")):
        return "CN"
    return "US"


def currency_for_market(market: MarketCode) -> str:
    return {"CN": "CNY", "HK": "HKD", "US": "USD"}[market]


def search_static_symbols(query: str, markets: set[MarketCode] | None = None) -> list[SymbolSearchResult]:
    term = query.strip().upper()
    if not term:
        return []
    matches = []
    for item in STATIC_SYMBOLS:
        if markets and item.market not in markets:
            continue
        if term in item.symbol.upper() or query.strip() in item.name:
            matches.append(item)
    return matches


def display_name_for_symbol(symbol: str) -> str:
    normalized = normalize_symbol(symbol, None)
    for item in STATIC_SYMBOLS:
        if item.symbol == normalized:
            return item.name
    return normalized


def yahoo_symbol(symbol: str) -> str:
    normalized = normalize_symbol(symbol, None)
    index_map = {
        "000001.SH": "000001.SS",
        "399001.SZ": "399001.SZ",
        "399006.SZ": "399006.SZ",
        "HSTECH.HK": "^HSTECH",
        "HSI.HK": "^HSI",
        "HSCEI.HK": "^HSCE",
        "DJI": "^DJI",
        "SPX": "^GSPC",
        "NDX": "^NDX",
    }
    if normalized in index_map:
        return index_map[normalized]
    if normalized.endswith(".SH"):
        return normalized.removesuffix(".SH") + ".SS"
    if normalized.endswith(".HK"):
        return normalized.removesuffix(".HK").zfill(4) + ".HK"
    return normalized


def _normalize_cn_code(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return f"{code}.SH"
    if code.startswith(("0", "2", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return code
