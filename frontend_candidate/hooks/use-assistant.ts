"use client";

import demoConversationJson from "@/public/demo/conversation.json";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { OrcaApiError } from "@/lib/api/client";
import {
  DemoAssistantTransport,
  DisabledAssistantTransport,
  HttpAssistantTransport,
} from "@/lib/assistant/transport";
import {
  demonstrationConversationSchema,
  type AssistantMessage,
  type AssistantMode,
} from "@/lib/schemas/assistant";
import type {
  AssistantApiResponse,
  AssistantContextValues,
  AssistantLanguage,
} from "@/lib/schemas/assistant-api";
import type { JourneyResponse } from "@/lib/schemas/journey";
import { useChatSessions, type ConversationSession } from "@/lib/chat-session-context";

export type { ConversationSession };

const parsedFixture = demonstrationConversationSchema.safeParse(demoConversationJson);

export function useAssistant(
  mode: AssistantMode,
  language: AssistantLanguage,
  context: AssistantContextValues,
  userId: string = "guest",
) {
  const {
    sessions,
    activeSessionId,
    activeSession,
    startNewChat: contextStartNewChat,
    switchSession: contextSwitchSession,
    deleteSession: contextDeleteSession,
    saveActiveSession,
  } = useChatSessions();

  const [messages, setMessages] = useState<AssistantMessage[]>(() => activeSession?.messages || []);
  const [busy, setBusy] = useState(false);
  const [fixtureError, setFixtureError] = useState(!parsedFixture.success);
  const [latestResponse, setLatestResponse] = useState<AssistantApiResponse | null>(() => activeSession?.latestResponse || null);
  const [conversationId, setConversationId] = useState<string | null>(() => activeSession?.conversationId || null);
  const [lastError, setLastError] = useState<OrcaApiError | null>(null);
  const controller = useRef<AbortController | null>(null);
  const lastRequest = useRef<{ text: string; actionId?: string } | null>(null);
  const currentSessionIdRef = useRef<string>(activeSessionId);
  const isHydrated = useRef(false);

  // Sync state ONLY when activeSessionId actually changes
  useEffect(() => {
    currentSessionIdRef.current = activeSessionId;
    const target = sessions.find((s) => s.id === activeSessionId);
    if (target) {
      setMessages(target.messages || []);
      setConversationId(target.conversationId || null);
      setLatestResponse(target.latestResponse || null);
    } else {
      setMessages([]);
      setConversationId(null);
      setLatestResponse(null);
    }
    setLastError(null);
    lastRequest.current = null;
    isHydrated.current = true;
  }, [activeSessionId]);

  // Sync messages, conversationId, and latestResponse to the active session in context
  useEffect(() => {
    if (!isHydrated.current) return;
    if (messages.length === 0) return;
    saveActiveSession(messages, conversationId, latestResponse, activeSessionId);
  }, [messages, conversationId, latestResponse, activeSessionId, saveActiveSession]);

  const transport = useMemo(() => {
    if (mode === "live") return new HttpAssistantTransport();
    if (mode === "demo" && parsedFixture.success) return new DemoAssistantTransport(parsedFixture.data);
    return new DisabledAssistantTransport();
  }, [mode]);

  const send = useCallback(async (text: string, actionId?: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    controller.current?.abort();
    const active = new AbortController();
    controller.current = active;
    lastRequest.current = { text: trimmed, actionId };
    setLastError(null);

    const userMessage: AssistantMessage = {
      id: `user-${crypto.randomUUID()}`,
      kind: "user",
      role: "user",
      mode: mode === "demo" ? "demonstration" : mode === "live" ? "live" : "deterministic",
      content: trimmed,
      created_at: new Date().toISOString(),
      evidence_references: [],
      warnings: [],
      suggested_actions: [],
    };
    const recentMessages = messages
      .filter((message) => message.role === "user" || message.role === "assistant")
      .slice(-20)
      .map((message) => ({ role: message.role as "user" | "assistant", content: message.content }));
    setMessages((current) => [...current, userMessage]);
    setBusy(true);

    try {
      const result = await transport.send({
        text: trimmed,
        actionId,
        conversationId,
        preferredLanguage: language,
        context,
        recentMessages,
      }, active.signal);
      if (active.signal.aborted) return;
      setMessages((current) => [...current, ...result.messages]);
      if (result.response) {
        setLatestResponse(result.response);
        setConversationId(result.response.conversation_id);
      }
    } catch (error) {
      const cancelled = error instanceof DOMException && error.name === "AbortError"
        || error instanceof OrcaApiError && error.code === "REQUEST_CANCELLED";
      if (cancelled) return;
      const apiError = error instanceof OrcaApiError
        ? error
        : new OrcaApiError("ASSISTANT_UI_ERROR", "The assistant result could not be displayed.", 0);
      setLastError(apiError);
      setMessages((current) => [...current, {
        id: `error-${crypto.randomUUID()}`,
        kind: "error",
        role: "system",
        mode: mode === "live" ? "live" : mode === "demo" ? "demonstration" : "deterministic",
        content: assistantErrorMessage(apiError),
        created_at: new Date().toISOString(),
        evidence_references: [],
        warnings: [],
        suggested_actions: ["retry_assistant"],
        error_code: apiError.code,
        retryable: apiError.status === 0 || apiError.status === 429 || apiError.status >= 500,
      }]);
    } finally {
      if (!active.signal.aborted) setBusy(false);
    }
  }, [context, conversationId, language, messages, mode, transport]);

  const loadDemonstration = useCallback(() => {
    if (!parsedFixture.success) {
      setFixtureError(true);
      return false;
    }
    controller.current?.abort();
    setFixtureError(false);
    setMessages(parsedFixture.data.messages);
    setLatestResponse(null);
    setConversationId(null);
    setLastError(null);
    return true;
  }, []);

  const addClarification = useCallback((missing: ("location" | "operational_limits" | "requested_time")[]) => {
    setMessages((current) => [...current, {
      id: `clarification-${crypto.randomUUID()}`,
      kind: "clarification",
      role: "assistant",
      mode: mode === "live" ? "live" : "deterministic",
      content: "Add the missing query context, then send your question again. ORCA will not guess coordinates, time, or vessel limits.",
      created_at: new Date().toISOString(),
      missing_fields: missing,
      evidence_references: [],
      warnings: [],
      suggested_actions: ["open_query_context"],
    }]);
  }, [mode]);

  const addSystemNotice = useCallback((content: string) => {
    setMessages((current) => [...current, {
      id: `notice-${crypto.randomUUID()}`,
      kind: "system_notice",
      role: "system",
      mode: mode === "demo" ? "demonstration" : mode === "live" ? "live" : "deterministic",
      content,
      created_at: new Date().toISOString(),
      evidence_references: [],
      warnings: [],
      suggested_actions: [],
    }]);
  }, [mode]);

  const addDeterministicResult = useCallback((result: JourneyResponse) => {
    const id = `result-${result.generated_at}`;
    setMessages((current) => current.some((message) => message.id === id) ? current : [...current, {
      id,
      kind: "deterministic_result",
      role: "assistant",
      mode: "deterministic",
      content: `Deterministic ORCA result: ${result.journey_status.replaceAll("_", " ")}. Open the structured evidence panel for complete provenance and limitations.`,
      created_at: result.generated_at,
      journey_result: result,
      tool_activity: buildProvenActivity(result),
      evidence_references: buildEvidenceReferences(result),
      warnings: result.notices,
      suggested_actions: ["explain_sources"],
    }]);
  }, []);

  const cancel = useCallback(() => {
    controller.current?.abort();
    transport.cancel();
    setBusy(false);
  }, [transport]);

  const startNewChat = useCallback(() => {
    controller.current?.abort();
    transport.cancel();
    setBusy(false);
    setMessages([]);
    setConversationId(null);
    setLatestResponse(null);
    setLastError(null);
    lastRequest.current = null;
    contextStartNewChat();
  }, [transport, contextStartNewChat]);

  const switchSession = useCallback((sessionId: string) => {
    controller.current?.abort();
    transport.cancel();
    setBusy(false);
    contextSwitchSession(sessionId);
  }, [transport, contextSwitchSession]);

  const deleteSession = useCallback((sessionId: string) => {
    contextDeleteSession(sessionId);
  }, [contextDeleteSession]);

  const reset = useCallback(() => {
    startNewChat();
  }, [startNewChat]);

  const retry = useCallback(() => {
    if (lastRequest.current) void send(lastRequest.current.text, lastRequest.current.actionId);
  }, [send]);

  useEffect(() => () => controller.current?.abort(), []);
  return {
    messages,
    busy,
    fixtureError,
    latestResponse,
    conversationId,
    lastError,
    canRetry: Boolean(lastError && lastRequest.current),
    sessions,
    activeSessionId,
    startNewChat,
    switchSession,
    deleteSession,
    send,
    cancel,
    retry,
    reset,
    loadDemonstration,
    addClarification,
    addSystemNotice,
    addDeterministicResult,
  };
}

