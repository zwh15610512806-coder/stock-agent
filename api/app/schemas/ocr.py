from pydantic import BaseModel

from app.schemas.portfolio import PortfolioPosition


class OcrPositionsResponse(BaseModel):
    status: str
    positions: list[PortfolioPosition]
    raw_lines: list[str]
    message: str = ""
