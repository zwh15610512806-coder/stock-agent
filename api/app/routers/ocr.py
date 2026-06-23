from fastapi import APIRouter, File, Request, UploadFile

from app.schemas.ocr import OcrPositionsResponse
from app.services.ocr import DoubaoVisionOcrService

router = APIRouter(prefix="/api/ocr", tags=["ocr"])


@router.post("/positions", response_model=OcrPositionsResponse)
async def parse_positions(
    request: Request,
    file: UploadFile = File(...),
) -> OcrPositionsResponse:
    service: DoubaoVisionOcrService = request.app.state.ocr_service
    status, positions, lines = await service.recognize_positions(await file.read(), file.content_type or "image/png")
    message = ""
    if status == "unavailable":
        message = "AI OCR 未配置，请在后端环境变量中设置 VOLCENGINE_API_KEY。"
    elif status == "failed":
        message = "AI OCR 调用失败，请检查火山方舟 API Key、模型开通状态、网络或图片格式。"
    elif not positions:
        message = "AI 已返回识别结果，但未提取到可用持仓行。"
    return OcrPositionsResponse(status=status, positions=positions, raw_lines=lines, message=message)
