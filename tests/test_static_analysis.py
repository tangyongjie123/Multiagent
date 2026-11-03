"""确定性安全与质量规则测试。"""

from pathlib import Path

from app.agents.specialists import _source_priority
from app.domain.models import FindingCategory
from app.services.redaction import redact_sensitive_text
from app.services.repository import RepositorySnapshot
from app.services.static_analysis import run_static_analysis


def test_static_rules_detect_secret_and_empty_catch(tmp_path: Path) -> None:
    source = "String api_key = \"supersecret123\";\ntry { x(); } catch (Exception e) {}\n"
    snapshot = RepositorySnapshot(
        root=tmp_path,
        commit_sha="abc",
        file_count=1,
        total_bytes=len(source),
        languages={"Java": 1},
        build_files=[],
        test_files=["src/test/AppTest.java"],
        entry_points=[],
        spring_indicators=[],
        tree=["src/main/App.java"],
        source_files={"src/main/App.java": source},
    )

    findings = run_static_analysis(snapshot)
    categories = {finding.category for finding in findings}
    titles = {finding.title for finding in findings}

    assert FindingCategory.SECURITY in categories
    assert "存在空的异常处理块" in titles
    lines_by_title = {finding.title: finding.line for finding in findings}
    assert lines_by_title["代码中可能包含敏感凭证"] == 1
    assert lines_by_title["存在空的异常处理块"] == 2


def test_source_priority_prefers_application_code() -> None:
    assert _source_priority("src/main/java/App.java") == 0
    assert _source_priority("scripts/tool.py") == 1
    assert _source_priority("pom.xml") == 2
    assert _source_priority("src/test/java/AppTest.java") == 3


def test_redaction_handles_prefixed_database_password_names() -> None:
    content = "DB_PWD='root-secret'; ADMIN_TOKEN='token-value'; SECRET_KEY='key-value';"
    redacted = redact_sensitive_text(content)

    assert "root-secret" not in redacted
    assert "token-value" not in redacted
    assert "key-value" not in redacted
    assert redacted.count("<REDACTED>") == 3
