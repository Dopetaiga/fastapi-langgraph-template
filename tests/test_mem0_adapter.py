from __future__ import annotations

from app.capabilities.memory_store import Mem0MemoryStore


class FakeMem0Client:
    def __init__(self) -> None:
        self.calls = []

    async def add(self, **kwargs):
        self.calls.append(("add", kwargs))
        return {"results": [{"id": "m1", "memory": "likes tea", "event": "ADD"}]}

    async def search(self, **kwargs):
        self.calls.append(("search", kwargs))
        return {"results": [{"id": "m1", "memory": "likes tea", "score": 0.9}]}

    async def get_all(self, **kwargs):
        self.calls.append(("get_all", kwargs))
        return {"count": 1, "results": [{"id": "m1", "memory": "likes tea"}]}


async def test_mem0_adapter_scopes_search_and_normalizes_results():
    client = FakeMem0Client()
    store = Mem0MemoryStore(client)

    records = await store.search(user_id="u1", query="drink", top_k=3)

    assert records[0].text == "likes tea"
    assert records[0].score == 0.9
    assert client.calls == [("search", {
        "query": "drink",
        "filters": {"user_id": "u1"},
        "top_k": 3,
    })]


async def test_mem0_adapter_add_and_paginated_list():
    client = FakeMem0Client()
    store = Mem0MemoryStore(client)

    added = await store.add(
        user_id="u1",
        messages=[{"role": "user", "content": "I like tea"}],
        metadata={"source": "chat"},
    )
    listed = await store.list(user_id="u1", page=2, page_size=10)

    assert added[0].id == "m1"
    assert listed[0].text == "likes tea"
    assert client.calls[1] == ("get_all", {
        "filters": {"user_id": "u1"},
        "page": 2,
        "page_size": 10,
    })
