"""兼容 DeepSeek 与 DashScope 的对话模型客户端。"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.core.config import get_settings


class LLMNotConfiguredError(RuntimeError):
    """当前对话模型缺少必要配置。"""


def create_chat_model() -> ChatOpenAI:
    """按当前提供方创建 OpenAI 兼容的对话模型。"""

    settings = get_settings()
    api_key = settings.effective_chat_api_key
    if api_key is None or not settings.effective_chat_base_url:
        raise LLMNotConfiguredError("对话模型 API 尚未配置")

    return ChatOpenAI(
        model=settings.effective_chat_model,
        api_key=api_key,
        base_url=settings.effective_chat_base_url,
        temperature=0,
        max_retries=0,
        timeout=settings.chat_request_timeout_seconds,
    )
