"""在证据进入模型、事件或报告前移除常见敏感值。"""

from __future__ import annotations

import re

SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b([a-z0-9_]*(?:api[_-]?key|secret(?:_key)?|token|"
    r"password|passwd|pwd|credential)[a-z0-9_]*)\b"
    r"\s*[:=]\s*[\"']?([^\s\"',;]{6,})"
)
PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN ([A-Z ]*PRIVATE KEY)-----.*?-----END \1-----",
    re.DOTALL,
)
URL_CREDENTIALS = re.compile(r"(https?://[^/\s:@]+):([^@\s/]+)@")


def redact_sensitive_text(content: str) -> str:
    """替换常见凭证赋值、URL 密码和私钥正文。"""

    redacted = PRIVATE_KEY_BLOCK.sub("[REDACTED PRIVATE KEY]", content)
    redacted = SECRET_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}=<REDACTED>",
        redacted,
    )
    return URL_CREDENTIALS.sub(r"\1:<REDACTED>@", redacted)
