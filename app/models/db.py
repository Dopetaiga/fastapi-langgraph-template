"""SQLAlchemy ORM models for application tables."""
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.engine import Base


class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    team_id = Column(String, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    metadata_ = Column("metadata", JSONB, default=dict)


class RunModel(Base):
    __tablename__ = "runs"

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True)
    status = Column(Enum("queued", "running", "paused", "completed", "failed", "cancelled", name="run_status"), index=True)
    graph_name = Column(String)
    graph_version = Column(String, nullable=False, default="1")
    graph_definition_hash = Column(String, nullable=True)
    graph_snapshot = Column(JSONB, nullable=True)
    input_text = Column(Text)
    output_text = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    step_count = Column(Integer, default=0)
    termination_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class JobModel(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runs.id"), index=True)
    status = Column(Enum("queued", "running", "retry_wait", "completed", "failed", name="job_status"), index=True)
    lease_owner = Column(String, nullable=True, index=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True, index=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    trace_context = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RunEventModel(Base):
    __tablename__ = "run_events"

    id = Column(String, primary_key=True)
    seq = Column(Integer, nullable=False)
    run_id = Column(String, ForeignKey("runs.id"), index=True)
    type = Column(String, index=True)
    node = Column(String, nullable=True)
    payload = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_run_event_seq"),
    )


# ---------------------------------------------------------------------------
# Phase 5–8 models
# ---------------------------------------------------------------------------

class KnowledgeBaseModel(Base):
    __tablename__ = "knowledge_bases"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text, nullable=True)
    embedding_model = Column(String, default="text-embedding-3-small")
    chunk_size = Column(Integer, default=512)
    chunk_overlap = Column(Integer, default=64)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DocumentModel(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True)
    knowledge_base_id = Column(String, ForeignKey("knowledge_bases.id"), index=True)
    filename = Column(String)
    content_type = Column(String)
    status = Column(String, default="pending")  # pending, processing, completed, failed
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunkModel(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(String, primary_key=True)
    document_id = Column(String, ForeignKey("documents.id"), index=True)
    knowledge_base_id = Column(String, ForeignKey("knowledge_bases.id"), index=True)
    content = Column(Text)
    embedding = Column(Vector(1536), nullable=True)
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ApprovalModel(Base):
    __tablename__ = "approvals"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runs.id"), index=True)
    node_id = Column(String)
    action = Column(String)
    action_id = Column(String, unique=True, nullable=True)
    tool_name = Column(String, nullable=True)
    canonical_arguments = Column(JSONB, nullable=True)
    arguments_hash = Column(String, nullable=True)
    status = Column(Enum("pending", "approved", "rejected", "expired", name="approval_status"), default="pending", index=True)
    details = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
