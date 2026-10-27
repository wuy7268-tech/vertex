import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.runtime import SessionLocal
from app.seed import seed_workspace


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        db = SessionLocal()
        seed_workspace(db)
        db.close()
        yield test_client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_search_and_run(client):
    search = client.get("/api/search", params={"q": "navigation proposal"})
    assert search.status_code == 200
    assert any(hit["title"] == "Navigation proposal" for hit in search.json()["results"])
    goals = client.get("/api/goals").json()["goals"]
    goal = next(item for item in goals if item["title"] == "Design review prep")
    run = client.post(f"/api/goals/{goal['id']}/run")
    assert run.status_code == 200
    body = run.json()
    assert body["run"]["status"] == "completed"
    kinds = {event["kind"] for event in body["run"]["events"]}
    assert "plan" in kinds
    assert "checkpoint" in kinds
    assert body["run"]["artifacts"]["documents"]
    tasks = client.get("/api/tasks").json()["tasks"]
    assert any(task["source"] == "agent" for task in tasks)


def test_create_task_and_reject_bad_integration_mode(client):
    created = client.post("/api/tasks", json={"title": "Write the demo script", "priority": "high"})
    assert created.status_code == 200
    assert created.json()["status"] == "todo"
    bad = client.put("/api/integrations/gmail", json={"mode": "carrier-pigeon"})
    assert bad.status_code == 400
