"""Alembic migration: add Phase 5-8 tables."""
from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers
revision = "001_add_phase5_8_tables"
down_revision = "000_bootstrap_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # knowledge_bases
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(), server_default="text-embedding-3-small"),
        sa.Column("chunk_size", sa.Integer(), server_default="512"),
        sa.Column("chunk_overlap", sa.Integer(), server_default="64"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_kb_name"),
    )
    op.create_index("ix_knowledge_bases_name", "knowledge_bases", ["name"])

    # documents
    op.create_table(
        "documents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("knowledge_base_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending"),
        sa.Column("chunk_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_kb_id", "documents", ["knowledge_base_id"])

    # knowledge_chunks with pgvector embedding
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("knowledge_base_id", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chunks_kb_id", "knowledge_chunks", ["knowledge_base_id"])
    op.create_index("ix_chunks_doc_id", "knowledge_chunks", ["document_id"])
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # approvals
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("node_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("action_id", sa.String(), nullable=True),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("canonical_arguments", JSONB, nullable=True),
        sa.Column("arguments_hash", sa.String(), nullable=True),
        sa.Column("status", sa.String(), server_default="pending"),
        sa.Column("details", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approvals_run_id", "approvals", ["run_id"])
    op.create_index("ix_approvals_status", "approvals", ["status"])
    op.create_index("uq_approvals_action_id", "approvals", ["action_id"], unique=True)

def downgrade() -> None:
    op.drop_table("approvals")
    op.drop_table("knowledge_chunks")
    op.drop_table("documents")
    op.drop_table("knowledge_bases")
    op.execute("DROP EXTENSION IF EXISTS vector")
