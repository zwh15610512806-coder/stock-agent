import json

import httpx

from app.schemas.portfolio import PortfolioPosition
from app.services.ocr import parse_position_text_lines
from app.services.ocr import DoubaoVisionOcrService, parse_ai_position_payload, parse_ocr_text_result


class FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient: str):
        assert orient == "records"
        return self.rows


class FakeAshareNames:
    def __init__(self, rows):
        self.rows = rows

    def stock_info_a_code_name(self):
        return FakeTable(self.rows)


def test_parses_common_broker_position_lines() -> None:
    positions = parse_position_text_lines(
        [
            "贵州茅台 600519 持仓 10 成本 1000.00 现价 1200.00",
            "腾讯控股 00700.HK 数量 20 成本价 300 当前价 250",
        ]
    )

    assert positions[0].symbol == "600519.SH"
    assert positions[0].name == "贵州茅台"
    assert positions[0].quantity == 10
    assert positions[0].cost_price == 1000
    assert positions[0].current_price == 1200
    assert positions[1].symbol == "00700.HK"
    assert positions[1].market == "HK"


def test_parses_fragmented_ocr_position_lines() -> None:
    positions = parse_position_text_lines(
        [
            "贵州茅台",
            "600519",
            "持仓",
            "10",
            "成本",
            "1000.00",
            "现价",
            "1200.00",
        ]
    )

    assert positions[0].symbol == "600519.SH"
    assert positions[0].name == "贵州茅台"
    assert positions[0].quantity == 10
    assert positions[0].cost_price == 1000
    assert positions[0].current_price == 1200


def test_parses_ths_fragmented_holding_block_with_available_column() -> None:
    positions = parse_position_text_lines(
        [
            "同花顺App",
            "资产",
            "持仓",
            "可用",
            "成本",
            "现价",
            "贵州茅台",
            "600519",
            "10",
            "10",
            "1000.00",
            "1200.00",
        ]
    )

    assert positions[0].symbol == "600519.SH"
    assert positions[0].name == "贵州茅台"
    assert positions[0].quantity == 10
    assert positions[0].cost_price == 1000
    assert positions[0].current_price == 1200


def test_ignores_ths_app_header_with_time() -> None:
    positions = parse_position_text_lines(["同花顺App 20:07 三", "同花顺自选", "上证指数+1.78%"])

    assert positions == []


def test_parses_ths_watchlist_rows_without_quantity_or_cost() -> None:
    positions = parse_position_text_lines(
        [
            "同花顺App",
            "20:07",
            "同花顺自选",
            "4163.10+72.62",
            "上证指数+1.78%▼",
            "自选股",
            "持仓股",
            "汇总持仓",
            "最新",
            "涨幅",
            "士兰微",
            "44.80",
            "+7.10%",
            "2.",
            "600460融",
            "通裕重工",
            "3.01",
            "+8.27%",
            "0.",
            "创 300185融",
            "方正科技",
            "14.05",
            "-2.43%",
            "-0.",
            "600601融",
            "紫金矿业",
            "30.44",
            "+2.53%",
            "0.",
            "601899融",
            "协鑫集成",
            "3.11",
            "+1.30%",
            "0.",
            "002506融",
            "峰璟股份",
            "3.96",
            "+3.66%",
            "0.",
            "002662融",
            "中能电气",
            "6.20",
            "+1.97%",
            "0.",
            "创 300062",
            "联建光电",
            "4.98",
            "+2.05%",
            "0.",
            "创 300269",
            "ST洲际",
            "2.22",
            "-3.48%",
            "-0.",
            "600759",
            "南京熊猫",
            "10.44",
            "-1.42%",
            "-0.",
            "600775融",
        ]
    )

    assert [item.symbol for item in positions] == [
        "600460.SH",
        "300185.SZ",
        "600601.SH",
        "601899.SH",
        "002506.SZ",
        "002662.SZ",
        "300062.SZ",
        "300269.SZ",
        "600759.SH",
        "600775.SH",
    ]
    assert positions[0].name == "士兰微"
    assert positions[0].quantity == 0
    assert positions[0].cost_price == 44.8
    assert positions[0].current_price == 44.8
    assert positions[0].raw_fields["识别类型"] == "自选/行情列表"
    assert positions[1].name == "通裕重工"
    assert positions[1].current_price == 3.01


