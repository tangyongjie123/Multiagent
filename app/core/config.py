"""应用配置。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """从环境变量和本地 `.env` 读取的配置。"""

    app_name: str = "MultiAgent Software Studio"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"
    frontend_origin: str = "http://localhost:5173"
    agent_execution_mode: Literal["simulation", "live"] = "simulation"
    chat_provider: Literal["deepseek", "dashscope"] = "deepseek"
    auto_create_tables: bool = True

    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_pro_model: str = "deepseek-v4-pro"

    embedding_provider: str = "openai-compatible"
    embedding_api_key: SecretStr | None = None
    embedding_base_url: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = Field(default=None, ge=1)
    dashscope_api_key: SecretStr | None = None
    dashscope_base_url: str | None = None
    dashscope_chat_model: str = "qwen3.8-flash"
    dashscope_embedding_model: str = "qwen3.7-text-embedding"
    dashscope_embedding_dimension: int = Field(default=1024, ge=1)

    rerank_api_key: SecretStr | None = None
    rerank_base_url: str | None = None
    rerank_model: str | None = None

    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "multiagent"
    postgres_user: str = "multiagent"
    postgres_password: SecretStr | None = None

    milvus_uri: str | None = None
    milvus_user: str | None = None
    milvus_password: SecretStr | None = None
    milvus_token: SecretStr | None = None
    milvus_database: str = "default"
    milvus_top_k: int = Field(default=8, ge=1, le=50)

    neo4j_uri: str | None = None
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr | None = None

    run_token_budget: int = Field(default=200_000, gt=0)
    max_repair_attempts: int = Field(default=3, ge=0, le=10)

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]

    @property
    def deepseek_configured(self) -> bool:
        return _has_real_secret(self.deepseek_api_key)

    @property
    def embedding_configured(self) -> bool:
        return bool(self.effective_embedding_api_key) and bool(
            self.effective_embedding_base_url
        ) and bool(self.effective_embedding_model)

    @property
    def effective_embedding_api_key(self) -> SecretStr | None:
        if _has_real_secret(self.embedding_api_key):
            return self.embedding_api_key
        if _has_real_secret(self.dashscope_api_key):
            return self.dashscope_api_key
        return None

    @property
    def effective_embedding_base_url(self) -> str | None:
        return self.embedding_base_url or self.dashscope_base_url

    @property
    def effective_embedding_model(self) -> str | None:
        return self.embedding_model or self.dashscope_embedding_model

    @property
    def effective_embedding_dimension(self) -> int:
        return self.embedding_dimension or self.dashscope_embedding_dimension

    @property
    def effective_chat_api_key(self) -> SecretStr | None:
        if self.chat_provider == "dashscope":
            return self.dashscope_api_key
        return self.deepseek_api_key

    @property
    def effective_chat_base_url(self) -> str | None:
        if self.chat_provider == "dashscope":
            return self.dashscope_base_url
        return self.deepseek_base_url

    @property
    def effective_chat_model(self) -> str:
        if self.chat_provider == "dashscope":
            return self.dashscope_chat_model
        return self.deepseek_model

    @property
    def llm_configured(self) -> bool:
        return bool(self.effective_chat_api_key) and bool(
            self.effective_chat_base_url
        )

    @property
    def postgres_configured(self) -> bool:
        return _has_real_secret(self.postgres_password)

    @property
    def postgres_async_dsn(self) -> str | None:
        if not self.postgres_configured or self.postgres_password is None:
            return None
        password = quote_plus(self.postgres_password.get_secret_value())
        user = quote_plus(self.postgres_user)
        database = quote_plus(self.postgres_db)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{database}"
        )

    @property
    def postgres_libpq_dsn(self) -> str | None:
        if not self.postgres_configured or self.postgres_password is None:
            return None
        password = quote_plus(self.postgres_password.get_secret_value())
        user = quote_plus(self.postgres_user)
        database = quote_plus(self.postgres_db)
        return (
            f"postgresql://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{database}"
        )

    @property
    def milvus_configured(self) -> bool:
        return (
            bool(self.milvus_uri)
            and "replace-with" not in str(self.milvus_uri)
            and bool(self.milvus_user)
            and _has_real_secret(self.milvus_password)
        )

    @property
    def neo4j_configured(self) -> bool:
        uri = self.neo4j_uri
        return (
            uri is not None
            and "replace-with" not in uri
            and _has_real_secret(self.neo4j_password)
        )


def _has_real_secret(secret: SecretStr | None) -> bool:
    if secret is None:
        return False
    value = secret.get_secret_value().strip()
    return bool(value) and "replace-with" not in value


@lru_cache
def get_settings() -> Settings:
    """返回进程级配置单例。"""

    return Settings()
