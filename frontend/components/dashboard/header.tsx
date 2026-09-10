"use client";

import { Activity, Clock3, Database, Languages, RadioTower, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { InformationDialog } from "@/components/ui/dialog";
import { useBackendHealth } from "@/hooks/use-health";
import type { JourneyMode } from "@/hooks/use-journey";
import type { AssistantMode } from "@/lib/schemas/assistant";
import type { AssistantApiResponse, AssistantLanguage } from "@/lib/schemas/assistant-api";
import type { JourneyResponse } from "@/lib/schemas/journey";

const languages: { value: AssistantLanguage; label: string }[] = [
  { value: "en", label: "English" },
  { value: "hi", label: "हिन्दी" },
  { value: "gu", label: "ગુજરાતી" },
  { value: "mr", label: "मराठी" },
  { value: "ta", label: "தமிழ்" },
  { value: "te", label: "తెలుగు" },
  { value: "ml", label: "മലയാളം" },
  { value: "bn", label: "বাংলা" },
];

export function Header({
  result,
  assistantResponse,
  mode,
  assistantMode,
  presentationMode,
  language,
  onLanguageChange,
  selectedTime,
}: {
  result: JourneyResponse | null;
  assistantResponse: AssistantApiResponse | null;
  mode: JourneyMode;
  assistantMode: AssistantMode;
  presentationMode?: boolean;
  language: AssistantLanguage;
  onLanguageChange: (language: AssistantLanguage) => void;
  selectedTime?: string;
}) {
  const health = useBackendHealth();
  const evidenceSummaries = result
    ? [result.origin.evidence?.summary, result.destination?.evidence?.summary].filter((summary) => summary !== undefined)
    : [];
  const requestedSources = evidenceSummaries.reduce((total, summary) => total + summary.requested_sources, 0);
  const usableSources = assistantResponse
    ? assistantResponse.evidence_summary.available_sources + assistantResponse.evidence_summary.degraded_sources
    : evidenceSummaries.reduce((total, summary) => total + summary.available_sources + summary.degraded_sources, 0);
  const totalSources = assistantResponse
    ? usableSources + assistantResponse.evidence_summary.pending_sources + assistantResponse.evidence_summary.unavailable_sources
    : requestedSources;
  const degradedSources = assistantResponse
    ? assistantResponse.evidence_summary.degraded_sources
    : evidenceSummaries.reduce((total, summary) => total + summary.degraded_sources, 0);
  const healthTone = health.isSuccess ? "success" : health.isError ? "danger" : "caution";
  const demonstration = mode === "demonstration" || assistantResponse?.routing_mode === "demonstration_fixture";
  const timestamp = assistantResponse?.generated_at ?? result?.generated_at ?? selectedTime;

  return <header className="app-header">
    <div className="flex min-w-0 items-center gap-3">
      <div className="header-orca-mark" aria-hidden="true"><span /></div>
      <div className="min-w-0">
        <div className="flex items-center gap-2"><RadioTower aria-hidden="true" className="size-4 text-teal-300" /><h1 className="text-lg font-bold tracking-[0.08em] sm:text-xl">ORCA</h1></div>
        <p className="hidden text-xs text-slate-300 sm:block">Marine Intelligence</p>
      </div>
    </div>
    <div className="header-statuses">
      <Badge tone={healthTone}><Activity aria-hidden="true" className="size-3.5" />Backend {health.isSuccess ? "online" : health.isError ? "offline" : "checking"}</Badge>
      <Badge tone="info"><Database aria-hidden="true" className="size-3.5" />Live data</Badge>
      <Badge tone={degradedSources ? "caution" : totalSources ? "success" : "neutral"}><ShieldCheck aria-hidden="true" className="size-3.5" />{totalSources ? `${usableSources}/${totalSources} sources usable` : "Evidence pending"}</Badge>
      <Badge className="hidden xl:inline-flex"><Clock3 aria-hidden="true" className="size-3.5" />{timestamp ? new Date(timestamp).toLocaleString() : "No time selected"}</Badge>
      <label className="language-control"><Languages aria-hidden="true" className="size-4" /><span className="sr-only">Assistant language</span><select aria-label="Assistant language" value={language} onChange={(event) => onLanguageChange(event.target.value as AssistantLanguage)}>{languages.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <InformationDialog />
    </div>
    <span className="sr-only">Assistant mode: {assistantMode}</span>
  </header>;
}