function assistantErrorMessage(error: OrcaApiError) {
  if (error.status === 429) return "ORCA’s assistant is temporarily rate limited. Wait before retrying; deterministic journey tools remain available.";
  if (error.code === "ASSISTANT_GRAPH_TIMEOUT" || error.code === "REQUEST_TIMEOUT") return "The assistant request took too long. You can retry or use the deterministic journey controls.";
  if (error.code === "ASSISTANT_NOT_CONFIGURED") return "The live assistant is not enabled on this backend. Deterministic journey tools remain available.";
  if (error.code === "NETWORK_UNAVAILABLE") return "The ORCA backend could not be reached. Check the backend connection, then retry.";
  return error.message;
}

function buildProvenActivity(result: JourneyResponse) {
  const evidenceAvailable = Boolean(result.origin.evidence || result.destination?.evidence);
  return [
    { id: "pfz", label: "PFZ lookup", status: result.pfz_resolution.status === "PFZ_FOUND" ? "complete" as const : result.pfz_resolution.status === "PFZ_REFRESH_PENDING" ? "waiting" as const : "unavailable" as const },
    { id: "marine", label: "Marine evidence", status: evidenceAvailable ? "complete" as const : "unavailable" as const },
    { id: "assessment", label: "Operational assessment", status: result.origin.assessment ? "complete" as const : "unavailable" as const },
  ];
}

function buildEvidenceReferences(result: JourneyResponse) {
  const sources = ["sst", "chlorophyll", "waves", "wind", "currents", "sea_level"] as const;
  return sources.flatMap((source) => (["origin", "destination"] as const).flatMap((location) => {
    const evidence = location === "origin" ? result.origin.evidence : result.destination?.evidence;
    const item = evidence?.evidence[source];
    if (!item || item.state === "not_requested") return [];
    const data = item.data as Record<string, unknown> | null | undefined;
    return [{
      source,
      label: source === "sea_level" ? "Sea level" : source[0].toUpperCase() + source.slice(1),
      state: item.state,
      valid_time: typeof data?.valid_time === "string" ? data.valid_time : typeof data?.analysis_time === "string" ? data.analysis_time : null,
      freshness: typeof data?.cache_status === "string" ? data.cache_status : null,
      location,
    }];
  }));
}
