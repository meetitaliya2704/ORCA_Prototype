"use client";

import demoConversationJson from "@/public/demo/conversation.json";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DemoAssistantTransport, DisabledAssistantTransport } from "@/lib/assistant/transport";
import { demonstrationConversationSchema, type AssistantMessage } from "@/lib/schemas/assistant";
import type { JourneyResponse } from "@/lib/schemas/journey";

const parsedFixture = demonstrationConversationSchema.safeParse(demoConversationJson);

export function useAssistant(mode: "disabled" | "demo") {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [fixtureError, setFixtureError] = useState(!parsedFixture.success);
  const controller = useRef<AbortController | null>(null);
  const transport = useMemo(() => mode === "demo" && parsedFixture.success
    ? new DemoAssistantTransport(parsedFixture.data)
    : new DisabledAssistantTransport(), [mode]);

  const send = useCallback(async (text: string, actionId?: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    controller.current?.abort();
    const active = new AbortController();
    controller.current = active;
    const userMessage: AssistantMessage = {
      id: `user-${crypto.randomUUID()}`, kind: "user", role: "user",
      mode: mode === "demo" ? "demonstration" : "deterministic",
      content: trimmed, created_at: new Date().toISOString(), evidence_references: [], warnings: [], suggested_actions: [],
    };
    setMessages((current) => [...current, userMessage]);
    setBusy(true);
    try {
      const response = await transport.send({ text: trimmed, actionId }, active.signal);
      if (!active.signal.aborted) setMessages((current) => [...current, ...response]);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setMessages((current) => [...current, {
          id: `error-${crypto.randomUUID()}`, kind: "error", role: "system", mode: mode === "demo" ? "demonstration" : "deterministic",
          content: "The saved conversational response could not be displayed. Use the deterministic journey controls instead.",
          created_at: new Date().toISOString(), evidence_references: [], warnings: [], suggested_actions: ["find_pfz"],
        }]);
      }
    } finally { if (!active.signal.aborted) setBusy(false); }
  }, [mode, transport]);

  const loadDemonstration = useCallback(() => {
    if (!parsedFixture.success) { setFixtureError(true); return false; }
    setFixtureError(false);
    setMessages(parsedFixture.data.messages);
    return true;
  }, []);

  const addClarification = useCallback((missing: ("location" | "operational_limits" | "requested_time")[]) => {
    setMessages((current) => [...current, {
      id: `clarification-${crypto.randomUUID()}`, kind: "clarification", role: "assistant", mode: "deterministic",
      content: "Add your location and at least one user-supplied operational limit in Advanced query parameters, then run the deterministic PFZ journey.",
      created_at: new Date().toISOString(), missing_fields: missing, evidence_references: [], warnings: [], suggested_actions: ["open_advanced_parameters"],
    }]);
  }, []);

  const addSystemNotice = useCallback((content: string) => {
    setMessages((current) => [...current, {
      id: `notice-${crypto.randomUUID()}`, kind: "system_notice", role: "system", mode: mode === "demo" ? "demonstration" : "deterministic",
      content, created_at: new Date().toISOString(), evidence_references: [], warnings: [], suggested_actions: [],
    }]);
  }, [mode]);

  const addDeterministicResult = useCallback((result: JourneyResponse) => {
    const id = `result-${result.generated_at}`;
    setMessages((current) => current.some((message) => message.id === id) ? current : [...current, {
      id, kind: "deterministic_result", role: "assistant", mode: "deterministic",
      content: `Deterministic ORCA result: ${result.journey_status.replaceAll("_", " ")}. Open the structured evidence panel for the complete provenance and limitations.`,
      created_at: result.generated_at,
      journey_result: result,
      tool_activity: buildProvenActivity(result),
      evidence_references: buildEvidenceReferences(result), warnings: result.notices, suggested_actions: ["explain_sources"],
    }]);
  }, []);

  const cancel = useCallback(() => { controller.current?.abort(); transport.cancel(); setBusy(false); }, [transport]);
  const reset = useCallback(() => { cancel(); setMessages([]); setFixtureError(false); }, [cancel]);
  useEffect(() => () => controller.current?.abort(), []);
  return { messages, busy, fixtureError, send, cancel, reset, loadDemonstration, addClarification, addSystemNotice, addDeterministicResult };
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
    return [{ source, label: source === "sea_level" ? "Sea level" : source[0].toUpperCase() + source.slice(1), state: item.state,
      valid_time: typeof data?.valid_time === "string" ? data.valid_time : typeof data?.analysis_time === "string" ? data.analysis_time : null,
      freshness: typeof data?.cache_status === "string" ? data.cache_status : null, location }];
  }));
}
