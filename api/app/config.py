from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "智投终端 API"
    environment: str = "local"
    deepseek_api_key: str = ""
    deepseek_api_base: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    volcengine_api_key: str = ""
    volcengine_api_base: str = "https://ark.cn-beijing.volces.com/api/v3"
    volcengine_ocr_model: str = "doubao-seed-2-0-lite-260215"
    market_cache_ttl_seconds: int = 90
    tencentcloud_secret_id: str = ""
    tencentcloud_secret_key: str = ""
    tencentcloud_region: str = "ap-guangzhou"
    tencentcloud_ocr_endpoint: str = "ocr.tencentcloudapi.com"

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
