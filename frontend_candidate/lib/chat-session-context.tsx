"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useUserMode } from "./context";
import type { AssistantMessage } from "./schemas/assistant";
import type { AssistantApiResponse } from "./schemas/assistant-api";

export interface ConversationSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: AssistantMessage[];
  conversationId: string | null;
  latestResponse: AssistantApiResponse | null;
}

interface ChatSessionContextType {
  sessions: ConversationSession[];
  activeSessionId: string;
  activeSession: ConversationSession | null;
  startNewChat: () => void;
  switchSession: (sessionId: string) => void;
  deleteSession: (sessionId: string) => void;
  saveActiveSession: (
    messages: AssistantMessage[],
    conversationId: string | null,
    latestResponse: AssistantApiResponse | null,
    sessionId?: string
  ) => void;
}

const ChatSessionContext = createContext<ChatSessionContextType | undefined>(undefined);

export function ChatSessionProvider({ children }: { children: React.ReactNode }) {
  const { user } = useUserMode();
  const userId = user?.email || user?.name || "guest";
  const userPrefix = useMemo(() => encodeURIComponent(userId.trim() || "guest"), [userId]);

  const KEY_SESSIONS = `orca_${userPrefix}_sessions`;
  const KEY_ACTIVE_SESSION = `orca_${userPrefix}_active_session_id`;

  const [sessions, setSessions] = useState<ConversationSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>(() => "session-initial");
  const isHydrated = useRef(false);

  // Load saved sessions from sessionStorage on mount or user change
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = sessionStorage.getItem(KEY_SESSIONS);
      let loaded: ConversationSession[] = [];
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed) && parsed.length > 0) {
          loaded = parsed;
        }
      }

      if (loaded.length > 0) {
        setSessions(loaded);
        const savedActive = sessionStorage.getItem(KEY_ACTIVE_SESSION);
        const active = loaded.find((s) => s.id === savedActive) || loaded[0];
        setActiveSessionId(active.id);
      } else {
        const initialId = `session-${Date.now()}`;
        setSessions([]);
        setActiveSessionId(initialId);
      }
    } catch {
      // Storage read failed safely
    } finally {
      isHydrated.current = true;
    }
  }, [KEY_SESSIONS, KEY_ACTIVE_SESSION]);

  const activeSession = useMemo(() => {
    return sessions.find((s) => s.id === activeSessionId) || null;
  }, [sessions, activeSessionId]);

  const startNewChat = useCallback(() => {
    const newId = `session-${Date.now()}`;
    setActiveSessionId(newId);
    if (typeof window !== "undefined") {
      try {
        sessionStorage.setItem(KEY_ACTIVE_SESSION, newId);
        sessionStorage.removeItem(`orca_${userPrefix}_messages`);
        sessionStorage.removeItem(`orca_${userPrefix}_conv_id`);
        sessionStorage.removeItem(`orca_${userPrefix}_response`);
      } catch {
        // Ignore
      }
    }
  }, [KEY_ACTIVE_SESSION, userPrefix]);

  const switchSession = useCallback((sessionId: string) => {
    const target = sessions.find((s) => s.id === sessionId);
    if (!target) return;
    setActiveSessionId(target.id);
    if (typeof window !== "undefined") {
      try {
        sessionStorage.setItem(KEY_ACTIVE_SESSION, target.id);
      } catch {
        // Ignore
      }
    }
  }, [sessions, KEY_ACTIVE_SESSION]);

  const deleteSession = useCallback((sessionId: string) => {
    setSessions((prev) => {
      const filtered = prev.filter((s) => s.id !== sessionId);
      if (typeof window !== "undefined") {
        try {
          sessionStorage.setItem(KEY_SESSIONS, JSON.stringify(filtered));
        } catch {
          // Ignore
        }
      }
      return filtered;
    });

    if (activeSessionId === sessionId) {
      startNewChat();
    }
  }, [activeSessionId, startNewChat, KEY_SESSIONS]);

  const saveActiveSession = useCallback((
    messages: AssistantMessage[],
    conversationId: string | null,
    latestResponse: AssistantApiResponse | null,
    sessionId?: string
  ) => {
    if (!isHydrated.current || typeof window === "undefined") return;

    setSessions((prev) => {
      const targetId = sessionId || activeSessionId;
      const existingIdx = prev.findIndex((s) => s.id === targetId);
      if (messages.length === 0 && existingIdx === -1) {
        return prev;
      }

      if (existingIdx >= 0) {
        const existing = prev[existingIdx];
        if (
          existing.messages === messages &&
          existing.conversationId === conversationId &&
          existing.latestResponse === latestResponse
        ) {
          return prev;
        }
      }

      const firstUserMsg = messages.find((m) => m.role === "user");
      const title = firstUserMsg ? firstUserMsg.content.slice(0, 42).trim() : "New Inquiry";
      const now = new Date().toISOString();

      let updated: ConversationSession[];
      if (existingIdx >= 0) {
        updated = [...prev];
        const existing = updated[existingIdx];
        updated[existingIdx] = {
          ...existing,
          title: existing.title === "New Inquiry" ? title : existing.title || title,
          updatedAt: now,
          messages,
          conversationId,
          latestResponse,
        };
      } else {
        updated = [
          {
            id: targetId,
            title,
            createdAt: now,
            updatedAt: now,
            messages,
            conversationId,
            latestResponse,
          },
          ...prev,
        ];
      }

      try {
        sessionStorage.setItem(KEY_SESSIONS, JSON.stringify(updated));
        sessionStorage.setItem(KEY_ACTIVE_SESSION, activeSessionId);
      } catch {
        // Ignore storage failures
      }
      return updated;
    });
  }, [activeSessionId, KEY_SESSIONS, KEY_ACTIVE_SESSION]);

  return (
    <ChatSessionContext.Provider
      value={{
        sessions,
        activeSessionId,
        activeSession,
        startNewChat,
        switchSession,
        deleteSession,
        saveActiveSession,
      }}
    >
      {children}
    </ChatSessionContext.Provider>
  );
}

export function useChatSessions() {
  const context = useContext(ChatSessionContext);
  if (!context) {
    return {
      sessions: [],
      activeSessionId: "default",
      activeSession: null,
      startNewChat: () => {},
      switchSession: () => {},
      deleteSession: () => {},
      saveActiveSession: () => {},
    };
  }
  return context;
}

