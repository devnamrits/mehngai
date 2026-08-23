from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "mehngai"
    environment: str = "development"

    database_url: str = "sqlite:///./mehngai.db"
    brightdata_api_key: str = ""
    brightdata_api_base: str = "https://api.brightdata.com"

    collector_ids: str = ""

    pipeline_token: str = "change-me"
    cors_origins: str = "*"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    ai_base_url: str = ""
    ai_model: str = "llama3.2"
    ai_api_key: str = ""

    mock_mode: bool = False
    mock_fail_collector: str = ""

    null_ratio_threshold: float = 0.4
    price_outlier_multiplier: float = 10.0

    @property
    def collectors(self) -> list[str]:
        return [c.strip() for c in self.collector_ids.split(",") if c.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
