from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.memory import get_memory_store
from app.capabilities.memory_store import MemoryRecord
from app.main import create_app


class FakeMemoryStore:
    def __init__(self) -> None:
        self.calls = []

    async def add(self, **kwargs):
        self.calls.append(("add", kwargs))
        return [MemoryRecord(id="m1", text="likes tea")]

    async def search(self, **kwargs):
        self.calls.append(("search", kwargs))
        return [MemoryRecord(id="m1", text="likes tea", score=0.9)]

    async def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        return [MemoryRecord(id="m1", text="likes tea")]


def _client(store: FakeMemoryStore) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_memory_store] = lambda: store
    return TestClient(app)


def test_add_memory_uses_async_store_boundary():
    store = FakeMemoryStore()
    response = _client(store).post("/memory/u1", json={
        "messages": [{"role": "user", "content": "I like tea"}],
        "metadata": {"source": "chat"},
    })
    assert response.status_code == 200
    assert response.json()["memories"][0]["text"] == "likes tea"
    assert store.calls[0][1]["user_id"] == "u1"


def test_search_memory_is_user_scoped():
    store = FakeMemoryStore()
    response = _client(store).post("/memory/u2/search", json={"query": "drink", "top_k": 3})
    assert response.status_code == 200
    assert store.calls == [("search", {"user_id": "u2", "query": "drink", "top_k": 3})]


def test_list_memory_passes_pagination():
    store = FakeMemoryStore()
    response = _client(store).get("/memory/u3?page=2&page_size=10")
    assert response.status_code == 200
    assert store.calls == [("list", {"user_id": "u3", "page": 2, "page_size": 10})]


def test_add_rejects_empty_messages():
    response = _client(FakeMemoryStore()).post("/memory/u1", json={"messages": []})
    assert response.status_code == 422
