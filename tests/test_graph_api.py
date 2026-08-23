from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_graph_catalog_exposes_valid_default_graph():
    client = TestClient(create_app())
    catalog = client.get("/graphs")
    graph = client.get("/graphs/default")
    assert catalog.status_code == 200
    assert "default" in catalog.json()["graphs"]
    assert graph.status_code == 200
    assert graph.json()["name"] == "default"
    assert sum(node["type"] == "supervisor" for node in graph.json()["nodes"]) == 1


def test_graph_catalog_rejects_path_traversal():
    response = TestClient(create_app()).get("/graphs/..%2Fsecret")
    assert response.status_code == 404
