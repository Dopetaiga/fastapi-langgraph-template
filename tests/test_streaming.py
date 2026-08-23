"""Durable SSE streaming contract tests."""
from __future__ import annotations

import json
from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.api.streaming import _sse_event, get_event_repository
from app.main import create_app


@dataclass
class FakeEvent:
    seq: int
    type: str
    payload: dict
    node: str | None = None


class FakeRepository:
    def __init__(self, events: list[FakeEvent], *, exists: bool = True) -> None:
        self.events = events
        self.exists = exists
        self.after_values: list[int] = []

    async def run_exists(self, _run_id: str) -> bool:
        return self.exists

    async def list_after(self, _run_id: str, after_seq: int):
        self.after_values.append(after_seq)
        return [event for event in self.events if event.seq > after_seq]

    async def run_is_terminal_or_paused(self, _run_id: str) -> bool:
        return True


def _client(repository: FakeRepository) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_event_repository] = lambda: repository
    return TestClient(app)


def test_stream_replays_durable_events_and_emits_sse_ids():
    repository = FakeRepository([
        FakeEvent(0, "run.started", {}),
        FakeEvent(1, "run.completed", {"status": "ok"}),
    ])
    response = _client(repository).get("/runs/r1/stream")

    assert response.status_code == 200
    assert "id: 0" in response.text
    assert "event: run.completed" in response.text
    assert repository.after_values == [-1]


def test_stream_honors_last_event_id_header():
    repository = FakeRepository([
        FakeEvent(0, "run.started", {}),
        FakeEvent(1, "run.completed", {}),
    ])
    response = _client(repository).get(
        "/runs/r1/stream?after_seq=-1",
        headers={"Last-Event-ID": "0"},
    )

    assert response.status_code == 200
    assert "id: 0" not in response.text
    assert "id: 1" in response.text
    assert repository.after_values == [0]


def test_stream_unknown_run_is_404():
    response = _client(FakeRepository([], exists=False)).get("/runs/missing/stream")
    assert response.status_code == 404


def test_sse_event_contains_id_type_node_and_payload():
    event = _sse_event("tool.completed", {"result": "ok"}, 5, "tool")
    data_line = next(line for line in event.splitlines() if line.startswith("data: "))
    data = json.loads(data_line.removeprefix("data: "))
    assert event.startswith("id: 5\nevent: tool.completed\n")
    assert data == {
        "type": "tool.completed",
        "seq": 5,
        "node": "tool",
        "payload": {"result": "ok"},
    }
