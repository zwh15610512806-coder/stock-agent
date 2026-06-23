import pytest

from app.schemas.ai import AiReportRequest
from app.services.ai_reports import DeepSeekReportService


@pytest.mark.asyncio
async def test_deepseek_report_returns_unavailable_without_key() -> None:
    service = DeepSeekReportService(api_key="")

    report = await service.generate(
        AiReportRequest(
            symbol="600519.SH",
            market="CN",
            horizon="中短线波段",
            risk_profile="稳健",
            quote=None,
            candles=[],
            portfolio_positions=[],
        )
    )

    assert report.status == "unavailable"
    assert "DEEPSEEK_API_KEY" in report.summary
    assert report.metadata["analysis_skill"] == "standard"
    assert report.disclaimer == "仅供研究参考，不构成任何证券买卖建议。"


def test_deepseek_prompt_uses_serenity_skill_when_enabled() -> None:
    service = DeepSeekReportService(api_key="test-key")

    prompt = service._build_prompt(
        AiReportRequest(
            symbol="600519.SH",
            market="CN",
            analysis_skill="serenity",
            horizon="中短线波段",
            risk_profile="稳健",
            quote=None,
            candles=[],
            portfolio_positions=[],
        )
    )

    assert "serenity-skill" in prompt
    assert "横向网页 PPT" in prompt
    assert '"analysis_skill": "serenity"' in prompt


@pytest.mark.asyncio
async def test_deepseek_report_metadata_marks_serenity_skill_without_key() -> None:
    service = DeepSeekReportService(api_key="")

    report = await service.generate(
        AiReportRequest(
            symbol="600519.SH",
            market="CN",
            analysis_skill="serenity",
            horizon="中短线波段",
            risk_profile="稳健",
            quote=None,
            candles=[],
            portfolio_positions=[],
        )
    )

    assert report.status == "unavailable"
    assert report.metadata["analysis_skill"] == "serenity"
    assert report.metadata["skill_label"] == "serenity-skill"
