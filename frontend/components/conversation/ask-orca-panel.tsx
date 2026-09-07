"use client";

import { Bot, ChevronDown, FlaskConical, MessageSquareText, RotateCcw, Send, Settings2, Square, Waves } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ActivityTrace } from "./activity-trace";
import { EvidenceChips } from "./evidence-chips";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { AssistantMessage, EvidenceReference } from "@/lib/schemas/assistant";
import type { JourneyResponse } from "@/lib/schemas/journey";

const suggestions = [
  ["find_pfz", "Where is the nearest PFZ today?", "Available"],
  ["explain_conditions", "What are the marine conditions near my location?", "Available"],
  ["tomorrow_limits", "Do tomorrow’s conditions exceed my vessel limits?", "Partially available"],
  ["official_alerts", "Are official cyclone or lightning alerts available?", "Planned"],
  ["regional_indicators", "Which areas show favourable SST and chlorophyll?", "Planned"],
  ["avoid_zones", "Which fishing zones should be avoided?", "Planned"],
  ["explain_degraded", "Why is this evidence degraded?", "Available"],
  ["explain_sources", "What sources support this result?", "Available"],
] as const;

export function AskOrcaPanel({ mode, presentationMode, messages, busy, fixtureError, onSend, onCancel, onReset, onLoadDemo, onRetry, canRetry, onQuickAction, onEvidenceSelect, onResultSelect }: {
  mode: "disabled" | "demo"; presentationMode: boolean; messages: AssistantMessage[]; busy: boolean; fixtureError: boolean;
  onSend: (text: string, actionId?: string) => void; onCancel: () => void; onReset: () => void; onLoadDemo: () => void; onRetry?: () => void; canRetry?: boolean;
  onQuickAction: (id: string, text: string) => void; onEvidenceSelect: (reference: EvidenceReference) => void; onResultSelect: (result: JourneyResponse) => void;
}) {
  const [draft, setDraft] = useState("");
  const [suggestionsOverride, setSuggestionsOverride] = useState<{ messageCount: number; open: boolean } | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const suggestionsOpen = suggestionsOverride?.messageCount === messages.length
    ? suggestionsOverride.open
    : messages.length === 0;

  useEffect(() => {
    if (typeof end.current?.scrollIntoView === "function") end.current.scrollIntoView({ block: "nearest" });
  }, [messages.length, suggestionsOpen]);

  const setSuggestionsForCurrentMessages = (open: boolean) => setSuggestionsOverride({ messageCount: messages.length, open });
  const submit = (event: React.FormEvent) => { event.preventDefault(); if (draft.trim()) { setSuggestionsForCurrentMessages(false); onSend(draft); setDraft(""); } };
  const selectSuggestion = (id: string, text: string) => {
    setSuggestionsForCurrentMessages(false);
    onQuickAction(id, text);
  };
  const loadDemonstration = () => { setSuggestionsForCurrentMessages(false); onLoadDemo(); };
  const resetDemonstration = () => { setSuggestionsForCurrentMessages(true); onReset(); };

  return <Card className="conversation-panel flex min-h-[32rem] min-w-0 flex-col overflow-hidden">
    <div className="shrink-0 border-b border-[var(--border)] p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="flex items-center gap-2 font-bold"><Bot aria-hidden="true" className="size-5 text-[var(--secondary)]" />Ask ORCA</h2><Badge tone={mode === "demo" ? "caution" : "neutral"}>{mode === "demo" ? "Demonstration Conversation" : "Assistant disabled"}</Badge></div><p className="mt-1 text-sm text-[var(--muted-foreground)]">Ask about PFZs, marine conditions, operational limits, hazards, environmental indicators and supporting evidence.</p>{presentationMode && <p className="mt-2 text-sm font-semibold text-[var(--information)]">Judge presentation mode · question first, optional map later</p>}</div>
    <div className="conversation-scroll min-h-0 flex-1 space-y-3 overflow-y-auto p-3" role="log" aria-label="ORCA conversation" aria-live="polite" aria-relevant="additions text">
      {messages.length === 0 && <div className="rounded-lg border border-dashed border-[var(--border)] p-4 text-center"><Waves aria-hidden="true" className="mx-auto size-7 text-[var(--secondary)]" /><h3 className="mt-2 font-semibold">Start with a deterministic action</h3><p className="mt-1 text-sm text-[var(--muted-foreground)]">{mode === "disabled" ? "Conversational agent connection is not enabled. You can continue using ORCA’s deterministic journey tools." : "Load the saved Gujarat demonstration or choose a suggested question."}</p></div>}
      {fixtureError && <div role="alert" className="rounded-lg border border-[var(--danger)] bg-[var(--danger-surface)] p-3 text-sm"><strong>Demonstration fixture invalid.</strong><p>Use the deterministic journey controls while the saved fixture is checked.</p></div>}
      {messages.map((message) => <article key={message.id} className={`message-card ${message.role === "user" ? "message-user" : message.kind === "error" ? "message-error" : "message-orca"}`} aria-label={`${message.role} message`}>
        <div className="flex flex-wrap items-center justify-between gap-2"><strong className="text-xs uppercase tracking-[0.08em]">{message.role === "user" ? "You" : message.kind === "deterministic_result" ? "Deterministic ORCA result" : message.mode === "demonstration" ? "Demonstration message" : "ORCA notice"}</strong><time className="text-xs text-[var(--muted-foreground)]" dateTime={message.created_at}>{new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></div><p className="mt-1 text-sm whitespace-pre-wrap">{message.content}</p>
        {"tool_activity" in message && <ActivityTrace steps={message.tool_activity} demonstration={message.mode === "demonstration"} />}
        <EvidenceChips references={message.evidence_references} onSelect={onEvidenceSelect} />
        {message.warnings.length > 0 && <ul className="mt-2 list-disc pl-5 text-xs text-[var(--caution)]">{message.warnings.map((warning) => <li className="long-token" key={warning}>{warning}</li>)}</ul>}
        {message.kind === "deterministic_result" && <Button variant="secondary" className="mt-3 w-full" onClick={() => onResultSelect(message.journey_result)}>Restore this result on map</Button>}
      </article>)}<div ref={end} aria-hidden="true" />
    </div>
    <section className="shrink-0 border-t border-[var(--border)]" aria-labelledby="suggested-questions-heading">
      <button
        type="button"
        className="flex min-h-11 w-full cursor-pointer items-center gap-2 px-3 py-2 text-left text-sm font-semibold hover:bg-[var(--surface-muted)]"
        aria-expanded={suggestionsOpen}
        aria-controls="orca-suggested-questions"
        onClick={() => setSuggestionsForCurrentMessages(!suggestionsOpen)}
      >
        <MessageSquareText aria-hidden="true" className="size-4 text-[var(--secondary)]" />
        <span id="suggested-questions-heading">Suggested questions</span>
        <span className="ml-auto text-xs font-normal text-[var(--muted-foreground)]">{suggestionsOpen ? "Hide" : "Show"}</span>
        <ChevronDown aria-hidden="true" className={`size-4 transition-transform ${suggestionsOpen ? "rotate-180" : ""}`} />
      </button>
      {suggestionsOpen && <div id="orca-suggested-questions" className="suggestion-list grid max-h-48 gap-2 overflow-y-auto px-3 pb-3" aria-label="Suggested questions">
        {suggestions.map(([id, text, availability]) => <button key={id} type="button" onClick={() => selectSuggestion(id, text)} className="flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-left text-xs font-semibold hover:border-[var(--secondary)]"><span>{text}</span><span className={`shrink-0 rounded-full px-2 py-0.5 text-[0.6875rem] ${availability === "Available" ? "bg-[var(--success-surface)] text-[var(--success)]" : availability === "Planned" ? "bg-[var(--surface-muted)] text-[var(--muted-foreground)]" : "bg-[var(--caution-surface)] text-[var(--caution)]"}`}>{availability}</span></button>)}
      </div>}
    </section>
    <div className="shrink-0 border-t border-[var(--border)] p-3">
      {mode === "demo" && <div className="mb-2 grid grid-cols-2 gap-2"><Button variant="secondary" onClick={loadDemonstration}><FlaskConical aria-hidden="true" className="size-4" />Load demonstration</Button><Button variant="ghost" onClick={resetDemonstration}><RotateCcw aria-hidden="true" className="size-4" />Reset demonstration</Button></div>}
      {canRetry && onRetry && <Button variant="secondary" className="mb-2 w-full" onClick={onRetry}><RotateCcw aria-hidden="true" className="size-4" />Retry deterministic request</Button>}
      <form onSubmit={submit} className="flex gap-2"><label htmlFor="assistant-message" className="sr-only">Message Ask ORCA</label><input id="assistant-message" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={mode === "demo" ? "Ask from the saved demonstration…" : "Try a deterministic action…"} className="min-h-11 min-w-0 flex-1 rounded-md border border-[var(--border)] bg-white px-3 text-base" /><Button type="submit" aria-label="Send message" disabled={!draft.trim() || busy}>{busy ? <Square aria-hidden="true" className="size-4" /> : <Send aria-hidden="true" className="size-4" />}</Button>{busy && <Button type="button" variant="secondary" aria-label="Cancel assistant request" onClick={onCancel}><Square aria-hidden="true" className="size-4" /></Button>}</form>
      <button type="button" onClick={() => onQuickAction("open_advanced_parameters", "Open advanced query parameters")} className="mt-2 flex min-h-11 w-full cursor-pointer items-center justify-center gap-2 text-sm font-semibold text-[var(--information)]"><Settings2 aria-hidden="true" className="size-4" />Advanced query parameters</button>
    </div>
  </Card>;
}
