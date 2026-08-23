"""Read-only graph catalog and validation API."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.graph.compiler import compile_graph
from app.graph.schemas import AgentDefinition
from app.runtime.run_manager import RunManager

router = APIRouter(prefix="/graphs", tags=["graphs"])
_manager = RunManager(graphs_dir="graphs", use_postgres_checkpointer=False)


class GraphValidationRequest(BaseModel):
    definition: AgentDefinition


@router.get("")
async def list_graphs():
    names = sorted(path.stem for path in Path("graphs").glob("*.yaml"))
    return {"graphs": names}


@router.get("/{name}")
async def get_graph(name: str):
    try:
        compiled = _manager.load_graph(name)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return compiled.definition.model_dump(mode="json")


@router.post("/validate")
async def validate_graph(request: GraphValidationRequest):
    compiled = compile_graph(request.definition)
    return {
        "valid": True,
        "supervisor_id": compiled.supervisor_id,
        "node_count": len(compiled.node_map),
    }
