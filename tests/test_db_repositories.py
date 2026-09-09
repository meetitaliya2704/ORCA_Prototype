from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.agents.capabilities import AssistantIntent
from app.db.base import Base
from app.db.errors import PersistenceValidationError
from app.db.models import (
    AssistantRunStatus,
    Conversation,
    ConversationMode,
    EvidenceQuality,
    MessageRole,
)
from app.db.repositories import (
    AssistantRunRepository,
    ConversationRepository,
    EvidenceSnapshotRepository,
)
from app.db.session import DatabaseSessionManager
from app.services.assistant_persistence import AssistantPersistenceService


@pytest.fixture
async def database():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


async def test_conversation_and_ordered_messages_persist(database) -> None:
    _, factory = database
    async with factory.begin() as session:
        repository = ConversationRepository(session)
        conversation = await repository.create(
            title="Gujarat evidence",
            language="gu",
            mode=ConversationMode.LIVE,
        )
        first = await repository.append_message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="First question",
        )
        second = await repository.append_message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="Deterministic response",
        )
        assert (first.sequence_number, second.sequence_number) == (1, 2)

    async with factory() as session:
        loaded = await ConversationRepository(session).get(
            conversation.id, include_messages=True
        )
        assert loaded is not None
        assert loaded.language == "gu"
        assert [message.sequence_number for message in loaded.messages] == [1, 2]


async def test_assistant_run_completion_and_json_evidence(database) -> None:
    _, factory = database
    async with factory.begin() as session:
        conversations = ConversationRepository(session)
        conversation = await conversations.create()
        started = await AssistantPersistenceService(session).start_turn(
            conversation_id=conversation.id,
            content="Assess the configured limits",
        )
        assistant_message = await conversations.append_message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="Available evidence was evaluated.",
        )
        completed = await AssistantRunRepository(session).complete(
            run_id=started.run.id,
            status=AssistantRunStatus.SUCCEEDED,
            intent=AssistantIntent.OPERATIONAL_CONDITIONS,
            assistant_message_id=assistant_message.id,
            latency_ms=12,
            input_tokens=20,
            output_tokens=8,
        )
        payload = {"status": "partial", "evidence": {"waves": {"value": 1.2}}}
        snapshot = await EvidenceSnapshotRepository(session).save(
            assistant_run_id=completed.id,
            evidence_quality=EvidenceQuality.DEGRADED,
            result=payload,
            sources={"waves": {"provider": "fixture"}},
            warnings=["Saved fixture warning"],
            demonstration=False,
            retrieved_at=datetime.now(UTC),
        )
        payload["status"] = "mutated-after-save"
        assert snapshot.result["status"] == "partial"

    async with factory() as session:
        loaded_run = await AssistantRunRepository(session).get(completed.id)
        loaded_snapshot = await EvidenceSnapshotRepository(session).get_for_run(
            completed.id
        )
        assert loaded_run is not None
        assert loaded_run.status == AssistantRunStatus.SUCCEEDED.value
        assert loaded_run.completed_at is not None
        assert loaded_snapshot is not None
        assert loaded_snapshot.result["status"] == "partial"
        assert loaded_snapshot.sources["waves"]["provider"] == "fixture"


async def test_session_manager_rolls_back_failed_transaction(database) -> None:
    engine, factory = database
    manager = object.__new__(DatabaseSessionManager)
    manager.engine = engine
    manager.session_factory = factory

    with pytest.raises(RuntimeError, match="force rollback"):
        async with manager.session() as session:
            session.add(Conversation(language="en", mode="live"))
            await session.flush()
            raise RuntimeError("force rollback")

    async with factory() as session:
        assert list(await session.scalars(select(Conversation))) == []


async def test_evidence_rejects_sensitive_and_non_finite_json(database) -> None:
    _, factory = database
    async with factory.begin() as session:
        conversation = await ConversationRepository(session).create()
        started = await AssistantPersistenceService(session).start_turn(
            conversation_id=conversation.id,
            content="Persist bounded evidence",
        )
        repository = EvidenceSnapshotRepository(session)
        common = {
            "assistant_run_id": started.run.id,
            "evidence_quality": EvidenceQuality.NORMAL,
            "sources": {},
            "warnings": [],
            "demonstration": False,
            "retrieved_at": datetime.now(UTC),
        }
        with pytest.raises(PersistenceValidationError, match="sensitive"):
            await repository.save(
                result={"token": "must-not-persist"},
                **common,
            )
        with pytest.raises(PersistenceValidationError, match="finite"):
            await repository.save(
                result={"value": float("nan")},
                **common,
            )
