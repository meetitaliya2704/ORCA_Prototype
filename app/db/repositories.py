from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.capabilities import AssistantIntent
from app.db.errors import PersistenceNotFoundError, PersistenceValidationError
from app.db.models import (
    AssistantRun,
    AssistantRunStatus,
    Conversation,
    ConversationMode,
    EvidenceQuality,
    EvidenceSnapshot,
    Message,
    MessageRole,
)

SAFE_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")
MAX_EVIDENCE_JSON_BYTES = 1_000_000
SENSITIVE_JSON_KEYS = {
    "api_key",
    "authorization",
    "credential",
    "database_url",
    "password",
    "secret",
    "token",
}


def _validate_json_payload(name: str, value: Any) -> None:
    def inspect(item: Any) -> None:
        if isinstance(item, BaseException):
            raise PersistenceValidationError(
                f"{name} must not contain exception objects"
            )
        if isinstance(item, dict):
            for key, child in item.items():
                if str(key).strip().lower() in SENSITIVE_JSON_KEYS:
                    raise PersistenceValidationError(
                        f"{name} contains a prohibited sensitive field"
                    )
                inspect(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                inspect(child)

    inspect(value)
    try:
        encoded = json.dumps(value, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise PersistenceValidationError(
            f"{name} must contain finite JSON-compatible data"
        ) from None
    if len(encoded.encode("utf-8")) > MAX_EVIDENCE_JSON_BYTES:
        raise PersistenceValidationError(
            f"{name} exceeds the normalized evidence size limit"
        )


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        title: str | None = None,
        language: str = "en",
        mode: ConversationMode = ConversationMode.LIVE,
    ) -> Conversation:
        normalized_language = language.strip()
        if not normalized_language or len(normalized_language) > 16:
            raise PersistenceValidationError("Conversation language is invalid")
        conversation = Conversation(
            title=title.strip() if title and title.strip() else None,
            language=normalized_language,
            mode=mode.value,
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get(
        self,
        conversation_id: UUID,
        *,
        include_messages: bool = False,
    ) -> Conversation | None:
        statement = select(Conversation).where(Conversation.id == conversation_id)
        if include_messages:
            statement = statement.options(selectinload(Conversation.messages))
        return await self.session.scalar(statement)

    async def require(self, conversation_id: UUID) -> Conversation:
        conversation = await self.get(conversation_id)
        if conversation is None:
            raise PersistenceNotFoundError("conversation")
        return conversation

    async def append_message(
        self,
        *,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
    ) -> Message:
        normalized_content = content.strip()
        if not normalized_content:
            raise PersistenceValidationError("Message content must not be empty")
        conversation = await self.session.scalar(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .with_for_update()
        )
        if conversation is None:
            raise PersistenceNotFoundError("conversation")
        last_sequence = await self.session.scalar(
            select(func.max(Message.sequence_number)).where(
                Message.conversation_id == conversation_id
            )
        )
        message = Message(
            conversation_id=conversation_id,
            role=role.value,
            content=normalized_content,
            sequence_number=(last_sequence or 0) + 1,
        )
        conversation.updated_at = datetime.now(UTC)
        self.session.add(message)
        await self.session.flush()
        return message


class AssistantRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        conversation_id: UUID,
        user_message_id: UUID,
        model: str | None = None,
        integration: str | None = None,
    ) -> AssistantRun:
        user_message = await self.session.get(Message, user_message_id)
        if (
            user_message is None
            or user_message.conversation_id != conversation_id
            or user_message.role != MessageRole.USER.value
        ):
            raise PersistenceValidationError(
                "Assistant run requires a user message in the same conversation"
            )
        run = AssistantRun(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            status=AssistantRunStatus.QUEUED.value,
            model=model,
            integration=integration,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def get(self, run_id: UUID) -> AssistantRun | None:
        return await self.session.get(AssistantRun, run_id)

    async def mark_running(self, run_id: UUID) -> AssistantRun:
        run = await self._require(run_id)
        run.status = AssistantRunStatus.RUNNING.value
        await self.session.flush()
        return run

    async def complete(
        self,
        *,
        run_id: UUID,
        status: AssistantRunStatus,
        intent: AssistantIntent | None = None,
        assistant_message_id: UUID | None = None,
        error_code: str | None = None,
        latency_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        completed_at: datetime | None = None,
    ) -> AssistantRun:
        if status not in {
            AssistantRunStatus.SUCCEEDED,
            AssistantRunStatus.FAILED,
            AssistantRunStatus.CANCELLED,
        }:
            raise PersistenceValidationError(
                "Assistant run completion status is invalid"
            )
        for field_name, value in (
            ("latency_ms", latency_ms),
            ("input_tokens", input_tokens),
            ("output_tokens", output_tokens),
        ):
            if value is not None and value < 0:
                raise PersistenceValidationError(f"{field_name} must not be negative")
        if error_code is not None and not SAFE_ERROR_CODE.fullmatch(error_code):
            raise PersistenceValidationError("Assistant run error code is invalid")

        run = await self._require(run_id)
        if assistant_message_id is not None:
            assistant_message = await self.session.get(Message, assistant_message_id)
            if (
                assistant_message is None
                or assistant_message.conversation_id != run.conversation_id
                or assistant_message.role != MessageRole.ASSISTANT.value
            ):
                raise PersistenceValidationError(
                    "Assistant message must belong to the run conversation"
                )
        run.status = status.value
        run.intent = intent.value if intent is not None else None
        run.assistant_message_id = assistant_message_id
        run.error_code = error_code
        run.latency_ms = latency_ms
        run.input_tokens = input_tokens
        run.output_tokens = output_tokens
        run.completed_at = completed_at or datetime.now(UTC)
        await self.session.flush()
        return run

    async def _require(self, run_id: UUID) -> AssistantRun:
        run = await self.get(run_id)
        if run is None:
            raise PersistenceNotFoundError("assistant run")
        return run


class EvidenceSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(
        self,
        *,
        assistant_run_id: UUID,
        evidence_quality: EvidenceQuality,
        result: dict[str, Any],
        sources: dict[str, Any],
        warnings: list[Any],
        demonstration: bool,
        retrieved_at: datetime,
        valid_at: datetime | None = None,
    ) -> EvidenceSnapshot:
        if not isinstance(result, dict) or not isinstance(sources, dict):
            raise PersistenceValidationError(
                "Evidence result and sources must be JSON objects"
            )
        if not isinstance(warnings, list):
            raise PersistenceValidationError("Evidence warnings must be a JSON array")
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise PersistenceValidationError("retrieved_at must be timezone-aware")
        if valid_at is not None and (
            valid_at.tzinfo is None or valid_at.utcoffset() is None
        ):
            raise PersistenceValidationError("valid_at must be timezone-aware")
        if await self.session.get(AssistantRun, assistant_run_id) is None:
            raise PersistenceNotFoundError("assistant run")
        _validate_json_payload("result", result)
        _validate_json_payload("sources", sources)
        _validate_json_payload("warnings", warnings)
        existing = await self.get_for_run(assistant_run_id)
        if existing is not None:
            raise PersistenceValidationError(
                "An evidence snapshot already exists for this assistant run"
            )
        snapshot = EvidenceSnapshot(
            assistant_run_id=assistant_run_id,
            evidence_quality=evidence_quality.value,
            result=deepcopy(result),
            sources=deepcopy(sources),
            warnings=deepcopy(warnings),
            demonstration=demonstration,
            retrieved_at=retrieved_at,
            valid_at=valid_at,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def get_for_run(self, assistant_run_id: UUID) -> EvidenceSnapshot | None:
        return await self.session.scalar(
            select(EvidenceSnapshot).where(
                EvidenceSnapshot.assistant_run_id == assistant_run_id
            )
        )
