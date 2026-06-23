from pydantic import BaseModel, Field


class SourceKeyStatus(BaseModel):
    name: str
    configured: bool
    detail: str = ""


class SourceCacheStatus(BaseModel):
    path: str
    exists: bool
    writable: bool
    detail: str = ""


class FreeDataSource(BaseModel):
    name: str
    category: str
    source: str
    detail: str = ""


class SourcesStatusResponse(BaseModel):
    key_status: list[SourceKeyStatus] = Field(default_factory=list)
    cache: SourceCacheStatus
    free_data_sources: list[FreeDataSource] = Field(default_factory=list)
    disclaimer: str
