from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


def test_live() -> None:
    response = TestClient(app).get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_without_database() -> None:
    def unavailable_db():
        yield object()
    app.dependency_overrides[get_db] = unavailable_db
    response = TestClient(app).get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
    app.dependency_overrides.clear()


def test_ready_with_database() -> None:
    class Healthy:
        def execute(self, _query):
            return 1
    def healthy_db():
        yield Healthy()
    app.dependency_overrides[get_db] = healthy_db
    response = TestClient(app).get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    app.dependency_overrides.clear()
