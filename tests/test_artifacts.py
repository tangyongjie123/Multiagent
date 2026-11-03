"""生成工程文件树、路径安全和 ZIP 打包测试。"""

from pathlib import Path
from uuid import UUID

import pytest

from app.services.artifacts import (
    ArtifactPathError,
    build_workspace_diff,
    build_workspace_zip,
    list_workspace_files,
    resolve_workspace_file,
)


def test_list_diff_and_zip_exclude_build_output(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/App.java").write_text("class App {}\n", encoding="utf-8")
    (tmp_path / "target").mkdir()
    (tmp_path / "target/App.class").write_bytes(b"binary")

    files = list_workspace_files(tmp_path)
    additions, deletions, patch = build_workspace_diff(tmp_path)
    archive = build_workspace_zip(tmp_path)

    assert files == [("src/App.java", 14)]
    assert additions == 1
    assert deletions == 0
    assert "diff --git a/src/App.java" in patch
    assert archive.startswith(b"PK")


def test_resolve_file_rejects_path_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / str(UUID(int=1))
    workspace.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(ArtifactPathError):
        resolve_workspace_file(workspace, "../secret.txt")
