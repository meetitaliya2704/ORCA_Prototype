from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import SecretStr

from app.agents.capabilities import AssistantIntent
from app.schemas.assistant import (
    AssistantConversationMessage,
    AssistantResponseStatus,
)


_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi (हिंदी)",
    "gu": "Gujarati (ગુજરાતી)",
    "mr": "Marathi (मराठी)",
    "ta": "Tamil (தமிழ்)",
    "te": "Telugu (తెలుగు)",
    "ml": "Malayalam (മലയാളം)",
    "bn": "Bengali (বাংলা)",
}


class LLMResponseExplainer:
    """Conversational natural-language explainer for ORCA marine decisions and guidance."""

    def __init__(
        self,
        *,
        provider: str = "openrouter",
        api_key: SecretStr,
        model: str = "nex-agi/nex-n2.5-mini:free",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 12.0,
        max_tokens: int = 500,
        temperature: float = 0.3,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.provider = provider.strip().lower()
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._http_client = http_client

    async def explain(
        self,
        *,
        message: str,
        language: str,
        intent: AssistantIntent,
        deterministic_answer: str,
        status: AssistantResponseStatus,
        recent_messages: tuple[AssistantConversationMessage, ...] = (),
    ) -> str | None:
        """Generate a natural conversational response in the user's language.

        Returns None on any error or timeout so the caller safely uses the
        deterministic answer.
        """
        try:
            if self.provider == "openrouter":
                return await self._explain_openrouter(
                    message=message,
                    language=language,
                    intent=intent,
                    deterministic_answer=deterministic_answer,
                    status=status,
                    recent_messages=recent_messages,
                )
            if self.provider == "gemini":
                return await self._explain_gemini(
                    message=message,
                    language=language,
                    intent=intent,
                    deterministic_answer=deterministic_answer,
                    status=status,
                    recent_messages=recent_messages,
                )
        except Exception:
            return None
        return None

    def _build_system_prompt(self, language: str) -> str:
        lang_name = _LANGUAGE_NAMES.get(language, "English")
        return (
            "You are ORCA, an intelligent maritime decision-support assistant for fishermen, "
            "coastal navigators, and vessel operators.\n"
            f"You MUST respond fluently and naturally in {lang_name}.\n\n"
            "MANDATORY OPERATIONAL RULES:\n"
            "1. When verified marine findings, wave heights, wind speeds, ocean currents, "
            "SST, PFZ coordinates, or vessel limit assessments are provided, you MUST ground your "
            "response strictly in those numbers and statuses. NEVER invent, contradict, or alter "
            "any coordinates, measurements, or safety evaluations.\n"
            "2. If the user greets you or asks a general conversational question (e.g. 'Hello', "
            "'Who are you?', 'What is a PFZ?', 'How do ocean currents affect fishing?'), answer "
            f"politely, warmly, and helpfully in {lang_name}, explaining what ORCA does or addressing "
            "their marine topic clearly.\n"
            "3. Answer the user's specific natural language question directly in conversational prose "
            f"in {lang_name}. If verified data was computed, explain the outcome conversationally first, "
            "then summarize the key readings or bulletin details clearly.\n"
            "4. Never output raw JSON or code blocks. Present your advice cleanly and practically "
            "for someone planning to go to sea."
        )

    def _build_user_prompt(
        self,
        *,
        message: str,
        language: str,
        intent: AssistantIntent,
        deterministic_answer: str,
        status: AssistantResponseStatus,
    ) -> str:
        lang_name = _LANGUAGE_NAMES.get(language, "English")
        return (
            f"User's Question: {message}\n"
            f"Target Language: {lang_name}\n"
            f"Intent: {intent.value}\n"
            f"Outcome Status: {status.value}\n\n"
            "Verified Facts from Official Calculations:\n"
            f"{deterministic_answer}\n\n"
            f"Please give a natural, helpful response to the user in {lang_name} addressing "
            "their query directly while keeping all verified facts accurate."
        )

    async def _explain_openrouter(
        self,
        *,
        message: str,
        language: str,
        intent: AssistantIntent,
        deterministic_answer: str,
        status: AssistantResponseStatus,
        recent_messages: tuple[AssistantConversationMessage, ...],
    ) -> str | None:
        system_prompt = self._build_system_prompt(language)
        user_prompt = self._build_user_prompt(
            message=message,
            language=language,
            intent=intent,
            deterministic_answer=deterministic_answer,
            status=status,
        )

        messages_payload: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

        # Include up to 4 recent messages for conversational continuity
        for prev in recent_messages[-4:]:
            role = "assistant" if prev.role == "assistant" else "user"
            messages_payload.append({"role": role, "content": prev.content})

        messages_payload.append({"role": "user", "content": user_prompt})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages_payload,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://orca-marine.org",
            "X-Title": "ORCA Marine Decision Support",
        }

        if self._http_client is not None:
            response = await self._http_client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )

        if response.status_code != 200:
            return None

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content", "")
        return content.strip() if content and content.strip() else None

    async def _explain_gemini(
        self,
        *,
        message: str,
        language: str,
        intent: AssistantIntent,
        deterministic_answer: str,
        status: AssistantResponseStatus,
        recent_messages: tuple[AssistantConversationMessage, ...],
    ) -> str | None:
        try:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            return None

        chat_kwargs: dict[str, Any] = {
            "model": self.model,
            "google_api_key": self.api_key.get_secret_value(),
            "vertexai": False,
            "temperature": self.temperature,
            "max_retries": 0,
            "timeout": self.timeout_seconds,
            "max_output_tokens": self.max_tokens,
        }
        try:
            chat_model = ChatGoogleGenerativeAI(**chat_kwargs, thinking_budget=0)
        except (TypeError, ValueError):
            chat_model = ChatGoogleGenerativeAI(**chat_kwargs)

        system_prompt = self._build_system_prompt(language)
        user_prompt = self._build_user_prompt(
            message=message,
            language=language,
            intent=intent,
            deterministic_answer=deterministic_answer,
            status=status,
        )

        messages: list[Any] = [SystemMessage(content=system_prompt)]
        for prev in recent_messages[-4:]:
            if prev.role == "assistant":
                messages.append(AIMessage(content=prev.content))
            else:
                messages.append(HumanMessage(content=prev.content))
        messages.append(HumanMessage(content=user_prompt))

        async with asyncio.timeout(self.timeout_seconds):
            resp = await chat_model.ainvoke(messages)
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            return text.strip() if text and text.strip() else None

