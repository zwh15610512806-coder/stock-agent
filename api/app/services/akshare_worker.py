from __future__ import annotations

import json
import os
import sys
from typing import Any

from app.services.market import AKSHARE_WORKER_ENV, MarketDataService


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        sys.stderr.write("missing akshare worker operation\n")
        return 2

    os.environ[AKSHARE_WORKER_ENV] = "1"
    operation = args[0]
    service = MarketDataService()

    try:
        result = _run_operation(service, operation, args[1:])
    except Exception as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1

    sys.stdout.write(json.dumps(_jsonable(result), ensure_ascii=True))
    return 0


def _run_operation(service: MarketDataService, operation: str, args: list[str]) -> Any:
    if operation == "a_share_activity":
        return service._fetch_a_share_activity_sync()
    if operation == "industry_heatmap":
        return service._fetch_fund_flow_heatmap_sync("industry")
    if operation == "sector_heatmap":
        return service._fetch_sector_heatmap_sync()
    if operation == "concept_heatmap":
        return service._fetch_fund_flow_heatmap_sync("concept")
    if operation == "region_heatmap":
        return service._fetch_region_heatmap_sync()
    if operation == "etf_heatmap":
        return service._fetch_etf_heatmap_sync()
    if operation == "fund_flow_summary":
        return service._fetch_fund_flow_summary_sync()
    if operation == "market_news":
        return service._fetch_market_news_sync()
    if operation == "commodity_quotes":
        return service._fetch_commodity_quotes_sync()
    if operation == "dragon_tiger":
        return service._fetch_dragon_tiger_sync()
    if operation == "quote":
        if len(args) != 1:
            raise ValueError("quote operation expects symbol")
        return service._fetch_akshare_quote_sync(args[0])
    if operation == "candles":
        if len(args) != 3:
            raise ValueError("candles operation expects symbol period limit")
        return service._fetch_akshare_candles_sync(args[0], args[1], int(args[2]))
    raise ValueError(f"unsupported akshare worker operation: {operation}")


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


if __name__ == "__main__":
    raise SystemExit(main())
