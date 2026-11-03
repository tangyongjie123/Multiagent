"""Tester Agent 契约测试生成器测试。"""

from app.agents.specialists import LLMSpecialistExecutor


def test_contract_test_targets_architect_endpoints() -> None:
    """测试文件必须覆盖列表、缺失资源和非法创建请求。"""

    generated = LLMSpecialistExecutor._build_contract_test(
        {
            "package_name": "com.example.book",
            "entities": [
                {
                    "name": "Book",
                    "table_name": "books",
                    "fields": [
                        {"name": "title", "java_type": "String", "nullable": False},
                        {"name": "isbn", "java_type": "String", "nullable": False},
                    ],
                }
            ],
            "endpoints": [
                {"method": "GET", "path": "/api/v1/tasks"},
                {"method": "GET", "path": "/api/v1/tasks/{id}"},
                {"method": "POST", "path": "/api/v1/tasks"},
                {"method": "PUT", "path": "/api/v1/tasks/{id}"},
                {"method": "DELETE", "path": "/api/v1/tasks/{id}"},
            ]
        }
    )

    assert generated.path == (
        "src/test/java/com/example/book/GeneratedApiContractTest.java"
    )
    assert "package com.example.book;" in generated.content
    assert "listEndpointReturnsSuccess" in generated.content
    assert "missingResourceReturnsNotFound" in generated.content
    assert "invalidCreateRequestReturnsBadRequest" in generated.content
    assert "fullCrudFlowWorks" in generated.content
    assert "duplicateIsbnReturnsConflict" in generated.content
    assert 'assertEquals(409, post("/api/v1/tasks", body).statusCode())' in generated.content
    assert 'assertEquals(400, response.statusCode())' in generated.content
