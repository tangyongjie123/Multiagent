"""FastAPI 基础接口测试。"""

from fastapi.testclient import TestClient

from app.main import app


def test_live_endpoint() -> None:
    """应用存活检查不依赖外部数据库。"""

    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
