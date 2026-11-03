"""Git URL 校验和仓库静态扫描测试。"""

from pathlib import Path

import pytest

from app.services.repository import (
    RepositoryError,
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
