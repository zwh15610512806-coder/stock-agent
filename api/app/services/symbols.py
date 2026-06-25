import importlib
import time
from collections.abc import Iterable, Mapping

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

A_SHARE_POOL_SOURCE = "akshare-stock-info-a-code-name"
A_SHARE_POOL_TTL_SECONDS = 6 * 60 * 60
_A_SHARE_POOL_CACHE: dict[tuple[int, str], tuple[float, list[SymbolSearchResult]]] = {}


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


def search_static_symbols(
    query: str,
    markets: set[MarketCode] | None = None,
    akshare_module: object | None = None,
) -> list[SymbolSearchResult]:
    raw_term = query.strip()
    term = raw_term.upper()
    if not raw_term:
        return []
    matches: list[SymbolSearchResult] = []
    seen: set[str] = set()
    for item in STATIC_SYMBOLS:
        if markets and item.market not in markets:
            continue
        if term in item.symbol.upper() or raw_term in item.name:
            matches.append(item)
            seen.add(item.symbol)
    if markets is None or "CN" in markets:
        for item in _a_share_pool(akshare_module):
            if item.symbol in seen:
                continue
            if term in item.symbol.upper() or term in item.symbol.removesuffix(".SH").removesuffix(".SZ").removesuffix(".BJ") or raw_term in item.name:
                matches.append(item)
                seen.add(item.symbol)
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


def _a_share_pool(akshare_module: object | None = None) -> list[SymbolSearchResult]:
    module = akshare_module or _import_akshare()
    if module is None:
        return []
    cache_key = _a_share_pool_cache_key(module)
    cached = _A_SHARE_POOL_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < A_SHARE_POOL_TTL_SECONDS:
        return cached[1]
    try:
        rows = _records(module.stock_info_a_code_name())
    except Exception:
        return []
    items: list[SymbolSearchResult] = []
    seen: set[str] = set()
    for row in rows:
        code = _clean_text(_row_value(row, ("code", "代码", "股票代码", "证券代码", "symbol")))
        name = _clean_text(_row_value(row, ("name", "名称", "股票简称", "证券简称")))
        symbol = _normalize_a_share_pool_code(code)
        if not symbol or not name or symbol in seen:
            continue
        seen.add(symbol)
        exchange = _exchange_for_symbol(symbol)
        items.append(
            SymbolSearchResult(
                symbol=symbol,
                name=name,
                market="CN",
                currency="CNY",
                type="stock",
                source=A_SHARE_POOL_SOURCE,
                exchange=exchange,
            )
        )
    _A_SHARE_POOL_CACHE[cache_key] = (time.time(), items)
    return items


def _import_akshare() -> object | None:
    try:
        return importlib.import_module("akshare")
    except Exception:
        return None


def _a_share_pool_cache_key(module: object) -> tuple[int, str]:
    module_type = type(module)
    return id(module), f"{module_type.__module__}.{module_type.__qualname__}"


def _normalize_a_share_pool_code(code: str) -> str:
    raw = code.strip().upper()
    if not raw:
        return ""
    for prefix in ("SH", "SZ", "BJ"):
        if raw.startswith(prefix) and raw[len(prefix):].isdigit():
            raw = raw[len(prefix):]
            break
    if raw.endswith((".SH", ".SZ", ".BJ")):
        return normalize_symbol(raw, "CN")
    if raw.isdigit():
        return normalize_symbol(raw.zfill(6), "CN")
    return ""


def _exchange_for_symbol(symbol: str) -> str | None:
    if symbol.endswith(".SH"):
        return "SH"
    if symbol.endswith(".SZ"):
        return "SZ"
    if symbol.endswith(".BJ"):
        return "BJ"
    return None


def _records(table: object) -> list[Mapping[str, object]]:
    if hasattr(table, "to_dict"):
        raw_records = table.to_dict("records")
    else:
        raw_records = table
    if not isinstance(raw_records, Iterable):
        return []
    records: list[Mapping[str, object]] = []
    for row in raw_records:
        if isinstance(row, Mapping):
            records.append(row)
    return records


def _row_value(row: Mapping[str, object], names: tuple[str, ...]) -> object:
    for name in names:
        if name in row:
            return row[name]
    lower_names = {name.lower() for name in names}
    for key, value in row.items():
        if str(key).lower() in lower_names:
            return value
    return None


def _clean_text(value: object) -> str:
    return str(value or "").strip()
