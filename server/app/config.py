from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SmartSupport Agent API"
    app_env: str = "development"
    web_origin: str = "http://localhost:5173"
    knowledge_base_path: Path = Path("knowledge-base")
    database_url: str = "postgresql+psycopg://smart_support:smart_support_dev@127.0.0.1:5432/smart_support"
    upload_dir: Path = Path("data/uploads")
    max_upload_mb: int = 10
    embedding_mode: str = "local"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = 512
    knowledge_gap_similarity_threshold: float = 0.82
    knowledge_gap_backfill_limit: int = 200
    auth_secret: str = "smart-support-local-development-secret-2026"
    auth_token_minutes: int = 480
    requests_per_minute: int = 600
    chat_requests_per_minute: int = 30
    off_topic_max_consecutive_questions: int = 3
    off_topic_window_seconds: int = 1800
    redis_url: str = ""
    llm_mode: str = "mock"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout_seconds: float = 30.0
    intent_router_min_confidence: float = 0.65

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def psycopg_database_url(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
