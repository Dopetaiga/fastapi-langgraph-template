"""YAML loader for AgentDefinition."""
from __future__ import annotations

from pathlib import Path

import yaml

from app.graph.schemas import AgentDefinition


def load_graph_from_yaml(path: str | Path) -> AgentDefinition:
    """Load and validate an AgentDefinition from a YAML file."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return AgentDefinition.model_validate(raw)
