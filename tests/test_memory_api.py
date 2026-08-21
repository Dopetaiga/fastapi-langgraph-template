"""Tests for memory API endpoints (Phase 9)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


class TestMemoryAPI:
    def test_put_and_get_user_memory(self, client: TestClient):
        resp = client.post("/memory/user", json={
            "user_id": "u1",
            "key": "lang",
            "value": {"lang": "python"},
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["key"] == "lang"
        assert body["value"]["lang"] == "python"

    def test_get_user_memory(self, client: TestClient):
        client.post("/memory/user", json={"user_id": "u2", "key": "pref", "value": {"theme": "dark"}})
        resp = client.get("/memory/user/u2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["key"] == "pref"

    def test_get_user_memory_key(self, client: TestClient):
        client.post("/memory/user", json={"user_id": "u3", "key": "color", "value": {"color": "blue"}})
        resp = client.get("/memory/user/u3/color")
        assert resp.status_code == 200
        assert resp.json()["value"]["color"] == "blue"

    def test_get_missing_key_404(self, client: TestClient):
        resp = client.get("/memory/user/nobody/missing")
        assert resp.status_code == 404

    def test_put_team_memory(self, client: TestClient):
        resp = client.post("/memory/team", json={
            "team_id": "team-1",
            "key": "goal",
            "value": {"goal": "launch"},
        })
        assert resp.status_code == 200
        assert resp.json()["namespace"] == "team"

    def test_get_team_memory(self, client: TestClient):
        client.post("/memory/team", json={"team_id": "team-2", "key": "k1", "value": {"v": 1}})
        resp = client.get("/memory/team/team-2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["key"] == "k1"

    def test_user_isolation(self, client: TestClient):
        client.post("/memory/user", json={"user_id": "uA", "key": "secret", "value": {"s": "A"}})
        client.post("/memory/user", json={"user_id": "uB", "key": "secret", "value": {"s": "B"}})
        resp_a = client.get("/memory/user/uA/secret")
        resp_b = client.get("/memory/user/uB/secret")
        assert resp_a.json()["value"]["s"] == "A"
        assert resp_b.json()["value"]["s"] == "B"
