from fastapi import APIRouter, File, Request, UploadFile

from app.schemas.ocr import OcrPositionsResponse
from app.services.ocr import (
    DoubaoVisionOcrService,
    has_watchlist_fallback_positions,
    no_position_message,
    parse_ocr_text_result,
    watchlist_position_message,
)

router = APIRouter(prefix="/api/ocr", tags=["ocr"])


@router.post("/positions", response_model=OcrPositionsResponse)
async def parse_positions(
    request: Request,
    file: UploadFile = File(...),
) -> OcrPositionsResponse:
    service: DoubaoVisionOcrService = request.app.state.ocr_service
    status, positions, lines = await service.recognize_positions(await file.read(), file.content_type or "image/png")
    parsed = parse_ocr_text_result(lines)
    portfolio_summary = parsed.portfolio_summary
    unmatched_rows = parsed.unmatched_rows
    if not positions and parsed.positions:
        positions = parsed.positions
    message = ""
    if status == "unavailable":
        message = "AI OCR 未配置，请在后端环境变量中设置 VOLCENGINE_API_KEY。"
    elif status == "failed":
        message = "AI OCR 调用失败，请检查火山方舟 API Key、模型开通状态、网络或图片格式。"
    elif positions and has_watchlist_fallback_positions(positions):
        message = watchlist_position_message(positions)
    elif portfolio_summary or unmatched_rows:
        message = f"已识别券商持仓页，导入 {len(positions)} 条持仓"
        if unmatched_rows:
            message += f"，{len(unmatched_rows)} 行待确认"
        message += "。"
    elif not positions:
        message = no_position_message(lines)
    return OcrPositionsResponse(
        status=status,
        positions=positions,
        raw_lines=lines,
        message=message,
        portfolio_summary=portfolio_summary,
        unmatched_rows=unmatched_rows,
    )
