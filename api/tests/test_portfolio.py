from app.schemas.portfolio import PortfolioPosition
from app.services.portfolio import analyze_portfolio


def test_analyzes_total_pnl_weights_and_concentration_risk() -> None:
    result = analyze_portfolio(
        [
            PortfolioPosition(
                symbol="600519.SH",
                name="贵州茅台",
                market="CN",
                quantity=10,
                cost_price=1000,
                current_price=1200,
                currency="CNY",
            ),
            PortfolioPosition(
                symbol="00700.HK",
                name="腾讯控股",
                market="HK",
                quantity=20,
                cost_price=300,
                current_price=250,
                currency="HKD",
            ),
        ]
    )

    assert result.total_value == 17000
    assert result.pnl == 1000
    assert result.positions[0].market_value == 12000
    assert result.positions[0].pnl_pct == 0.2
    assert result.weights[0].symbol == "600519.SH"
    assert round(result.weights[0].weight, 4) == 0.7059
    assert result.risks[0].level == "high"


def test_empty_portfolio_returns_zero_snapshot() -> None:
    result = analyze_portfolio([])

    assert result.total_value == 0
    assert result.pnl == 0
    assert result.positions == []
    assert result.weights == []
    assert result.risks == []
