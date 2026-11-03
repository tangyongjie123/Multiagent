"""配置回退逻辑测试。"""

import os
from pathlib import Path

import pytest
from pydantic import SecretStr

import app.core.config as config_module
from app.core.config import Settings


def test_dashscope_embedding_fallback() -> None:
    """未设置通用 Embedding 配置时使用 DashScope 配置。"""

    settings = Settings(
        dashscope_api_key=SecretStr("test-key"),
        dashscope_base_url="https://example.invalid/v1",
        dashscope_embedding_model="qwen3.7-text-embedding",
        dashscope_embedding_dimension=1024,
    )

    assert settings.embedding_configured is True
    assert settings.effective_embedding_model == "qwen3.7-text-embedding"
    assert settings.effective_embedding_dimension == 1024


def test_dashscope_chat_provider() -> None:
    """可以显式选择 DashScope 作为对话模型提供方。"""

    settings = Settings(
        chat_provider="dashscope",
        dashscope_api_key=SecretStr("test-key"),
        dashscope_base_url="https://example.invalid/v1",
        dashscope_chat_model="qwen3.8-flash",
    )

    assert settings.llm_configured is True
    assert settings.effective_chat_model == "qwen3.8-flash"
    assert settings.effective_chat_base_url == "https://example.invalid/v1"


def test_local_env_file_overrides_process_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_env = tmp_path / ".env.local"
    local_env.write_text(
        "REPOGRAPH_LOCAL_OVERRIDE=local-value\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REPOGRAPH_LOCAL_OVERRIDE", "process-value")
    monkeypatch.setattr(config_module, "LOCAL_ENV_PATH", local_env)

    config_module._apply_local_env_overrides()

    assert os.environ["REPOGRAPH_LOCAL_OVERRIDE"] == "local-value"
