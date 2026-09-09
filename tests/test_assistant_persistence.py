from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.agents.capabilities import AssistantIntent
from app.db.base import Base
from app.db.models import (
    AssistantRun,
    AssistantRunStatus,
    ConversationMode,
    EvidenceQuality,
    Message,
)
from app.services.assistant_store import SQLAlchemyAssistantPersistence


@pytest.fixture
async def store():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield SQLAlchemyAssistantPersistence(factory), factory
    finally:
        await engine.dispose()


async def test_turn_is_persisted_in_order_and_can_continue(store):
    persistence, factory = store
    started = await persistence.begin_turn(
        conversation_id=None,
        content="First question",
        language="en",
        mode=ConversationMode.LIVE,
        model=None,
        integration="deterministic_fallback",
    )
    assistant_id = await persistence.finalize_turn(
        references=started,
        assistant_content="Deterministic answer",
        intent=AssistantIntent.MARINE_CONDITIONS,
        run_status=AssistantRunStatus.SUCCEEDED,
        latency_ms=12,
        input_tokens=None,
        output_tokens=None,
        evidence_quality=EvidenceQuality.NORMAL,
        result={"status": "complete"},
        sources={"waves": {"source": "waves", "state": "available"}},
        warnings=[],
        demonstration=False,
        retrieved_at=datetime.now(UTC),
        valid_at=datetime.now(UTC),
    )
    continued = await persistence.begin_turn(
        conversation_id=started.conversation_id,
        content="Explain the sources",
        language="en",
        mode=ConversationMode.LIVE,
        model=None,
        integration="deterministic_fallback",
    )
    assert continued.conversation_id == started.conversation_id
    assert await persistence.latest_sources(started.conversation_id) == {
        "waves": {"source": "waves", "state": "available"}
    }
    assert (
        await persistence.latest_intent(started.conversation_id)
        == AssistantIntent.MARINE_CONDITIONS
    )
    async with factory() as session:
        messages = list(
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == started.conversation_id)
                .order_by(Message.sequence_number)
            )
        )
        assert [message.sequence_number for message in messages] == [1, 2, 3]
        assert messages[1].id == assistant_id


async def test_failed_run_records_only_safe_error_code(store):
    persistence, factory = store
    started = await persistence.begin_turn(
        conversation_id=None,
        content="Question",
        language="gu",
        mode=ConversationMode.LIVE,
        model="gemini-3.7-flash",
        integration="gemini_function_call_with_deterministic_fallback",
    )
    await persistence.fail_turn(
        references=started,
        error_code="ASSISTANT_ROUTER_TIMEOUT",
        latency_ms=20,
    )
    async with factory() as session:
        run = await session.get(AssistantRun, started.run_id)
        assert run.status == "failed"
        assert run.error_code == "ASSISTANT_ROUTER_TIMEOUT"
        assert run.assistant_message_id is None


async def test_cancelled_turn_records_cancelled_status(store):
    persistence, factory = store
    started = await persistence.begin_turn(
        conversation_id=None,
        content="Question",
        language="en",
        mode=ConversationMode.LIVE,
        model=None,
        integration="deterministic_fallback",
    )
    await persistence.fail_turn(
        references=started,
        error_code="ASSISTANT_REQUEST_CANCELLED",
        latency_ms=3,
        cancelled=True,
    )
    async with factory() as session:
        run = await session.get(AssistantRun, started.run_id)
        assert run.status == "cancelled"
        assert run.error_code == "ASSISTANT_REQUEST_CANCELLED"