def test_parses_ai_position_json_payload() -> None:
    positions = parse_ai_position_payload(
        json.dumps(
            {
                "positions": [
                    {
                        "symbol": "600519",
                        "name": "贵州茅台",
                        "market": "CN",
                        "quantity": 10,
                        "cost_price": 1000,
                        "current_price": 1200,
                    },
                    {
                        "symbol": "00700",
                        "name": "腾讯控股",
                        "market": "HK",
                        "quantity": 20,
                        "cost_price": 300,
                        "current_price": 250,
                    },
                ]
            },
            ensure_ascii=False,
        )
    )

    assert positions[0].symbol == "600519.SH"
    assert positions[0].currency == "CNY"
    assert positions[1].symbol == "00700.HK"
    assert positions[1].currency == "HKD"


def test_parses_ai_position_payload_with_chinese_keys() -> None:
    positions = parse_ai_position_payload(
        json.dumps(
            {
                "持仓列表": [
                    {
                        "股票代码": "600519",
                        "股票名称": "贵州茅台",
                        "市场": "A股",
                        "持仓数量": "10",
                        "成本价": "1,000.00",
                        "现价": "1,200.00",
                    },
                    {
                        "证券代码": 700,
                        "证券名称": "腾讯控股",
                        "市场": "港股",
                        "数量": 20,
                        "成本": 300,
                        "当前价": 250,
                    },
                ]
            },
            ensure_ascii=False,
        )
    )

    assert positions[0].symbol == "600519.SH"
    assert positions[0].name == "贵州茅台"
    assert positions[0].quantity == 10
    assert positions[0].cost_price == 1000
    assert positions[0].current_price == 1200
    assert positions[1].symbol == "00700.HK"
    assert positions[1].name == "腾讯控股"


def test_parses_ai_markdown_table_payload() -> None:
    positions = parse_ai_position_payload(
        """
| 代码 | 名称 | 市场 | 持仓数量 | 成本价 | 最新价 |
| --- | --- | --- | ---: | ---: | ---: |
| 600519 | 贵州茅台 | A股 | 10 | 1,000.00 | 1,200.00 |
| 00700 | 腾讯控股 | 港股 | 20 | 300.00 | 250.00 |
"""
    )

    assert [item.symbol for item in positions] == ["600519.SH", "00700.HK"]
    assert positions[0].name == "贵州茅台"
    assert positions[0].quantity == 10
    assert positions[1].market == "HK"


def test_parses_nested_ai_payload_with_broker_field_aliases_and_derived_prices() -> None:
    positions = parse_ai_position_payload(
        json.dumps(
            {
                "result": {
                    "rows": [
                        {
                            "证券代码": "600519",
                            "证券名称": "贵州茅台",
                            "交易市场": "沪A",
                            "股份余额": "10",
                            "成本金额": "10,000.00",
                            "参考市值": "12,000.00",
                        }
                    ]
                }
            },
            ensure_ascii=False,
        )
    )

    assert positions == [
        PortfolioPosition(
            symbol="600519.SH",
            name="贵州茅台",
            market="CN",
            quantity=10,
                cost_price=1000,
                current_price=1200,
                currency="CNY",
                market_value=12000,
                cost_value=10000,
                source="ocr",
            )
        ]


def test_parses_ths_ai_payload_with_full_position_fields() -> None:
    positions = parse_ai_position_payload(
        json.dumps(
            {
                "positions": [
                    {
                        "证券代码": "600519",
                        "证券名称": "贵州茅台",
                        "持仓数量": "10",
                        "可用数量": "8",
                        "成本金额": "10,000.00",
                        "参考市值": "12,000.00",
                        "浮动盈亏": "2,000.00",
                        "盈亏比例": "20.00%",
                        "同花顺备注": "融资持仓",
                    }
                ]
            },
            ensure_ascii=False,
        )
    )

    assert positions[0].symbol == "600519.SH"
    assert positions[0].quantity == 10
    assert positions[0].available_quantity == 8
    assert positions[0].cost_price == 1000
    assert positions[0].current_price == 1200
    assert positions[0].cost_value == 10000
    assert positions[0].market_value == 12000
    assert positions[0].pnl == 2000
    assert positions[0].pnl_pct == 0.2
    assert positions[0].source == "ocr"
    assert positions[0].raw_fields == {"同花顺备注": "融资持仓"}


