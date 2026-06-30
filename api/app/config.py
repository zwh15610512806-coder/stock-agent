from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "息壤投研 API"
    environment: str = "local"
    deepseek_api_key: str = ""
    deepseek_api_base: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    openai_api_key: str = ""
    news_search_api_key: str = ""
    news_search_api_base: str = "https://api.openai.com/v1"
    news_search_model: str = "gpt-4.1-mini"
    news_search_timeout_seconds: float = 8.0
    dashboard_source_timeout_seconds: float = 8.0
    dashboard_slow_source_timeout_seconds: float = 12.0
    dashboard_optional_source_timeout_seconds: float = 6.0
    volcengine_api_key: str = ""
    volcengine_api_base: str = "https://ark.cn-beijing.volces.com/api/v3"
    volcengine_ocr_model: str = "doubao-seed-2-0-lite-260215"
    market_cache_ttl_seconds: int = 90
    macro_data_provider: str = "hybrid"
    danginvest_base_url: str = "https://dang-invest.com"
    danginvest_timeout_seconds: float = 8.0
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
