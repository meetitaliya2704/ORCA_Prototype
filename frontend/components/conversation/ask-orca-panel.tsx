"use client";

import {
  Bot,
  ChevronDown,
  Clock,
  FlaskConical,
  History,
  LoaderCircle,
  MessageSquareText,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  Trash2,
  Waves,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ActivityTrace } from "./activity-trace";
import { AssistantContextPanel } from "./assistant-context-panel";
import { EvidenceChips } from "./evidence-chips";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { ConversationSession } from "@/hooks/use-assistant";
import type { AssistantMessage, AssistantMode, EvidenceReference } from "@/lib/schemas/assistant";
import type { AssistantContextValues } from "@/lib/schemas/assistant-api";
import type { JourneyResponse } from "@/lib/schemas/journey";

const suggestions = [
  ["find_pfz", "Find nearest PFZ advisory"],
  ["explain_conditions", "Check marine conditions"],
  ["assess_limits", "Assess operational limits"],
  ["explain_sources", "Explain evidence sources"],
] as const;

const BUSY_STAGES = [
  { title: "Analyzing request...", subtitle: "Connecting to INCOIS & Copernicus marine feeds..." },
  { title: "Fetching Marine Observations...", subtitle: "Aggregating SST, wave spectrum, wind vectors, currents & tides..." },
  { title: "Evaluating Operational Limits...", subtitle: "Validating vessel safety boundaries & advisory zones..." },
  { title: "Synthesizing Intelligence...", subtitle: "Finalizing verified marine decision bulletin..." },
];

