"""Pytest configuration and shared fixtures."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def mock_litellm_response():
    """Provide a fake litellm completion result."""
    class FakeChoice:
        def __init__(self):
            self.message = type("Message", (), {"content": "Hello!"})()

    class FakeResult:
        def __init__(self):
            self.choices = [FakeChoice()]

    return FakeResult()
