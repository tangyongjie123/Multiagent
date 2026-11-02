"""Tester Agent 契约测试生成器测试。"""

from app.agents.specialists import LLMSpecialistExecutor


def test_contract_test_targets_architect_endpoints() -> None:
    """测试文件必须覆盖列表、缺失资源和非法创建请求。"""

    generated = LLMSpecialistExecutor._build_contract_test(
        {
            "endpoints": [
                {"method": "GET", "path": "/api/v1/tasks"},
                {"method": "GET", "path": "/api/v1/tasks/{id}"},
                {"method": "POST", "path": "/api/v1/tasks"},
            ]
        }
    )

    assert generated.path.endswith("GeneratedApiContractTest.java")
    assert "listEndpointReturnsSuccess" in generated.content
    assert "missingResourceReturnsNotFound" in generated.content
    assert "invalidCreateRequestReturnsBadRequest" in generated.content
    assert 'assertEquals(400, response.statusCode())' in generated.content
