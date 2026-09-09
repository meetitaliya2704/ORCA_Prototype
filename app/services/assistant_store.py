from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.capabilities import AssistantIntent
from app.db.errors import (
    DatabaseOperationError,
    PersistenceValidationError,
    sanitize_database_error,
)
from app.db.models import (
    AssistantRun,
    AssistantRunStatus,
    ConversationMode,
    EvidenceQuality,
    EvidenceSnapshot,
    MessageRole,
)
from app.db.repositories import (
    AssistantRunRepository,
    ConversationRepository,
    EvidenceSnapshotRepository,
)


@dataclass(frozen=True, slots=True)
class AssistantTurnReferences:
    conversation_id: UUID
    user_message_id: UUID
    run_id: UUID


class AssistantPersistencePort(Protocol):
    async def begin_turn(
        self,
        *,
        conversation_id: UUID | None,
        content: str,
        language: str,
        mode: ConversationMode,
        model: str | None,
        integration: str,
    ) -> AssistantTurnReferences: ...

    async def finalize_turn(
        self,
        *,
        references: AssistantTurnReferences,
        assistant_content: str,
        intent: AssistantIntent,
        run_status: AssistantRunStatus,
        latency_ms: int,
        input_tokens: int | None,
        output_tokens: int | None,
        evidence_quality: EvidenceQuality | None,
        result: dict[str, Any],
        sources: dict[str, Any],
        warnings: list[Any],
        demonstration: bool,
        retrieved_at: datetime,
        valid_at: datetime | None,
    ) -> UUID: ...

    async def fail_turn(
        self,
        *,
        references: AssistantTurnReferences,
        error_code: str,
        latency_ms: int,
        cancelled: bool = False,
    ) -> None: ...

    async def latest_sources(self, conversation_id: UUID) -> dict[str, Any]: ...

    async def latest_intent(self, conversation_id: UUID) -> AssistantIntent | None: ...


class SQLAlchemyAssistantPersistence:
    """Short transactions around potentially slow model/provider work."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def begin_turn(
        self,
        *,
        conversation_id: UUID | None,
        content: str,
        language: str,
        mode: ConversationMode,
        model: str | None,
        integration: str,
    ) -> AssistantTurnReferences:
        try:
            async with self.session_factory.begin() as session:
                conversations = ConversationRepository(session)
                conversation = (
                    await conversations.create(language=language, mode=mode)
                    if conversation_id is None
                    else await conversations.require(conversation_id)
                )
                if conversation.mode != mode.value:
                    raise PersistenceValidationError(
                        "Conversation mode cannot change between turns"
                    )
                user_message = await conversations.append_message(
                    conversation_id=conversation.id,
                    role=MessageRole.USER,
                    content=content,
                )
                runs = AssistantRunRepository(session)
                run = await runs.create(
                    conversation_id=conversation.id,
                    user_message_id=user_message.id,
                    model=model,
                    integration=integration,
                )
                await runs.mark_running(run.id)
                return AssistantTurnReferences(
                    conversation_id=conversation.id,
                    user_message_id=user_message.id,
                    run_id=run.id,
                )
        except DatabaseOperationError:
            raise
        except SQLAlchemyError as exc:
            raise DatabaseOperationError(sanitize_database_error(exc)) from None

    async def finalize_turn(
        self,
        *,
        references: AssistantTurnReferences,
        assistant_content: str,
        intent: AssistantIntent,
        run_status: AssistantRunStatus,
        latency_ms: int,
        input_tokens: int | None,
        output_tokens: int | None,
        evidence_quality: EvidenceQuality | None,
        result: dict[str, Any],
        sources: dict[str, Any],
        warnings: list[Any],
        demonstration: bool,
        retrieved_at: datetime,
        valid_at: datetime | None,
    ) -> UUID:
        try:
            async with self.session_factory.begin() as session:
                conversations = ConversationRepository(session)
                assistant_message = await conversations.append_message(
                    conversation_id=references.conversation_id,
                    role=MessageRole.ASSISTANT,
                    content=assistant_content,
                )
                await AssistantRunRepository(session).complete(
                    run_id=references.run_id,
                    status=run_status,
                    intent=intent,
                    assistant_message_id=assistant_message.id,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                if evidence_quality is not None:
                    await EvidenceSnapshotRepository(session).save(
                        assistant_run_id=references.run_id,
                        evidence_quality=evidence_quality,
                        result=result,
                        sources=sources,
                        warnings=warnings,
                        demonstration=demonstration,
                        retrieved_at=retrieved_at,
                        valid_at=valid_at,
                    )
                return assistant_message.id
        except DatabaseOperationError:
            raise
        except SQLAlchemyError as exc:
            raise DatabaseOperationError(sanitize_database_error(exc)) from None

    async def fail_turn(
        self,
        *,
        references: AssistantTurnReferences,
        error_code: str,
        latency_ms: int,
        cancelled: bool = False,
    ) -> None:
        try:
            async with self.session_factory.begin() as session:
                await AssistantRunRepository(session).complete(
                    run_id=references.run_id,
                    status=(
                        AssistantRunStatus.CANCELLED
                        if cancelled
                        else AssistantRunStatus.FAILED
                    ),
                    error_code=error_code,
                    latency_ms=latency_ms,
                )
        except (DatabaseOperationError, SQLAlchemyError):
            return

    async def latest_sources(self, conversation_id: UUID) -> dict[str, Any]:
        try:
            async with self.session_factory() as session:
                snapshot = await session.scalar(
                    select(EvidenceSnapshot)
                    .join(AssistantRun)
                    .where(AssistantRun.conversation_id == conversation_id)
                    .order_by(AssistantRun.started_at.desc())
                    .limit(1)
                )
                return dict(snapshot.sources) if snapshot is not None else {}
        except SQLAlchemyError as exc:
            raise DatabaseOperationError(sanitize_database_error(exc)) from None

    async def latest_intent(self, conversation_id: UUID) -> AssistantIntent | None:
        try:
            async with self.session_factory() as session:
                value = await session.scalar(
                    select(AssistantRun.intent)
                    .where(
                        AssistantRun.conversation_id == conversation_id,
                        AssistantRun.intent.is_not(None),
                    )
                    .order_by(AssistantRun.started_at.desc())
                    .limit(1)
                )
                return AssistantIntent(value) if value is not None else None
        except SQLAlchemyError as exc:
            raise DatabaseOperationError(sanitize_database_error(exc)) from None