def test_parses_ths_fragmented_holding_block_with_market_value_and_pnl() -> None:
    positions = parse_position_text_lines(
        [
            "同花顺App",
            "持仓",
            "可用",
            "成本",
            "现价",
            "市值",
            "盈亏",
            "盈亏率",
            "贵州茅台",
            "600519",
            "10",
            "8",
            "1000.00",
            "1200.00",
            "12000.00",
            "2000.00",
            "20.00%",
        ]
    )

    assert positions[0].symbol == "600519.SH"
    assert positions[0].available_quantity == 8
    assert positions[0].market_value == 12000
    assert positions[0].pnl == 2000
    assert positions[0].pnl_pct == 0.2


def test_parses_zhongtai_broker_holding_page_with_summary_and_name_lookup() -> None:
    result = parse_ocr_text_result(
        [
            "中泰证券",
            "**0221",
            "买入",
            "卖出",
            "撤单",
            "持仓",
            "查询",
            "人民币账户 CNY A股",
            "仓位 88.2%",
            "总资产",
            "35,469.43",
            "总盈亏",
            "-8,182.58",
            "当日参考盈亏",
            "-1,073.00 -2.94%",
            "总市值",
            "31,290.00",
            "可用",
            "4,179.43",
            "可取",
            "4,179.37",
            "持仓股",
            "市值",
            "盈亏",
            "持仓/可用",
            "成本/现价",
            "通裕重工",
            "11,480.00",
            "-7,198.78",
            "-38.544%",
            "4000",
            "4000",
            "4.670",
            "2.870",
            "亨通股份",
            "8,280.00",
            "-1,089.09",
            "-11.623%",
            "900",
            "900",
            "10.410",
            "9.200",
            "赛腾股份",
            "6,805.00",
            "-655.07",
            "-8.781%",
            "100",
            "100",
            "74.601",
            "68.050",
            "士兰微",
            "4,725.00",
            "760.36",
            "19.180%",
            "100",
            "100",
            "39.646",
            "47.250",
            "查看已清仓股票",
        ],
        akshare_module=FakeAshareNames(
            [
                {"code": "300185", "name": "通裕重工"},
                {"code": "600226", "name": "亨通股份"},
                {"code": "603283", "name": "赛腾股份"},
                {"code": "600460", "name": "士兰微"},
            ]
        ),
    )

    assert result.portfolio_summary is not None
    assert result.portfolio_summary["total_assets"] == 35469.43
    assert result.portfolio_summary["total_pnl"] == -8182.58
    assert result.portfolio_summary["day_pnl"] == -1073.00
    assert result.portfolio_summary["day_pnl_pct"] == -0.0294
    assert result.portfolio_summary["market_value"] == 31290.00
    assert result.portfolio_summary["available_cash"] == 4179.43
    assert result.portfolio_summary["withdrawable_cash"] == 4179.37
    assert result.portfolio_summary["position_ratio"] == 0.882
    assert result.unmatched_rows == []
    assert [item.symbol for item in result.positions] == ["300185.SZ", "600226.SH", "603283.SH", "600460.SH"]
    first = result.positions[0]
    assert first.name == "通裕重工"
    assert first.quantity == 4000
    assert first.available_quantity == 4000
    assert first.cost_price == 4.67
    assert first.current_price == 2.87
    assert first.market_value == 11480
    assert first.pnl == -7198.78
    assert first.pnl_pct == -0.38544
    assert first.raw_fields["代码来源"] == "A股名称精确匹配"


