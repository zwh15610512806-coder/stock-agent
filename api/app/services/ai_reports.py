import json

import httpx

from app.schemas.ai import AiReportRequest, AiReportResponse, AiReportSection
from app.services.portfolio import DISCLAIMER

STANDARD_REPORT_PROMPT = (
    "请基于以下 JSON 生成中文研究报告，包含：结论摘要、趋势与量价、组合暴露、"
    "主要风险、后续观察指标。不要给出确定性买卖指令或承诺收益。"
)

SERENITY_SKILL_PROMPT = (
    "已启用 serenity-skill 分析模式。请按 serenity-skill / guizang-ppt-skill 的报告分析方式组织输出："
    "把研究结论整理成可直接转为横向网页 PPT 的结构，优先采用数据汇报和瑞士国际主义风格；"
    "先给一句封面级核心判断，再给 3-5 个页面级要点，每个要点包含标题、关键证据、可视化建议和讲述重点；"
    "最后输出风险页和观察清单。保持短句、强结构、可投屏，不堆砌长段落；仍然不得给出确定性买卖指令或承诺收益。"
)


class DeepSeekReportService:
    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model

    async def generate(self, request: AiReportRequest) -> AiReportResponse:
        if not self.api_key:
            return AiReportResponse(
                status="unavailable",
                symbol=request.symbol,
                market=request.market,
                summary="DeepSeek 未配置：请在后端环境变量中设置 DEEPSEEK_API_KEY 后再生成 AI 研究报告。",
                sections=[
                    AiReportSection(
                        title="数据解读",
                        body="当前仅展示行情和组合的规则化分析；AI 研究报告需要后端持有 DeepSeek API Key。",
                    )
                ],
                watch_metrics=["价格趋势", "成交量变化", "组合权重", "新闻与公告"],
                risks=["免费行情可能延迟或缺失", "AI 输出需要人工复核"],
                model=self.model,
                metadata=self._build_metadata(request, "unavailable"),
                disclaimer=DISCLAIMER,
            )
        try:
            return await self._generate_with_deepseek(request)
        except Exception as exc:
            return AiReportResponse(
                status="failed",
                symbol=request.symbol,
                market=request.market,
                summary=f"DeepSeek 报告生成失败：{exc}",
                sections=[],
                watch_metrics=["稍后重试", "检查后端网络与 API Key"],
                risks=["模型服务不可用时不要依据缺失报告做判断"],
                model=self.model,
                metadata=self._build_metadata(request, "failed"),
                disclaimer=DISCLAIMER,
            )

    async def _generate_with_deepseek(self, request: AiReportRequest) -> AiReportResponse:
        prompt = self._build_prompt(request)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是谨慎的证券研究助理，只做研究分析，不提供承诺性买卖建议。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{self.api_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return AiReportResponse(
            status="completed",
            symbol=request.symbol,
            market=request.market,
            summary=content[:240],
            sections=[AiReportSection(title="DeepSeek 研究报告", body=content)],
            watch_metrics=["趋势结构", "成交量", "估值变化", "组合权重", "风险事件"],
            risks=["模型可能遗漏事实或误读延迟行情", "报告不构成证券买卖建议"],
            model=self.model,
            metadata=self._build_metadata(request, "deepseek"),
            disclaimer=DISCLAIMER,
        )

    def _build_prompt(self, request: AiReportRequest) -> str:
        quote = request.quote.model_dump(mode="json") if request.quote else None
        candles = [item.model_dump(mode="json") for item in request.candles[-40:]]
        positions = [item.model_dump(mode="json") for item in request.portfolio_positions]
        context = {
            "symbol": request.symbol,
            "market": request.market,
            "analysis_skill": request.analysis_skill,
            "horizon": request.horizon,
            "risk_profile": request.risk_profile,
            "quote": quote,
            "candles": candles,
            "portfolio_positions": positions,
        }
        instruction = STANDARD_REPORT_PROMPT
        if request.analysis_skill == "serenity":
            instruction = f"{STANDARD_REPORT_PROMPT}\n{SERENITY_SKILL_PROMPT}"
        return (
            f"{instruction}\n"
            + json.dumps(context, ensure_ascii=False)
        )

    def _build_metadata(self, request: AiReportRequest, source: str) -> dict[str, str]:
        metadata = {
            "source": source,
            "analysis_skill": request.analysis_skill,
        }
        if request.analysis_skill == "serenity":
            metadata["skill_label"] = "serenity-skill"
        return metadata
