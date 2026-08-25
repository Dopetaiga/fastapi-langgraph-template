"""Static contract checks for the zero-build WebUI event timeline."""

from pathlib import Path


def test_webui_subscribes_to_model_lifecycle_events() -> None:
    source = (Path(__file__).parents[1] / "webui" / "js" / "app.js").read_text("utf-8")
    for event_type in (
        "llm.requested",
        "llm.completed",
        "llm.failed",
        "llm.fallback",
        "llm.retrying",
    ):
        assert event_type in source