def test_broker_holding_name_lookup_requires_unique_exact_match() -> None:
    result = parse_ocr_text_result(
        [
            "持仓股",
            "市值",
            "盈亏",
            "持仓/可用",
            "成本/现价",
            "同名股份",
            "1,000.00",
            "10.00",
            "1.00%",
            "100",
            "100",
            "9.90",
            "10.00",
            "未知股份",
            "2,000.00",
            "-20.00",
            "-1.00%",
            "200",
            "200",
            "10.10",
            "10.00",
        ],
        akshare_module=FakeAshareNames(
            [
                {"code": "600001", "name": "同名股份"},
                {"code": "000001", "name": "同名股份"},
            ]
        ),
    )

    assert result.positions == []
    assert [row["name"] for row in result.unmatched_rows] == ["同名股份", "未知股份"]
    assert result.unmatched_rows[0]["reason"] == "股票名称不是唯一精确匹配"
    assert result.unmatched_rows[1]["reason"] == "股票名称未匹配 A 股代码"


def test_global_index_cards_are_not_imported_as_positions() -> None:
    result = parse_ocr_text_result(
        [
            "全球指数",
            "000001.SH",
            "上证指数",
            "4,043.64",
            "+0.37%",
            "免费公开源，可能延迟、缺失或被缓存",
            "399001.SZ",
            "深证成指",
            "15,597.51",
            "+0.64%",
            "399006.SZ",
            "创业板指",
            "4,019.93",
            "+0.07%",
            "DJI",
            "52,900.07",
            "SPX",
            "7,483.24",
            "NDX",
            "29,329.21",
        ],
        akshare_module=FakeAshareNames([]),
    )

    assert result.positions == []
    assert result.portfolio_summary is None
    assert result.unmatched_rows == []


def test_falls_back_to_text_lines_when_json_has_no_position_container() -> None:
    positions = parse_ai_position_payload(
        json.dumps(
            {"message": "识别结果如下：\n贵州茅台 600519 持仓 10 成本 1000.00 现价 1200.00"},
            ensure_ascii=False,
        )
    )

    assert positions[0].symbol == "600519.SH"
    assert positions[0].quantity == 10


def test_unparseable_ai_payload_returns_empty_positions() -> None:
    assert parse_ai_position_payload("未识别到券商持仓表格") == []


async def test_doubao_vision_service_sends_image_and_parses_positions() -> None:
    captured_payload: dict | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "positions": [
                                        {
                                            "symbol": "AAPL",
                                            "name": "Apple",
                                            "market": "US",
                                            "quantity": 3,
                                            "cost_price": 180,
                                            "current_price": 200,
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    service = DoubaoVisionOcrService(
        api_key="test-key",
        api_base="https://ark.test/api/v3",
        model="doubao-seed-2-0-lite-260215",
        transport=httpx.MockTransport(handler),
    )

    status, positions, raw_lines = await service.recognize_positions(b"png-bytes")

    assert status == "completed"
    assert positions == [
        PortfolioPosition(
            symbol="AAPL",
            name="Apple",
            market="US",
            quantity=3,
            cost_price=180,
            current_price=200,
            currency="USD",
            source="ocr",
        )
    ]
    assert raw_lines
    assert captured_payload is not None
    assert captured_payload["model"] == "doubao-seed-2-0-lite-260215"
    assert "券商持仓" in captured_payload["messages"][0]["content"]
    content = captured_payload["messages"][1]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


async def test_doubao_vision_service_uses_uploaded_image_mime_type() -> None:
    captured_payload: dict | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"positions": []}, ensure_ascii=False),
                        }
                    }
                ]
            },
        )

    service = DoubaoVisionOcrService(
        api_key="test-key",
        api_base="https://ark.test/api/v3",
        model="doubao-seed-2-0-lite-260215",
        transport=httpx.MockTransport(handler),
    )

    await service.recognize_positions(b"jpg-bytes", "image/jpeg")

    assert captured_payload is not None
    content = captured_payload["messages"][1]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


async def test_doubao_vision_service_reports_unavailable_when_api_key_missing_and_fallback_fails() -> None:
    class FailedFallback:
        async def recognize_lines(self, image_bytes: bytes):
            return "failed", []

    service = DoubaoVisionOcrService(
        api_key="",
        api_base="https://ark.test/api/v3",
        model="doubao-seed-2-0-lite-260215",
        fallback=FailedFallback(),
    )

    status, positions, raw_lines = await service.recognize_positions(b"png-bytes")

    assert status == "unavailable"
    assert positions == []
    assert raw_lines == []
