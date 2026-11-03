"""报告下载路径安全测试。"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

import app.api.routes.analyses as analyses_route


def test_report_path_must_stay_inside_analysis_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    report = workspace / ".analysis/report.md"
    report.parent.mkdir(parents=True)
    report.write_text("# report", encoding="utf-8")
    monkeypatch.setattr(
        analyses_route,
        "repository_workspace",
        lambda _: workspace,
    )

    assert (
        analyses_route._resolve_report_path(UUID(int=1), str(report))
        == report.resolve()
    )

    outside = tmp_path / "outside.md"
    outside.write_text("not allowed", encoding="utf-8")
    assert analyses_route._resolve_report_path(UUID(int=1), str(outside)) is None