export function AskOrcaPanel({
  mode,
  presentationMode,
  messages,
  busy,
  fixtureError,
  context,
  contextOpen,
  conversationId,
  sessions = [],
  activeSessionId,
  onSwitchSession,
  onDeleteSession,
  onContextChange,
  onContextOpenChange,
  onSend,
  onCancel,
  onReset,
  onLoadDemo,
  onRetry,
  canRetry,
  onQuickAction,
  onEvidenceSelect,
  onResultSelect,
}: {
  mode: AssistantMode;
  presentationMode: boolean;
  messages: AssistantMessage[];
  busy: boolean;
  fixtureError: boolean;
  context: AssistantContextValues;
  contextOpen: boolean;
  conversationId?: string | null;
  sessions?: ConversationSession[];
  activeSessionId?: string;
  onSwitchSession?: (sessionId: string) => void;
  onDeleteSession?: (sessionId: string) => void;
  onContextChange: (values: AssistantContextValues) => void;
  onContextOpenChange: (open: boolean) => void;
  onSend: (text: string, actionId?: string) => void;
  onCancel: () => void;
  onReset: () => void;
  onLoadDemo: () => void;
  onRetry?: () => void;
  canRetry?: boolean;
  onQuickAction: (id: string, text: string) => void;
  onEvidenceSelect: (reference: EvidenceReference) => void;
  onResultSelect: (result: JourneyResponse) => void;
}) {
  const [draft, setDraft] = useState("");
  const [suggestionsOverride, setSuggestionsOverride] = useState<{ messageCount: number; open: boolean } | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const suggestionsOpen = suggestionsOverride?.messageCount === messages.length
    ? suggestionsOverride.open
    : messages.length === 0;
  const lastClarification = [...messages].reverse().find((message) => message.kind === "clarification");
  const missingFields = lastClarification?.kind === "clarification" ? lastClarification.missing_fields : [];

  const [busyStageIndex, setBusyStageIndex] = useState(0);

  useEffect(() => {
    if (!busy) {
      setBusyStageIndex(0);
      return;
    }
    const t1 = setTimeout(() => setBusyStageIndex(1), 1600);
    const t2 = setTimeout(() => setBusyStageIndex(2), 3400);
    const t3 = setTimeout(() => setBusyStageIndex(3), 5000);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    };
  }, [busy]);

  useEffect(() => {
    if (typeof end.current?.scrollIntoView === "function") end.current.scrollIntoView({ block: "nearest" });
  }, [messages.length, suggestionsOpen, busyStageIndex]);

  const setSuggestionsForCurrentMessages = (open: boolean) => setSuggestionsOverride({ messageCount: messages.length, open });
  const submit = () => {
    if (!draft.trim() || busy) return;
    setSuggestionsForCurrentMessages(false);
    onSend(draft);
    setDraft("");
  };
  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };
  const selectSuggestion = (id: string, text: string) => {
    setSuggestionsForCurrentMessages(false);
    onQuickAction(id, text);
  };
  const reset = () => {
    setSuggestionsForCurrentMessages(true);
    onReset();
    window.setTimeout(() => composer.current?.focus(), 0);
  };

  return <Card className="conversation-panel flex min-h-[36rem] min-w-0 flex-col overflow-hidden">
    <div className="conversation-heading shrink-0 border-b border-[var(--border)] p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="mt-1 flex items-center gap-2 text-xl font-bold"><Bot aria-hidden="true" className="size-6 text-[var(--primary)]" />Ask ORCA</h2>
          <p className="mt-1 max-w-xl text-sm text-[var(--muted-foreground)]">Ask about PFZ advisories, marine conditions, or operational limits.</p>
        </div>
        <div className="flex items-center gap-2">
          {sessions && sessions.length > 0 && (
            <Button
              type="button"
              variant={historyOpen ? "primary" : "secondary"}
              size="sm"
              onClick={() => setHistoryOpen(!historyOpen)}
              title="View saved conversation sessions"
              className="h-8 gap-1.5 text-xs font-semibold"
            >
              <History aria-hidden="true" className="size-3.5" />
              History
              <span className="ml-0.5 rounded-full bg-slate-200 px-1.5 py-0.2 text-[0.65rem] font-bold text-slate-800">
                {sessions.length}
              </span>
            </Button>
          )}
          {messages.length > 0 && (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => { reset(); setHistoryOpen(false); }}
              title="Start a new conversation thread"
              className="h-8 gap-1.5 text-xs font-semibold"
            >
              <RotateCcw aria-hidden="true" className="size-3.5" />
              New chat
            </Button>
          )}
        </div>
      </div>
    </div>

    {historyOpen && sessions && sessions.length > 0 && (
      <section className="border-b border-[var(--border)] bg-[var(--surface-raised)] p-3 shadow-inner" aria-label="Conversation History">
        <div className="flex items-center justify-between pb-2">
          <span className="text-xs font-bold uppercase tracking-wider text-[var(--muted-foreground)]">
            Saved Conversations ({sessions.length})
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setHistoryOpen(false)}
            className="h-6 text-xs text-[var(--muted-foreground)]"
          >
            Close
          </Button>
        </div>
        <div className="grid max-h-56 gap-1.5 overflow-y-auto pr-1">
          {sessions.map((s) => {
            const isActive = s.id === activeSessionId;
            return (
              <div
                key={s.id}
                className={`flex items-center justify-between rounded-lg border p-2.5 transition-colors ${
                  isActive
                    ? "border-[var(--secondary)] bg-white shadow-sm"
                    : "border-[var(--border)] bg-white/70 hover:bg-white"
                }`}
              >
                <button
                  type="button"
                  onClick={() => {
                    onSwitchSession?.(s.id);
                    setHistoryOpen(false);
                  }}
                  className="flex min-w-0 flex-1 cursor-pointer flex-col text-left"
                >
                  <div className="flex items-center gap-2">
                    <span className="truncate text-xs font-bold text-[var(--foreground)]">
                      {s.title}
                    </span>
                    {isActive && (
                      <span className="rounded bg-[var(--secondary)]/15 px-1.5 py-0.5 text-[0.65rem] font-bold text-[var(--secondary)]">
                        Active
                      </span>
                    )}
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-[0.7rem] text-[var(--muted-foreground)]">
                    <span className="flex items-center gap-1">
                      <Clock aria-hidden="true" className="size-3" />
                      {new Date(s.updatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                    <span>•</span>
                    <span>{s.messages.filter((m) => m.role === "user" || m.role === "assistant").length} messages</span>
                  </div>
                </button>
                {onDeleteSession && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteSession(s.id);
                    }}
                    title="Delete session"
                    className="size-7 shrink-0 text-[var(--muted-foreground)] hover:text-[var(--danger)]"
                  >
                    <Trash2 aria-hidden="true" className="size-3.5" />
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      </section>
    )}

    <section className="shrink-0 border-b border-[var(--border)]" aria-labelledby="suggested-questions-heading">
      <button type="button" className="flex min-h-11 w-full cursor-pointer items-center gap-2 px-4 py-2 text-left text-sm font-semibold transition-colors hover:bg-[var(--surface-muted)]" aria-expanded={suggestionsOpen} aria-controls="orca-suggested-questions" onClick={() => setSuggestionsForCurrentMessages(!suggestionsOpen)}>
        <MessageSquareText aria-hidden="true" className="size-4 text-[var(--secondary)]" /><span id="suggested-questions-heading">Suggested questions</span><span className="ml-auto text-xs font-normal text-[var(--muted-foreground)]">{suggestionsOpen ? "Hide" : "Show"}</span><ChevronDown aria-hidden="true" className={`size-4 transition-transform ${suggestionsOpen ? "rotate-180" : ""}`} />
      </button>
      {suggestionsOpen && <div id="orca-suggested-questions" className="suggestion-list grid max-h-48 gap-2 overflow-y-auto px-3 pb-3 sm:grid-cols-2" aria-label="Suggested questions">
        {suggestions.map(([id, text]) => <button key={id} type="button" onClick={() => selectSuggestion(id, text)} className="prompt-card"><span>{text}</span></button>)}
      </div>}
    </section>

    <AssistantContextPanel values={context} onChange={onContextChange} missingFields={missingFields} open={contextOpen} onOpenChange={onContextOpenChange} />

    <div className="conversation-scroll min-h-0 flex-1 space-y-4 overflow-y-auto p-3 sm:p-5" role="log" aria-label="ORCA conversation" aria-live="polite" aria-relevant="additions text">
      {messages.length === 0 && <div className="welcome-state relative overflow-hidden rounded-xl border border-[var(--border)] p-5 sm:p-7">
        <div className="wave-grid" aria-hidden="true" />
        <div className="relative">
          <div className="flex size-11 items-center justify-center rounded-xl bg-[var(--primary)] text-white"><Waves aria-hidden="true" className="size-6" /></div>
          <h3 className="mt-4 max-w-lg text-balance text-xl font-bold">What would you like to understand about today’s marine conditions?</h3>
          <p className="mt-2 max-w-xl text-sm leading-6 text-[var(--muted-foreground)]">
            ORCA analyzes official marine data sources and provides evidence-backed answers. All measurements come from verified providers.
          </p>
        </div>
      </div>}
      {messages.map((message) => <article key={message.id} className={`message-card min-w-0 break-words ${message.role === "user" ? "message-user" : message.kind === "error" ? "message-error" : "message-orca"}`} aria-label={`${message.role} message`}>
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <strong className="text-xs uppercase tracking-[0.1em]">{message.role === "user" ? "You" : "ORCA"}</strong>
          <time className="text-xs text-[var(--muted-foreground)]" dateTime={message.created_at}>{new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
        </div>
        <p className="mt-2 min-w-0 break-words whitespace-pre-wrap text-[0.925rem] leading-6">{message.content}</p>
        {message.kind === "clarification" && <div className="mt-3 min-w-0 rounded-lg bg-[var(--caution-surface)] p-3 text-sm"><strong>Information requested</strong><div className="mt-2 flex flex-wrap gap-2">{message.missing_fields.map((field) => <Badge tone="caution" key={field}>{field.replaceAll("_", " ")}</Badge>)}</div><Button variant="secondary" className="mt-3 w-full" onClick={() => onContextOpenChange(true)}>Add query context</Button></div>}
        {"tool_activity" in message && <ActivityTrace steps={message.tool_activity} demonstration={message.mode === "demonstration"} />}
        <EvidenceChips references={message.evidence_references} onSelect={onEvidenceSelect} />
        {message.warnings.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-[var(--caution)] min-w-0">{message.warnings.map((warning) => <li className="long-token min-w-0 break-words" key={warning}>{warning}</li>)}</ul>}
        {message.kind === "deterministic_result" && <Button variant="secondary" className="mt-3 w-full" onClick={() => onResultSelect(message.journey_result)}>Restore this result on map</Button>}
      </article>)}
      {busy && (
        <div role="status" className="message-card message-orca" aria-label="ORCA is processing the request">
          <div className="flex items-start gap-3">
            <span className="processing-indicator mt-1 shrink-0"><span /><span /><span /></span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <strong className="text-sm font-semibold text-[var(--foreground)]">{BUSY_STAGES[busyStageIndex].title}</strong>
                <span className="shrink-0 rounded-full bg-[var(--primary)]/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-[var(--primary)]">
                  Stage {busyStageIndex + 1}/4
                </span>
              </div>
              <p className="mt-1 text-xs text-[var(--muted-foreground)] transition-all duration-300">
                {BUSY_STAGES[busyStageIndex].subtitle}
              </p>
              <div className="mt-2.5 flex items-center gap-1.5">
                {[0, 1, 2, 3].map((step) => (
                  <span
                    key={step}
                    className={`h-1 flex-1 rounded-full transition-all duration-300 ${
                      step <= busyStageIndex ? "bg-[var(--primary)]" : "bg-[var(--border)]"
                    }`}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
      <div ref={end} aria-hidden="true" />
    </div>

    <div className="composer-shell shrink-0 border-t border-[var(--border)] p-3 sm:p-4">
      {canRetry && onRetry && <Button variant="secondary" className="mb-3 w-full" onClick={onRetry}><RotateCcw aria-hidden="true" className="size-4" />Retry assistant request</Button>}
      <div className="composer-box">
        <label htmlFor="assistant-message" className="sr-only">Message Ask ORCA</label>
        <textarea ref={composer} id="assistant-message" rows={2} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleKeyDown} placeholder="Ask about marine conditions, PFZ, or operational limits..." className="composer-input" />
        <div className="flex items-center justify-between gap-3 border-t border-[var(--border)] px-2 py-2">
          <p className="hidden text-xs text-[var(--muted-foreground)] sm:block">Enter to send · Shift+Enter for a new line</p>
          <div className="ml-auto flex gap-2">{busy && <Button type="button" variant="secondary" size="icon" aria-label="Cancel assistant request" onClick={onCancel}><Square aria-hidden="true" className="size-4" /></Button>}<Button type="button" size="icon" aria-label="Send message" disabled={!draft.trim() || busy} onClick={submit}>{busy ? <LoaderCircle aria-hidden="true" className="size-4 animate-spin" /> : <Send aria-hidden="true" className="size-4" />}</Button></div>
        </div>
      </div>
    </div>
  </Card>;
}
