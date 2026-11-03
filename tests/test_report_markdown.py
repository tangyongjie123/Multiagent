"""分类审查报告生成测试。"""

from __future__ import annotations

from pathlib import Path

from app.agents.specialists import _build_report_markdown
from app.agents.supervisor import AnalysisState
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
