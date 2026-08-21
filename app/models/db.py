"""SQLAlchemy ORM models for application tables."""
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
    status = Column(Enum("queued", "running", "completed", "failed", name="job_status"), index=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
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
    embedding = Column(ARRAY(Float), nullable=True)  # pgvector column
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ApprovalModel(Base):
    __tablename__ = "approvals"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runs.id"), index=True)
    node_id = Column(String)
    action = Column(String)
    status = Column(Enum("pending", "approved", "rejected", "expired", name="approval_status"), default="pending", index=True)
    details = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String, nullable=True)
    reason = Column(Text, nullable=True)


class UserMemoryModel(Base):
    __tablename__ = "user_memory"

    id = Column(String, primary_key=True)
    user_id = Column(String, index=True)
    key = Column(String)
    value = Column(JSONB)
    namespace = Column(String, default="user")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "key", "namespace", name="uq_user_memory_key"),
    )


class TeamMemoryModel(Base):
    __tablename__ = "team_memory"

    id = Column(String, primary_key=True)
    team_id = Column(String, index=True)
    key = Column(String)
    value = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("team_id", "key", name="uq_team_memory_key"),
    )
