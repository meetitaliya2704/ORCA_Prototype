"""Create assistant conversation persistence tables.

Revision ID: 20260908_0001
Revises:
Create Date: 2026-09-08
"""

from collections.abc import Sequence

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260908_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        Column("title", String(200), nullable=True),
        Column("language", String(16), nullable=False),
        Column("mode", String(32), nullable=False),
        Column(
            "created_at",
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        Column(
            "updated_at",
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        CheckConstraint(
            "mode IN ('live', 'demonstration')",
            name="ck_conversations_mode",
        ),
        PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_updated_at",
        "conversations",
        ["updated_at"],
    )

    op.create_table(
        "messages",
        Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        Column("role", String(16), nullable=False),
        Column("content", Text(), nullable=False),
        Column("sequence_number", Integer(), nullable=False),
        Column(
            "created_at",
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_messages_role",
        ),
        CheckConstraint(
            "sequence_number >= 1",
            name="ck_messages_sequence_positive",
        ),
        ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint("id"),
        UniqueConstraint(
            "conversation_id",
            "sequence_number",
            name="uq_messages_conversation_sequence",
        ),
    )
    op.create_index(
        "ix_messages_conversation_created_at",
        "messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "assistant_runs",
        Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        Column("user_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        Column("assistant_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        Column("intent", String(64), nullable=True),
        Column("status", String(24), nullable=False),
        Column("model", String(100), nullable=True),
        Column("integration", String(100), nullable=True),
        Column("error_code", String(100), nullable=True),
        Column("latency_ms", Integer(), nullable=True),
        Column("input_tokens", Integer(), nullable=True),
        Column("output_tokens", Integer(), nullable=True),
        Column(
            "started_at",
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        Column("completed_at", DateTime(timezone=True), nullable=True),
        CheckConstraint(
            "intent IS NULL OR intent IN ("
            "'nearest_pfz', 'operational_conditions', 'marine_conditions', "
            "'official_alerts', 'habitat_screening', 'lower_risk_route', "
            "'productivity_analysis', 'avoidance_zones', 'source_explanation', "
            "'clarification_required', 'unsupported')",
            name="ck_assistant_runs_intent",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_assistant_runs_status",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_assistant_runs_latency_nonnegative",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_assistant_runs_input_tokens_nonnegative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_assistant_runs_output_tokens_nonnegative",
        ),
        ForeignKeyConstraint(
            ["assistant_message_id"],
            ["messages.id"],
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_message_id"],
            ["messages.id"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_assistant_runs_conversation_started",
        "assistant_runs",
        ["conversation_id", "started_at"],
    )
    op.create_index("ix_assistant_runs_status", "assistant_runs", ["status"])

    op.create_table(
        "evidence_snapshots",
        Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        Column("assistant_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        Column("evidence_quality", String(24), nullable=False),
        Column("result", postgresql.JSONB(astext_type=Text()), nullable=False),
        Column("sources", postgresql.JSONB(astext_type=Text()), nullable=False),
        Column("warnings", postgresql.JSONB(astext_type=Text()), nullable=False),
        Column(
            "demonstration",
            Boolean(),
            server_default=text("false"),
            nullable=False,
        ),
        Column("retrieved_at", DateTime(timezone=True), nullable=False),
        Column("valid_at", DateTime(timezone=True), nullable=True),
        CheckConstraint(
            "evidence_quality IN ('normal', 'degraded', 'insufficient')",
            name="ck_evidence_snapshots_quality",
        ),
        ForeignKeyConstraint(
            ["assistant_run_id"],
            ["assistant_runs.id"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint("id"),
        UniqueConstraint(
            "assistant_run_id",
            name="uq_evidence_snapshots_assistant_run",
        ),
    )
    op.create_index(
        "ix_evidence_snapshots_retrieved_at",
        "evidence_snapshots",
        ["retrieved_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evidence_snapshots_retrieved_at",
        table_name="evidence_snapshots",
    )
    op.drop_table("evidence_snapshots")
    op.drop_index("ix_assistant_runs_status", table_name="assistant_runs")
    op.drop_index(
        "ix_assistant_runs_conversation_started",
        table_name="assistant_runs",
    )
    op.drop_table("assistant_runs")
    op.drop_index(
        "ix_messages_conversation_created_at",
        table_name="messages",
    )
    op.drop_table("messages")
    op.drop_index(
        "ix_conversations_updated_at",
        table_name="conversations",
    )
    op.drop_table("conversations")
