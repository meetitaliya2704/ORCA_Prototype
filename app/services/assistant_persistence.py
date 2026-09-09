from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AssistantRun, Conversation, Message, MessageRole
from app.db.repositories import AssistantRunRepository, ConversationRepository


@dataclass(frozen=True, slots=True)
class StartedAssistantTurn:
    conversation: Conversation
    user_message: Message
    run: AssistantRun


class AssistantPersistenceService:
    """Small transactional coordinator; the caller owns commit or rollback."""

    def __init__(self, session: AsyncSession) -> None:
        self.conversations = ConversationRepository(session)
        self.runs = AssistantRunRepository(session)

    async def start_turn(
        self,
        *,
        conversation_id: UUID,
        content: str,
        model: str | None = None,
        integration: str | None = None,
    ) -> StartedAssistantTurn:
        conversation = await self.conversations.require(conversation_id)
        user_message = await self.conversations.append_message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=content,
        )
        run = await self.runs.create(
            conversation_id=conversation_id,
            user_message_id=user_message.id,
            model=model,
            integration=integration,
        )
        return StartedAssistantTurn(
            conversation=conversation,
            user_message=user_message,
            run=run,
        )
