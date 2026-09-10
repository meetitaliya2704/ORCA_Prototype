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

const parsedFixture = demonstrationConversationSchema.safeParse(demoConversationJson);
const STORAGE_KEY_SESSIONS = "orca_conversation_sessions";
const STORAGE_KEY_ACTIVE_SESSION = "orca_active_session_id";
const STORAGE_KEY_MESSAGES = "orca_assistant_messages";
const STORAGE_KEY_CONV_ID = "orca_assistant_conversation_id";
const STORAGE_KEY_RESPONSE = "orca_assistant_latest_response";

export interface ConversationSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: AssistantMessage[];
  conversationId: string | null;
  latestResponse: AssistantApiResponse | null;
}

export function useAssistant(
  mode: AssistantMode,
  language: AssistantLanguage,
  context: AssistantContextValues,
) {
  const [sessions, setSessions] = useState<ConversationSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>(() => "session-initial");
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [fixtureError, setFixtureError] = useState(!parsedFixture.success);
  const [latestResponse, setLatestResponse] = useState<AssistantApiResponse | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [lastError, setLastError] = useState<OrcaApiError | null>(null);
  const controller = useRef<AbortController | null>(null);
  const lastRequest = useRef<{ text: string; actionId?: string } | null>(null);
  const isHydrated = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const rawSessions = localStorage.getItem(STORAGE_KEY_SESSIONS);
      let loadedSessions: ConversationSession[] = [];
      if (rawSessions) {
        const parsed = JSON.parse(rawSessions);
        if (Array.isArray(parsed) && parsed.length > 0) {
          loadedSessions = parsed;
        }
      }

      if (loadedSessions.length === 0) {
        const savedMessages = localStorage.getItem(STORAGE_KEY_MESSAGES);
        if (savedMessages) {
          const parsed = JSON.parse(savedMessages);
          if (Array.isArray(parsed) && parsed.length > 0) {
            const savedConvId = localStorage.getItem(STORAGE_KEY_CONV_ID);
            const savedResponse = localStorage.getItem(STORAGE_KEY_RESPONSE);
            const firstMsg = parsed.find((m: AssistantMessage) => m.role === "user");
            const legacySession: ConversationSession = {
              id: `session-${Date.now()}`,
              title: firstMsg ? firstMsg.content.slice(0, 36) : "Conversation",
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
              messages: parsed,
              conversationId: savedConvId ?? null,
              latestResponse: savedResponse ? JSON.parse(savedResponse) : null,
            };
            loadedSessions = [legacySession];
          }
        }
      }

      if (loadedSessions.length > 0) {
        setSessions(loadedSessions);
        const savedActiveId = localStorage.getItem(STORAGE_KEY_ACTIVE_SESSION);
        const active = loadedSessions.find((s) => s.id === savedActiveId) || loadedSessions[0];
        setActiveSessionId(active.id);
        setMessages(active.messages);
        setConversationId(active.conversationId);
        setLatestResponse(active.latestResponse);
      }
    } catch {
      // Storage read failed safely
    } finally {
      isHydrated.current = true;
    }
  }, []);

  useEffect(() => {
    if (!isHydrated.current || typeof window === "undefined") return;
    try {
      setSessions((prevSessions) => {
        const existingIndex = prevSessions.findIndex((s) => s.id === activeSessionId);
        if (messages.length === 0 && existingIndex === -1) {
          return prevSessions;
        }
        const firstUserMsg = messages.find((m) => m.role === "user");
        const title = firstUserMsg ? firstUserMsg.content.slice(0, 36) : "Conversation";
        const now = new Date().toISOString();

        let updated: ConversationSession[];
        if (existingIndex >= 0) {
          updated = [...prevSessions];
          updated[existingIndex] = {
            ...updated[existingIndex],
            title: updated[existingIndex].title === "Conversation" ? title : updated[existingIndex].title,
            updatedAt: now,
            messages,
            conversationId,
            latestResponse,
          };
        } else {
          updated = [
            {
              id: activeSessionId,
              title,
              createdAt: now,
              updatedAt: now,
              messages,
              conversationId,
              latestResponse,
            },
            ...prevSessions,
          ];
        }
        localStorage.setItem(STORAGE_KEY_SESSIONS, JSON.stringify(updated));
        localStorage.setItem(STORAGE_KEY_ACTIVE_SESSION, activeSessionId);
        if (messages.length > 0) {
          localStorage.setItem(STORAGE_KEY_MESSAGES, JSON.stringify(messages));
        } else {
          localStorage.removeItem(STORAGE_KEY_MESSAGES);
        }
        if (conversationId) {
          localStorage.setItem(STORAGE_KEY_CONV_ID, conversationId);
        } else {
          localStorage.removeItem(STORAGE_KEY_CONV_ID);
        }
        if (latestResponse) {
          localStorage.setItem(STORAGE_KEY_RESPONSE, JSON.stringify(latestResponse));
        } else {
          localStorage.removeItem(STORAGE_KEY_RESPONSE);
        }
        return updated;
      });
    } catch {
      // Storage write failed safely
    }
  }, [activeSessionId, messages, conversationId, latestResponse]);

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
    const newSessionId = `session-${Date.now()}`;
    setActiveSessionId(newSessionId);
    setMessages([]);
    setConversationId(null);
    setLatestResponse(null);
    setLastError(null);
    lastRequest.current = null;
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem(STORAGE_KEY_ACTIVE_SESSION, newSessionId);
        localStorage.removeItem(STORAGE_KEY_MESSAGES);
        localStorage.removeItem(STORAGE_KEY_CONV_ID);
        localStorage.removeItem(STORAGE_KEY_RESPONSE);
      } catch {
        // Ignore
      }
    }
  }, [transport]);

  const switchSession = useCallback((sessionId: string) => {
    controller.current?.abort();
    transport.cancel();
    setBusy(false);
    const target = sessions.find((s) => s.id === sessionId);
    if (!target) return;
    setActiveSessionId(target.id);
    setMessages(target.messages);
    setConversationId(target.conversationId);
    setLatestResponse(target.latestResponse);
    setLastError(null);
    lastRequest.current = null;
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem(STORAGE_KEY_ACTIVE_SESSION, target.id);
      } catch {
        // Ignore
      }
    }
  }, [sessions, transport]);

  const deleteSession = useCallback((sessionId: string) => {
    setSessions((prev) => {
      const filtered = prev.filter((s) => s.id !== sessionId);
      if (typeof window !== "undefined") {
        try {
          localStorage.setItem(STORAGE_KEY_SESSIONS, JSON.stringify(filtered));
        } catch {
          // Ignore
        }
      }
      return filtered;
    });
    if (activeSessionId === sessionId) {
      startNewChat();
    }
  }, [activeSessionId, startNewChat]);

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
