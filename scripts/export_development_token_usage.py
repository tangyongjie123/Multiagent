#!/usr/bin/env python3
"""从 Codex 会话日志导出开发过程 Token 使用记录。"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")
SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password)\s*[:=]"
)
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def parse_args() -> argparse.Namespace:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-file",
        type=Path,
        action="append",
        help="Codex 会话 JSONL 文件，可重复指定；默认使用最新会话。",
    )
    parser.add_argument(
        "--sessions-root",
        type=Path,
        default=codex_home / "sessions",
        help="Codex sessions 根目录。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "docs" / "DEVELOPMENT_TOKEN_USAGE.md",
        help="Markdown 输出路径。",
    )
    parser.add_argument(
        "--pricing-file",
        type=Path,
        default=PROJECT_ROOT / "configs" / "model_pricing.json",
        help="模型价格配置 JSON。",
    )
    return parser.parse_args()


def latest_session_file(sessions_root: Path) -> Path:
    candidates = [
        path
        for path in sessions_root.rglob("*.jsonl")
        if not path.name.endswith(".bak")
    ]
    if not candidates:
        raise FileNotFoundError(f"未在 {sessions_root} 找到 Codex 会话日志")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} 不是有效 JSON") from exc
            if isinstance(record, dict):
                records.append(record)
    return records


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [extract_text(item) for item in content]
        return " ".join(part for part in parts if part)
    if isinstance(content, dict):
        for key in ("text", "content"):
            if key in content:
                return extract_text(content[key])
    return ""


def normalize_label(text: str, limit: int = 88) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if SENSITIVE_ASSIGNMENT.search(cleaned) or any(
        pattern.search(cleaned) for pattern in SENSITIVE_VALUE_PATTERNS
    ):
        return "包含敏感信息的请求（已脱敏）"
    cleaned = cleaned.replace("|", "\\|")
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1]}…"


def is_context_message(text: str) -> bool:
    prefix = text.lstrip()
    return prefix.startswith(("<environment_context>", "<app-context>"))


def format_time(value: Any) -> str:
    if isinstance(value, (int, float)):
        timestamp = datetime.fromtimestamp(value, tz=UTC)
        return timestamp.astimezone(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    if not isinstance(value, str) or not value:
        return "—"
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return value
    return timestamp.astimezone(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def format_number(value: Any) -> str:
    if not isinstance(value, int):
        return "—"
    return f"{value:,}"


def format_cost(value: Decimal | None, currency: str) -> str:
    if value is None:
        return "—"
    return f"{currency} {value.quantize(Decimal('0.000001')):,.6f}"


def compact_turn_id(turn_id: str) -> str:
    if len(turn_id) <= 13:
        return turn_id
    return f"{turn_id[:8]}…{turn_id[-4:]}"


def load_pricing(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source:
        pricing = json.load(source)
    if not isinstance(pricing, dict) or not isinstance(pricing.get("models"), dict):
        raise TypeError(f"{path} 缺少 models 价格配置")
    return pricing


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def resolve_model_pricing(
    model: str, pricing: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    for model_id, config in pricing["models"].items():
        aliases = config.get("aliases", [])
        if model == model_id or model in aliases:
            return model_id, config
    return None


def is_peak(timestamp: datetime, pricing: dict[str, Any]) -> bool:
    utc_time = timestamp.astimezone(UTC)
    if utc_time.weekday() not in pricing.get("peak_weekdays", [0, 1, 2, 3, 4]):
        return False
    hour = utc_time.hour + utc_time.minute / 60
    return any(start <= hour < end for start, end in pricing.get("peak_hours_utc", []))


def calculate_cost(
    usage_records: list[tuple[str, dict[str, Any]]],
    model: str,
    pricing: dict[str, Any],
) -> tuple[Decimal | None, str]:
    resolved = resolve_model_pricing(model, pricing)
    if resolved is None:
        return None, "价格未配置"

    _, model_config = resolved
    unit_tokens = Decimal(str(pricing["unit_tokens"]))
    total_cost = Decimal(0)
    periods: set[str] = set()
    unknown_period = False

    for timestamp_value, usage in usage_records:
        timestamp = parse_timestamp(timestamp_value)
        if timestamp is None:
            unknown_period = True
            period = model_config["off_peak"]
        else:
            peak = is_peak(timestamp, pricing)
            periods.add("峰时" if peak else "谷时")
            period = model_config["peak" if peak else "off_peak"]

        input_tokens = int(usage.get("input_tokens") or 0)
        cached_input_tokens = min(
            int(usage.get("cached_input_tokens") or 0), input_tokens
        )
        uncached_input_tokens = input_tokens - cached_input_tokens
        output_tokens = int(usage.get("output_tokens") or 0)

        total_cost += (
            Decimal(uncached_input_tokens)
            * Decimal(str(period["uncached_input_per_million"]))
            / unit_tokens
        )
        total_cost += (
            Decimal(cached_input_tokens)
            * Decimal(str(period["cached_input_per_million"]))
            / unit_tokens
        )
        total_cost += (
            Decimal(output_tokens)
            * Decimal(str(period["output_per_million"]))
            / unit_tokens
        )

    labels = sorted(periods)
    if unknown_period:
        labels.append("时间缺失按谷时")
    return total_cost, " / ".join(labels) if labels else "无计费调用"


def collect_turns(
    records: list[dict[str, Any]], pricing: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    task_starts: list[dict[str, Any]] = []
    task_complete_ids: set[str] = set()
    task_aborted_ids: set[str] = set()
    user_messages: list[tuple[int, str]] = []
    turn_models: dict[str, str] = {}
    latest_usage: dict[str, tuple[int, dict[str, Any]]] = {}
    response_usage: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    thread_usage: dict[str, Any] = {}

    for record in records:
        record_type = record.get("type")
        payload = record.get("payload") or {}
        ordinal = record.get("ordinal")
        payload_type = payload.get("type")

        if record_type == "event_msg" and payload_type == "task_started":
            task_starts.append(record)
        elif record_type == "event_msg" and payload_type == "task_complete":
            turn_id = payload.get("turn_id")
            if isinstance(turn_id, str):
                task_complete_ids.add(turn_id)
        elif record_type == "event_msg" and payload_type == "turn_aborted":
            turn_id = payload.get("turn_id")
            if isinstance(turn_id, str):
                task_aborted_ids.add(turn_id)
        elif record_type == "response_item" and payload_type == "message":
            if payload.get("role") == "user" and isinstance(ordinal, int):
                text = extract_text(payload.get("content"))
                if text and not is_context_message(text):
                    user_messages.append((ordinal, text))
        elif record_type == "turn_context":
            turn_id = payload.get("turn_id")
            if isinstance(turn_id, str):
                turn_models[turn_id] = str(payload.get("model") or "未记录")
        elif record_type == "token_usage_record":
            turn_id = payload.get("turn_id")
            usage = payload.get("turn_token_usage")
            response_token_usage = payload.get("usage")
            if isinstance(turn_id, str) and isinstance(response_token_usage, dict):
                timestamp = str(record.get("timestamp") or "")
                response_usage.setdefault(turn_id, []).append(
                    (timestamp, response_token_usage)
                )
            if (
                isinstance(turn_id, str)
                and isinstance(usage, dict)
                and isinstance(ordinal, int)
            ):
                previous = latest_usage.get(turn_id)
                if previous is None or ordinal > previous[0]:
                    latest_usage[turn_id] = (ordinal, usage)
            current_thread_usage = payload.get("thread_token_usage")
            if isinstance(current_thread_usage, dict):
                thread_usage = current_thread_usage

    task_starts.sort(key=lambda item: item.get("ordinal", 0))
    turns: list[dict[str, Any]] = []

    for index, record in enumerate(task_starts):
        payload = record.get("payload") or {}
        turn_id = str(payload.get("turn_id") or "")
        current_ordinal = record.get("ordinal", 0)
        next_ordinal = (
            task_starts[index + 1].get("ordinal", 10**12)
            if index + 1 < len(task_starts)
            else 10**12
        )
        matching_prompts = [
            text
            for ordinal, text in user_messages
            if isinstance(current_ordinal, int) and current_ordinal <= ordinal < next_ordinal
        ]
        label = normalize_label(matching_prompts[0]) if matching_prompts else "系统触发或未记录用户请求"
        usage_entry = latest_usage.get(turn_id)
        usage = usage_entry[1] if usage_entry else {}
        model = turn_models.get(turn_id, "未记录")
        estimated_cost, billing_period = calculate_cost(
            response_usage.get(turn_id, []), model, pricing
        )

        if turn_id in task_aborted_ids:
            status = "已中止"
        elif turn_id in task_complete_ids:
            status = "已完成"
        elif usage_entry:
            status = "进行中或快照未完成"
        else:
            status = "未记录用量"

        turns.append(
            {
                "turn_id": turn_id,
                "started_at": format_time(payload.get("started_at") or record.get("timestamp")),
                "label": label,
                "model": model,
                "input_tokens": usage.get("input_tokens"),
                "cached_input_tokens": usage.get("cached_input_tokens"),
                "cache_write_input_tokens": usage.get("cache_write_input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "reasoning_output_tokens": usage.get("reasoning_output_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "estimated_cost": estimated_cost,
                "billing_period": billing_period,
                "status": status,
            }
        )

    return turns, thread_usage


def render_markdown(
    turns: list[dict[str, Any]],
    thread_usage: dict[str, Any],
    session_files: list[Path],
    pricing: dict[str, Any],
) -> str:
    generated_at = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    numeric_fields = (
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    )
    totals = {
        field: sum(
            turn[field]
            for turn in turns
            if isinstance(turn.get(field), int)
        )
        for field in numeric_fields
    }
    completed = sum(turn["status"] == "已完成" for turn in turns)
    incomplete = sum("进行中" in turn["status"] for turn in turns)
    session_names = "、".join(f"`{path.name}`" for path in session_files)
    currency = str(pricing["currency"])
    total_cost = sum(
        (turn["estimated_cost"] for turn in turns if turn["estimated_cost"] is not None),
        Decimal(0),
    )
    unpriced_turns = sum(turn["estimated_cost"] is None for turn in turns)

    lines = [
        "# 开发过程 Token 使用记录",
        "",
        f"生成时间：{generated_at}（Asia/Shanghai）",
        "",
        "> 本文件由 `scripts/export_development_token_usage.py` 根据 Codex 会话日志生成。",
        "> Token 数据来自 `token_usage_record` 中的 `turn_token_usage` 和 `thread_token_usage`。",
        "> 费用按照 `configs/model_pricing.json` 中的官方公开单价估算，最终扣费以供应商账单为准。",
        "",
        "## 数据来源",
        "",
        f"- 会话文件：{session_names}",
        f"- 已识别开发轮次：{len(turns)}",
        f"- 已完成轮次：{completed}",
        f"- 仍有进行中快照的轮次：{incomplete}",
        "",
        "## 累计统计",
        "",
        "| 指标 | Token 数量 |",
        "| --- | ---: |",
        f"| 输入 Token | {format_number(totals['input_tokens'])} |",
        f"| 缓存输入 Token | {format_number(totals['cached_input_tokens'])} |",
        f"| 缓存写入 Token | {format_number(totals['cache_write_input_tokens'])} |",
        f"| 输出 Token | {format_number(totals['output_tokens'])} |",
        f"| 推理输出 Token | {format_number(totals['reasoning_output_tokens'])} |",
        f"| 合计 Token | {format_number(totals['total_tokens'])} |",
        f"| 当前线程累计 Token | {format_number(thread_usage.get('total_tokens'))} |",
        f"| 估算总费用 | {format_cost(total_cost, currency)} |",
        f"| 未配置价格的轮次 | {unpriced_turns} |",
        "",
        (
            "缓存输入 Token 已包含在输入 Token 中，不应再次相加。"
            "当前线程累计值包含缓存上下文，因此会明显高于最后一轮 Token。"
        ),
        "",
        "## 每次开发任务",
        "",
        "| 序号 | 开始时间 | 工作内容摘要 | 模型 | 输入 | 缓存输入 | 缓存写入 | 输出 | 推理输出 | 合计 | 计费时段 | 估算费用 | 状态 | Turn ID |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | --- |",
    ]

    for index, turn in enumerate(turns, start=1):
        lines.append(
            "| {index} | {started_at} | {label} | {model} | {input_tokens} | "
            "{cached_input_tokens} | {cache_write_input_tokens} | {output_tokens} | "
            "{reasoning_output_tokens} | {total_tokens} | {billing_period} | {cost} | "
            "{status} | `{turn_id}` |".format(
                index=index,
                started_at=turn["started_at"],
                label=turn["label"],
                model=turn["model"],
                input_tokens=format_number(turn["input_tokens"]),
                cached_input_tokens=format_number(turn["cached_input_tokens"]),
                cache_write_input_tokens=format_number(
                    turn["cache_write_input_tokens"]
                ),
                output_tokens=format_number(turn["output_tokens"]),
                reasoning_output_tokens=format_number(turn["reasoning_output_tokens"]),
                total_tokens=format_number(turn["total_tokens"]),
                billing_period=turn["billing_period"],
                cost=format_cost(turn["estimated_cost"], currency),
                status=turn["status"],
                turn_id=compact_turn_id(turn["turn_id"]),
            )
        )

    lines.extend(
        [
            "",
            "## 记录规则",
            "",
            "- 每轮数据取该 `turn_id` 下序数最大的 `turn_token_usage`，避免重复累计同一轮快照。",
            "- 费用按每条模型响应的时间判断峰谷时段，并使用实际响应 usage 计算，避免用累计快照重复收费。",
            "- 缓存命中输入按缓存价格计费，其余输入按缓存未命中价格计费。",
            "- 推理输出 Token 已包含在输出 Token 中，不重复计费。",
            "- 中国法定节假日尚未接入价格配置，可能影响峰谷判断。",
            "- 在工作内容摘要中只保留用户请求开头，避免把完整对话和敏感内容复制到项目文档。",
            "- 若 `task_complete` 尚未出现，该轮可能只包含生成文档前的快照；下次运行脚本会覆盖为完整数据。",
            "- 开发过程 Token 与平台运行时生成代码的 Token 分开管理，后者应由平台运行记录和成本页面展示。",
            "",
            "## 更新命令",
            "",
            "```powershell",
            (
                "& 'D:\\itwork\\itwork2026\\app\\Miniconda3\\envs\\multiagent\\python.exe' "
                "scripts\\export_development_token_usage.py"
            ),
            "```",
            "",
            "## 价格来源",
            "",
            f"- 来源：{pricing['source']}",
            f"- 价格读取日期：{pricing['pricing_retrieved_at']}",
            f"- 币种：{currency}",
            f"- 计价单位：每 {int(pricing['unit_tokens']):,} Token",
            "- 详情见 `docs/MODEL_PRICING.md`。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    pricing = load_pricing(args.pricing_file)
    session_files = args.session_file or [latest_session_file(args.sessions_root)]
    records: list[dict[str, Any]] = []
    for session_file in session_files:
        records.extend(read_records(session_file))

    turns, thread_usage = collect_turns(records, pricing)
    markdown = render_markdown(turns, thread_usage, session_files, pricing)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    print(f"已生成 {args.output}")
    total_tokens = sum(
        turn["total_tokens"]
        for turn in turns
        if isinstance(turn["total_tokens"], int)
    )
    total_cost = sum(
        (turn["estimated_cost"] for turn in turns if turn["estimated_cost"] is not None),
        Decimal(0),
    )
    print(f"开发轮次：{len(turns)}；合计 Token：{format_number(total_tokens)}")
    print(f"估算费用：{format_cost(total_cost, str(pricing['currency']))}")


if __name__ == "__main__":
    main()
