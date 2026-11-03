"""不执行项目代码的确定性安全与质量检查。"""

from __future__ import annotations

import re

from app.domain.models import (
    Finding,
    FindingCategory,
    FindingSeverity,
)
from app.services.repository import RepositorySnapshot

# 这些规则只用于提示风险，不能替代编译器、类型系统或专业 SAST。
SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*[\"']?([^\s\"']{6,})"
)
PRIVATE_KEY_PATTERN = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
EMPTY_CATCH_PATTERN = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}", re.DOTALL)
COMMAND_PATTERN = re.compile(r"Runtime\.getRuntime\(\)\.exec|new\s+ProcessBuilder\s*\(")
SYSTEM_OUT_PATTERN = re.compile(r"System\.out\.print")
TODO_PATTERN = re.compile(r"TODO|FIXME")


def run_static_analysis(snapshot: RepositorySnapshot) -> list[Finding]:
    """运行确定性密钥、危险模式和基础质量规则。"""

    findings: list[Finding] = []
    for path, content in snapshot.source_files.items():
        # 安全规则：可能泄露凭证的内容只记录位置，不在证据中复制真实值。
        secret_match = SECRET_PATTERN.search(content) or PRIVATE_KEY_PATTERN.search(content)
        if secret_match:
            findings.append(
                Finding(
                    category=FindingCategory.SECURITY,
                    severity=FindingSeverity.CRITICAL,
                    title="代码中可能包含敏感凭证",
                    file_path=path,
                    line=_line_number(content, secret_match.start()),
                    evidence="检测到密钥、Token、密码或私钥特征。",
                    impact="凭证可能泄露并导致仓库或服务被未授权访问。",
                    recommendation="立即撤销凭证，改用环境变量或 Secret 管理。",
                )
            )
        # 命令执行本身不一定有漏洞，需结合参数来源由模型进一步判断。
        command_match = COMMAND_PATTERN.search(content)
        if command_match:
            findings.append(
                Finding(
                    category=FindingCategory.SECURITY,
                    severity=FindingSeverity.MAJOR,
                    title="发现系统命令执行调用",
                    file_path=path,
                    line=_line_number(content, command_match.start()),
                    evidence="代码包含 Runtime.exec 或 ProcessBuilder。",
                    impact="若参数来自外部输入，可能形成命令注入风险。",
                    recommendation="限制允许命令，避免拼接外部参数，并在沙箱中运行。",
                )
            )
        # 质量规则：空 catch 和标准输出通常是可直接验证的工程问题。
        catch_match = EMPTY_CATCH_PATTERN.search(content)
        if catch_match:
            findings.append(
                Finding(
                    category=FindingCategory.QUALITY,
                    severity=FindingSeverity.MAJOR,
                    title="存在空的异常处理块",
                    file_path=path,
                    line=_line_number(content, catch_match.start()),
                    evidence="检测到空 catch 代码块。",
                    impact="异常会被静默吞掉，增加排障和状态不一致风险。",
                    recommendation="记录日志、转换为业务异常或向上抛出。",
                )
            )
        system_out_match = SYSTEM_OUT_PATTERN.search(content)
        if system_out_match:
            findings.append(
                Finding(
                    category=FindingCategory.QUALITY,
                    severity=FindingSeverity.MINOR,
                    title="使用标准输出代替日志框架",
                    file_path=path,
                    line=_line_number(content, system_out_match.start()),
                    evidence="检测到 System.out.print。",
                    impact="生产环境缺少结构化日志和日志级别控制。",
                    recommendation="改用 SLF4J 或项目统一日志组件。",
                )
            )
        # 每个 TODO/FIXME 单独保留行号，方便前端直接定位。
        for todo_match in TODO_PATTERN.finditer(content):
            findings.append(
                Finding(
                    category=FindingCategory.QUALITY,
                    severity=FindingSeverity.INFO,
                    title="代码中存在未完成标记",
                    file_path=path,
                    line=_line_number(content, todo_match.start()),
                    evidence=f"检测到 {todo_match.group(0)} 标记。",
                    impact="可能表示未完成实现或已知遗留问题。",
                    recommendation="逐项确认并建立可跟踪任务。",
                )
            )
    return findings


def _line_number(content: str, offset: int) -> int:
    """把字符偏移转换为从 1 开始的行号。"""

    return content.count("\n", 0, offset) + 1
