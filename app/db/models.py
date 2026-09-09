from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


UUID_TYPE = PostgreSQLUUID(as_uuid=True).with_variant(Uuid(as_uuid=True), "sqlite")
JSONB_TYPE = JSONB().with_variant(JSON(), "sqlite")


class ConversationMode(StrEnum):
    LIVE = "live"
    DEMONSTRATION = "demonstration"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class AssistantRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EvidenceQuality(StrEnum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    INSUFFICIENT = "insufficient"


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('live', 'demonstration')",
            name="ck_conversations_mode",
        ),
        Index("ix_conversations_updated_at", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ConversationMode.LIVE.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.sequence_number",
    )
    runs: Mapped[list[AssistantRun]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_messages_role",
        ),
        CheckConstraint(
            "sequence_number >= 1",
            name="ck_messages_sequence_positive",
        ),
        UniqueConstraint(
            "conversation_id",
            "sequence_number",
            name="uq_messages_conversation_sequence",
        ),
        Index(
            "ix_messages_conversation_created_at",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    user_runs: Mapped[list[AssistantRun]] = relationship(
        back_populates="user_message",
        foreign_keys="AssistantRun.user_message_id",
    )
    assistant_runs: Mapped[list[AssistantRun]] = relationship(
        back_populates="assistant_message",
        foreign_keys="AssistantRun.assistant_message_id",
    )


class AssistantRun(Base):
    __tablename__ = "assistant_runs"
    __table_args__ = (
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
        Index(
            "ix_assistant_runs_conversation_started",
            "conversation_id",
            "started_at",
        ),
        Index("ix_assistant_runs_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_message_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    assistant_message_id: Mapped[UUID | None] = mapped_column(
        UUID_TYPE,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=AssistantRunStatus.QUEUED.value
    )
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    integration: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    conversation: Mapped[Conversation] = relationship(back_populates="runs")
    user_message: Mapped[Message] = relationship(
        back_populates="user_runs",
        foreign_keys=[user_message_id],
    )
    assistant_message: Mapped[Message | None] = relationship(
        back_populates="assistant_runs",
        foreign_keys=[assistant_message_id],
    )
    evidence_snapshot: Mapped[EvidenceSnapshot | None] = relationship(
        back_populates="assistant_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class EvidenceSnapshot(Base):
    __tablename__ = "evidence_snapshots"
    __table_args__ = (
        CheckConstraint(
            "evidence_quality IN ('normal', 'degraded', 'insufficient')",
            name="ck_evidence_snapshots_quality",
        ),
        UniqueConstraint(
            "assistant_run_id",
            name="uq_evidence_snapshots_assistant_run",
        ),
        Index("ix_evidence_snapshots_retrieved_at", "retrieved_at"),
    )

    id: Mapped[UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    assistant_run_id: Mapped[UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("assistant_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_quality: Mapped[str] = mapped_column(String(24), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB_TYPE, nullable=False, default=dict
    )
    sources: Mapped[dict[str, Any]] = mapped_column(
        JSONB_TYPE, nullable=False, default=dict
    )
    warnings: Mapped[list[Any]] = mapped_column(
        JSONB_TYPE, nullable=False, default=list
    )
    demonstration: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    assistant_run: Mapped[AssistantRun] = relationship(
        back_populates="evidence_snapshot"
    )
