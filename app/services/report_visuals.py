"""生成自包含的审查报告图表与 HTML。"""

from __future__ import annotations

import base64
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from typing import Any

# 报告图表使用暖纸色背景和近黑色文字，避免浏览器默认白色与高饱和色。
PAPER = "#f3eee1"
INK = "#17140e"
SOFT_INK = "#4a463c"
MUTED = "#8c8578"
TRACK = "#ded8ca"
ACCENT = "#e5532d"
SEVERITY_COLORS = {
    "critical": "#b92d2d",
    "major": "#e17b2d",
    "minor": "#c39a1c",
    "info": "#2d8588",
}
SEVERITY_LABELS = {
    "critical": "严重",
    "major": "主要",
    "minor": "次要",
    "info": "提示",
}
CATEGORY_LABELS = {
    "architecture": "架构",
    "test": "测试",
    "security": "安全",
    "quality": "质量",
}
CATEGORY_ORDER = tuple(CATEGORY_LABELS)


@dataclass(frozen=True)
class ReportVisuals:
    """报告中的两张 SVG 图表。"""

    severity_svg: str
    category_svg: str
    severity_alt: str
    category_alt: str
    source_line: str


def build_report_visuals(
    *,
    repository_name: str,
    findings: list[dict[str, Any]],
    generated_at: datetime | None = None,
) -> ReportVisuals:
    """按数据形状生成严重级别和分类图片。

    严重级别是同一总量的构成关系，使用 100% 堆叠条；分类是少量类目比较，
    使用排序后的零基线横向条形图。
    """

    generated = generated_at or datetime.now(UTC)
    source_line = (
        f"来源：RepoGraph 对 {repository_name} 的静态分析"
        f" · {generated:%Y-%m-%d} · 单位：项"
    )
    severity_counts = Counter(
        str(item.get("severity") or "info") for item in findings
    )
    category_counts = Counter(
        str(item.get("category") or "quality") for item in findings
    )
    total = len(findings)
    severity_alt, severity_svg = _severity_chart(
        severity_counts,
        total,
        source_line,
    )
    category_alt, category_svg = _category_chart(
        category_counts,
        total,
        source_line,
    )
    return ReportVisuals(
        severity_svg=severity_svg,
        category_svg=category_svg,
        severity_alt=severity_alt,
        category_alt=category_alt,
        source_line=source_line,
    )


def inject_markdown_visuals(markdown: str, visuals: ReportVisuals) -> str:
    """把 SVG 图片以 data URI 嵌入 Markdown，使报告单文件可携带图表。"""

    severity_data = _svg_data_uri(visuals.severity_svg)
    category_data = _svg_data_uri(visuals.category_svg)
    visual_section = "\n".join(
        [
            "## 可视化摘要",
            "",
            f"![{visuals.severity_alt}]({severity_data})",
            "",
            f"![{visuals.category_alt}]({category_data})",
            "",
            f"> {visuals.source_line}",
            "",
        ]
    )
    marker = "## 评估概览"
    if marker not in markdown:
        return f"{markdown.rstrip()}\n\n{visual_section}"
    return markdown.replace(marker, f"{visual_section}\n{marker}", 1)


