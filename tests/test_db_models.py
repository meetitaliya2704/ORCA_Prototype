from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql

from app.db.base import Base
from app.db.models import AssistantRun, Conversation, EvidenceSnapshot, Message


def test_expected_tables_and_relationships_are_declared() -> None:
    assert set(Base.metadata.tables) == {
        "conversations",
        "messages",
        "assistant_runs",
        "evidence_snapshots",
    }
    assert next(
        iter(Message.__table__.c.conversation_id.foreign_keys)
    ).target_fullname == ("conversations.id")
    assert next(
        iter(AssistantRun.__table__.c.user_message_id.foreign_keys)
    ).target_fullname == ("messages.id")
    assert (
        next(
            iter(EvidenceSnapshot.__table__.c.assistant_run_id.foreign_keys)
        ).target_fullname
        == "assistant_runs.id"
    )


def test_models_use_postgresql_uuid_timestamptz_and_jsonb() -> None:
    dialect = postgresql.dialect()
    assert Conversation.__table__.c.id.type.compile(dialect=dialect) == "UUID"
    assert (
        Conversation.__table__.c.created_at.type.compile(dialect=dialect)
        == "TIMESTAMP WITH TIME ZONE"
    )
    assert EvidenceSnapshot.__table__.c.result.type.compile(dialect=dialect) == "JSONB"
    assert EvidenceSnapshot.__table__.c.sources.type.compile(dialect=dialect) == "JSONB"
    assert (
        EvidenceSnapshot.__table__.c.warnings.type.compile(dialect=dialect) == "JSONB"
    )


def test_controlled_values_and_uniqueness_are_database_constraints() -> None:
    conversation_checks = {
        constraint.name
        for constraint in Conversation.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    message_constraints = Message.__table__.constraints
    evidence_constraints = EvidenceSnapshot.__table__.constraints
    assert "ck_conversations_mode" in conversation_checks
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_messages_conversation_sequence"
        for constraint in message_constraints
    )
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_evidence_snapshots_assistant_run"
        for constraint in evidence_constraints
    )
