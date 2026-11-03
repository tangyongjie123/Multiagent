"""Git URL 校验和仓库静态扫描测试。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.repository as repository_module
from app.services.repository import (
    RepositoryError,
    resolve_git_executable,
    scan_repository,
    validate_repository_url,
)


def test_git_url_validation() -> None:
    url, host = validate_repository_url("https://github.com/example/project.git")
    assert url == "https://github.com/example/project.git"
    assert host == "github.com"

    with pytest.raises(RepositoryError):
        validate_repository_url("file:///tmp/project")
    with pytest.raises(RepositoryError):
        validate_repository_url("https://token@github.com/example/project.git")
    with pytest.raises(RepositoryError):
        validate_repository_url("https://example.com/project.git")


def test_configured_git_executable_is_used(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "git.exe"
    executable.write_bytes(b"stub")
    monkeypatch.setattr(
        repository_module,
        "get_settings",
        lambda: SimpleNamespace(git_executable=str(executable)),
    )

    assert resolve_git_executable() == str(executable)


def test_missing_configured_git_executable_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        repository_module,
        "get_settings",
        lambda: SimpleNamespace(git_executable=str(tmp_path / "missing-git.exe")),
    )

    with pytest.raises(RepositoryError, match="GIT_EXECUTABLE"):
        resolve_git_executable()


@pytest.mark.asyncio
async def test_repository_snapshot_detects_spring_project(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    source = tmp_path / "src/main/java/example"
    source.mkdir(parents=True)
    (source / "DemoApplication.java").write_text(
        "@SpringBootApplication\npublic class DemoApplication {}",
        encoding="utf-8",
    )
    tests = tmp_path / "src/test/java/example"
    tests.mkdir(parents=True)
    (tests / "DemoTest.java").write_text(
        "class DemoTest { @Test void works() {} }",
        encoding="utf-8",
    )
    resources = tmp_path / "src/main/resources"
    resources.mkdir(parents=True)
    (resources / "application.yml").write_text(
        "server:\n  port: 8080\n",
        encoding="utf-8",
    )

    snapshot = await scan_repository(tmp_path)

    assert snapshot.file_count == 4
    assert snapshot.languages["Java"] == 2
    assert "pom.xml" in snapshot.build_files
    assert snapshot.test_files
    assert snapshot.spring_indicators
    assert "src/main/resources/application.yml" in snapshot.source_files