def build_html_report(
    *,
    repository_name: str,
    repository_url: str,
    branch: str | None,
    commit_sha: str | None,
    file_count: int,
    findings: list[dict[str, Any]],
    visuals: ReportVisuals,
) -> str:
    """生成无脚本、内嵌图表且经过 HTML 转义的自包含报告。"""

    category_groups = {
        category: [
            item
            for item in findings
            if str(item.get("category") or "quality") == category
        ]
        for category in CATEGORY_ORDER
    }
    finding_sections = []
    # 问题详情按固定分类顺序输出，保证不同报告的结构一致。
    for category, items in category_groups.items():
        cards = []
        for index, item in enumerate(items, start=1):
            location = str(item.get("file_path") or "项目级")
            if item.get("line"):
                location = f"{location}:{item['line']}"
            cards.append(
                """
                <article class="finding {severity}">
                  <div class="finding-meta">
                    <span>{index:02d}</span>
                    <b>{severity}</b>
                    <code>{location}</code>
                  </div>
                  <h3>{title}</h3>
                  <p><strong>证据</strong>{evidence}</p>
                  <p><strong>影响</strong>{impact}</p>
                  <p><strong>建议</strong>{recommendation}</p>
                </article>
                """.format(
                    index=index,
                    severity=escape(str(item.get("severity") or "info")),
                    location=escape(location),
                    title=escape(str(item.get("title") or "未命名问题")),
                    evidence=escape(str(item.get("evidence") or "")),
                    impact=escape(str(item.get("impact") or "")),
                    recommendation=escape(str(item.get("recommendation") or "")),
                )
            )
        if not cards:
            cards.append('<p class="empty">本分类未发现问题。</p>')
        finding_sections.append(
            f"""
            <section class="category-section">
              <div class="category-heading">
                <h2>{CATEGORY_LABELS[category]}</h2>
                <span>{len(items)} 项</span>
              </div>
              {''.join(cards)}
            </section>
            """
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(repository_name)} 代码审查报告</title>
  <style>
    :root {{
      color: {INK};
      background: {PAPER};
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{ max-width: 1080px; margin: 0 auto; padding: 48px 28px 72px; line-height: 1.65; }}
    header {{ padding-bottom: 24px; border-bottom: 2px solid {INK}; }}
    h1 {{
      margin: 0 0 16px;
      font-size: clamp(34px, 6vw, 64px);
      line-height: .98;
      letter-spacing: -.055em;
    }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 8px 22px; color: {SOFT_INK}; font-size: 12px; }}
    .summary {{ margin: 20px 0 30px; font-size: 14px; }}
    .charts {{ display: grid; gap: 18px; }}
    .chart {{ overflow: hidden; border: 1px solid #c9c2b4; background: {PAPER}; }}
    .chart svg {{ display: block; width: 100%; height: auto; }}
    .source {{ margin: 10px 0 32px; color: {MUTED}; font-size: 11px; }}
    .category-section {{ margin-top: 34px; }}
    .category-heading {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      border-bottom: 1px solid #aaa397;
    }}
    .category-heading h2 {{ margin: 0 0 8px; font-size: 24px; letter-spacing: -.035em; }}
    .category-heading span {{ color: {MUTED}; font-size: 12px; }}
    .finding {{
      margin-top: 10px;
      padding: 18px;
      border: 1px solid #c9c2b4;
      border-left: 5px solid {MUTED};
      background: #faf7ef;
    }}
    .finding.critical {{ border-left-color: #b92d2d; }}
    .finding.major {{ border-left-color: #e17b2d; }}
    .finding.minor {{ border-left-color: #c39a1c; }}
    .finding.info {{ border-left-color: #2d8588; }}
    .finding-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      color: {MUTED};
      font-family: "Cascadia Code", monospace;
      font-size: 10px;
    }}
    .finding-meta b {{ padding: 2px 6px; border: 1px solid #c9c2b4; color: {SOFT_INK}; }}
    .finding-meta code {{ margin-left: auto; }}
    .finding h3 {{ margin: 9px 0; font-size: 18px; }}
    .finding p {{
      display: grid;
      grid-template-columns: 42px 1fr;
      gap: 8px;
      margin: 6px 0;
      font-size: 12px;
    }}
    .finding p strong {{ color: {INK}; }}
    .empty {{ color: {MUTED}; }}
    @media (max-width: 640px) {{
      body {{ padding: 24px 14px 48px; }}
      .finding-meta code {{ width: 100%; margin-left: 0; overflow-wrap: anywhere; }}
      .finding p {{ grid-template-columns: 1fr; gap: 2px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(repository_name)}<br>代码审查报告</h1>
    <div class="meta">
      <span>仓库：{escape(repository_url)}</span>
      <span>分支：{escape(branch or "默认分支")}</span>
      <span>Commit：{escape((commit_sha or "未知")[:12])}</span>
      <span>文件：{file_count}</span>
      <span>问题：{len(findings)}</span>
    </div>
  </header>
  <p class="summary"><strong>{escape(visuals.category_alt)}</strong></p>
  <section class="charts">
    <div class="chart" role="img" aria-label="{escape(visuals.severity_alt)}">
      {visuals.severity_svg}
    </div>
    <div class="chart" role="img" aria-label="{escape(visuals.category_alt)}">
      {visuals.category_svg}
    </div>
  </section>
  <p class="source">{escape(visuals.source_line)}</p>
  {''.join(finding_sections)}
</body>
</html>
"""


def _severity_chart(
    counts: Counter[str],
    total: int,
    source_line: str,
) -> tuple[str, str]:
    """生成严重级别 100% 堆叠条 SVG 和无障碍替代文本。"""

    width = 960
    height = 310
    bar_x = 42
    bar_y = 128
    bar_width = 876
    bar_height = 68
    dominant = max(("critical", "major", "minor", "info"), key=lambda item: counts[item])
    dominant_count = counts[dominant]
    insight = (
        f"{SEVERITY_LABELS[dominant]}问题共 {dominant_count} 项，"
        f"占全部 {total} 项的 {_percentage(dominant_count, total)}"
        if total
        else "本次分析未发现问题"
    )
    alt = (
        f"严重级别分布图显示{SEVERITY_LABELS[dominant]}问题最多，"
        f"共 {dominant_count} 项，占全部 {total} 项的 {_percentage(dominant_count, total)}。"
        if total
        else "严重级别分布图显示本次分析未发现问题。"
    )
    segments: list[str] = []
    cursor: float = bar_x
    for severity in ("critical", "major", "minor", "info"):
        value = counts[severity]
        segment_width = bar_width * value / total if total else 0
        if segment_width > 0:
            segments.append(
                f'<rect x="{cursor:.1f}" y="{bar_y}" width="{segment_width:.1f}" '
                f'height="{bar_height}" fill="{SEVERITY_COLORS[severity]}"/>'
            )
            label = f"{SEVERITY_LABELS[severity]} {value}"
            if segment_width >= 72:
                segments.append(
                    f'<text x="{cursor + segment_width / 2:.1f}" '
                    f'y="{bar_y + 40}" text-anchor="middle" font-size="13" '
                    f'font-weight="700" fill="#fff">{label}</text>'
                )
            else:
                segments.append(
                    f'<text x="{cursor + segment_width / 2:.1f}" '
                    f'y="{bar_y - 12}" text-anchor="middle" font-size="11" '
                    f'fill="{SOFT_INK}">{label}</text>'
                )
            cursor += segment_width
    if total == 0:
        segments.append(
            f'<rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" '
            f'fill="{TRACK}"/>'
        )
        segments.append(
            f'<text x="{bar_x + bar_width / 2}" y="{bar_y + 41}" text-anchor="middle" '
            f'font-size="14" fill="{MUTED}">未发现问题</text>'
        )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg"
  width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <title>{escape(alt)}</title>
  <desc>{escape(alt)}</desc>
  <rect width="{width}" height="{height}" fill="{PAPER}"/>
  <text x="42" y="42" font-size="11" font-weight="700" letter-spacing="2"
    fill="{MUTED}">SEVERITY DISTRIBUTION · 严重级别</text>
  <text x="42" y="82" font-size="25" font-weight="750" fill="{INK}">{escape(insight)}</text>
  <text x="42" y="106" font-size="12" fill="{SOFT_INK}">全部问题按严重级别构成 · 单位：项</text>
  {''.join(segments)}
  <line x1="{bar_x}" y1="{bar_y + bar_height + 24}"
    x2="{bar_x + bar_width}" y2="{bar_y + bar_height + 24}" stroke="{TRACK}"/>
  <text x="42" y="{height - 26}" font-size="10" fill="{MUTED}">{escape(source_line)}</text>
</svg>"""
    return alt, svg


def _category_chart(
    counts: Counter[str],
    total: int,
    source_line: str,
) -> tuple[str, str]:
    """生成按数量降序的分类横向条形图 SVG。"""

    width = 960
    height = 430
    ranked = sorted(
        CATEGORY_ORDER,
        key=lambda category: (-counts[category], CATEGORY_ORDER.index(category)),
    )
    max_count = max((counts[category] for category in ranked), default=0)
    dominant = ranked[0]
    dominant_count = counts[dominant]
    insight = (
        f"{CATEGORY_LABELS[dominant]}问题最多，共 {dominant_count} 项，"
        f"占全部 {total} 项的 {_percentage(dominant_count, total)}"
        if total
        else "本次分析未发现问题"
    )
    alt = (
        f"分类条形图显示{CATEGORY_LABELS[dominant]}问题最多，"
        f"共 {dominant_count} 项，占全部 {total} 项的 {_percentage(dominant_count, total)}。"
        if total
        else "分类条形图显示本次分析未发现问题。"
    )
    rows: list[str] = []
    for index, category in enumerate(ranked):
        y = 132 + index * 62
        value = counts[category]
        length = 0 if max_count == 0 else max(3, value / max_count * 590)
        fill = ACCENT if index == 0 and value > 0 else SOFT_INK
        rows.extend(
            [
                f'<text x="42" y="{y + 19}" font-size="14" font-weight="700" fill="{INK}">'
                f"{CATEGORY_LABELS[category]}</text>",
                f'<rect x="150" y="{y}" width="620" height="24" fill="{TRACK}"/>',
                f'<rect x="150" y="{y}" width="{length:.1f}" height="24" fill="{fill}"/>',
                f'<text x="792" y="{y + 18}" font-size="13" font-weight="700" '
                f'fill="{INK}">{value} 项</text>',
                f'<text x="865" y="{y + 18}" font-size="12" fill="{SOFT_INK}">'
                f"{_percentage(value, total)}</text>",
            ]
        )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg"
  width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <title>{escape(alt)}</title>
  <desc>{escape(alt)}</desc>
  <rect width="{width}" height="{height}" fill="{PAPER}"/>
  <text x="42" y="42" font-size="11" font-weight="700" letter-spacing="2"
    fill="{MUTED}">ISSUE CATEGORIES · 分类评估</text>
  <text x="42" y="82" font-size="25" font-weight="750" fill="{INK}">{escape(insight)}</text>
  <text x="42" y="106" font-size="12" fill="{SOFT_INK}">按问题数量降序 · 零基线 · 单位：项</text>
  {''.join(rows)}
  <text x="42" y="{height - 24}" font-size="10" fill="{MUTED}">{escape(source_line)}</text>
</svg>"""
    return alt, svg


def _svg_data_uri(svg: str) -> str:
    """把 SVG 转为 Markdown 可内嵌的 base64 data URI。"""

    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _percentage(count: int, total: int) -> str:
    """格式化百分比，并处理零问题仓库。"""

    return f"{count / total * 100:.1f}%" if total else "0.0%"
