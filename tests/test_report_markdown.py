"""分类审查报告生成测试。"""

from __future__ import annotations

from pathlib import Path

from app.agents.specialists import _build_report_markdown
from app.agents.supervisor import AnalysisState
from app.services.report_visuals import (
    build_html_report,
    build_report_visuals,
    inject_markdown_visuals,
)
from app.services.repository import RepositorySnapshot


def test_report_groups_findings_and_includes_charts(tmp_path: Path) -> None:
    snapshot = RepositorySnapshot(
        root=tmp_path,
        commit_sha="abc123",
        file_count=8,
        total_bytes=1024,
        languages={"Java": 4},
        build_files=["pom.xml"],
        test_files=[],
        entry_points=[],
        spring_indicators=[],
        tree=[],
    )
    findings = [
        {
            "category": "quality",
            "severity": "minor",
            "title": "使用标准输出",
            "file_path": "App.java",
            "line": 10,
            "evidence": "System.out.print",
            "impact": "缺少日志级别",
            "recommendation": "使用 SLF4J",
        },
        {
            "category": "architecture",
            "severity": "major",
            "title": "缺少服务层",
            "file_path": "Controller.java",
            "line": 5,
            "evidence": "Controller 直接访问 Repository",
            "impact": "耦合较高",
            "recommendation": "抽取 Service",
        },
    ]
    state: AnalysisState = {
        "repository_url": "https://github.com/example/demo.git",
        "branch": "main",
    }

    markdown = _build_report_markdown(
        repository_name="demo",
        state=state,
        findings=findings,
        snapshot=snapshot,
    )

    assert "## 评估概览" in markdown
    assert "| 架构 | 1 | 50.0% |" in markdown
    assert "| 安全 | 0 | 0.0% |" in markdown
    assert "### 架构（1）" in markdown
    assert "### 质量（1）" in markdown
    assert markdown.index("### 架构（1）") < markdown.index("### 质量（1）")
    assert "`██████████░░░░░░░░░░`" in markdown


def test_report_contains_embedded_svg_images_and_html() -> None:
    findings = [
        {
            "category": "security",
            "severity": "critical",
            "title": "危险配置",
            "file_path": "application.properties",
            "line": 3,
            "evidence": "检测到敏感凭证",
            "impact": "可能泄露密钥",
            "recommendation": "改用环境变量",
        },
        {
            "category": "quality",
            "severity": "minor",
            "title": "日志不规范",
            "file_path": "App.java",
            "line": 9,
            "evidence": "使用标准输出",
            "impact": "缺少日志级别",
            "recommendation": "使用 SLF4J",
        },
    ]
    visuals = build_report_visuals(
        repository_name="demo",
        findings=findings,
    )
    markdown = inject_markdown_visuals("## 评估概览\n\n正文", visuals)
    html = build_html_report(
        repository_name="demo<script>",
        repository_url="https://github.com/example/demo.git",
        branch="main",
        commit_sha="abcdef123456",
        file_count=2,
        findings=findings,
        visuals=visuals,
    )

    assert "data:image/svg+xml;base64," in markdown
    assert visuals.severity_alt.startswith("严重级别分布图显示")
    assert visuals.category_alt.startswith("分类条形图显示")
    assert "<svg" in visuals.severity_svg
    assert "<svg" in visuals.category_svg
    assert "demo&lt;script&gt;" in html
    assert "<script>" not in html
    assert 'role="img"' in html
