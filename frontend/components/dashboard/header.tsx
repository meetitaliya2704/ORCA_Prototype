"use client";

import { Activity, Clock3, Database, RadioTower } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { InformationDialog } from "@/components/ui/dialog";
import { useBackendHealth } from "@/hooks/use-health";
import type { JourneyMode } from "@/hooks/use-journey";
import type { JourneyResponse } from "@/lib/schemas/journey";

export function Header({ result, mode, assistantMode, presentationMode }: { result: JourneyResponse | null; mode: JourneyMode; assistantMode?: "disabled" | "demo"; presentationMode?: boolean }) {
  const health = useBackendHealth();
  const evidenceSummaries = result
    ? [result.origin.evidence?.summary, result.destination?.evidence?.summary].filter((summary) => summary !== undefined)
    : [];
  const requestedSources = evidenceSummaries.reduce((total, summary) => total + summary.requested_sources, 0);
  const usableSources = evidenceSummaries.reduce((total, summary) => total + summary.available_sources + summary.degraded_sources, 0);
  const degradedSources = evidenceSummaries.reduce((total, summary) => total + summary.degraded_sources, 0);
  const healthTone = health.isSuccess ? "success" : health.isError ? "danger" : "caution";
  return (
    <header className="border-b border-slate-700 bg-[var(--primary)] text-white">
      <div className="mx-auto flex max-w-[1800px] flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2"><RadioTower aria-hidden="true" className="size-5 text-teal-300" /><h1 className="text-xl font-bold tracking-tight">ORCA</h1></div>
          <p className="text-sm text-slate-200">Marine Decision-Support Prototype</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2 text-sm">
          <Badge tone={healthTone}><Activity aria-hidden="true" className="size-3.5" />Backend {health.isSuccess ? "online" : health.isError ? "offline" : "checking"}</Badge>
          <Badge tone={mode === "demonstration" ? "caution" : "info"}><Database aria-hidden="true" className="size-3.5" />{mode === "demonstration" ? "Demonstration Snapshot" : "Live API mode"}</Badge>
          {assistantMode && <Badge tone={assistantMode === "demo" ? "caution" : "neutral"}>{assistantMode === "demo" ? "Demo conversation" : "Agent disabled"}</Badge>}
          {presentationMode && <Badge tone="info">Presentation mode</Badge>}
          <Badge><Clock3 aria-hidden="true" className="size-3.5" />{result ? new Date(result.generated_at).toLocaleString() : "No data selected"}</Badge>
          <Badge>{result ? `${usableSources}/${requestedSources} evidence sources usable · ${degradedSources} degraded` : "Awaiting query"}</Badge>
          <InformationDialog />
        </div>
      </div>
    </header>
  );
}
