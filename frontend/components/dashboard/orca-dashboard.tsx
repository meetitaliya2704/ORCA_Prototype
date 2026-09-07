"use client";

import { AlertTriangle, ChevronDown, FlaskConical, LoaderCircle, RefreshCw, Settings2, WifiOff } from "lucide-react";
import { useState } from "react";
import { Header } from "./header";
import { JourneyForm } from "@/components/journey/journey-form";
import { JourneyPanel } from "@/components/journey/journey-panel";
import { SpatialMapDialog } from "@/components/map/spatial-map-dialog";
import { EvidenceGrid } from "@/components/evidence/evidence-grid";
import { SourceDrawer } from "@/components/evidence/source-drawer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useJourney } from "@/hooks/use-journey";
import { publicConfig } from "@/lib/config";
import { useAssistant } from "@/hooks/use-assistant";
import { AskOrcaPanel } from "@/components/conversation/ask-orca-panel";
import type { EvidenceReference } from "@/lib/schemas/assistant";
import type { MarineSourceName } from "@/lib/formatters/marine";
import type { JourneyRequest, JourneyResponse } from "@/lib/schemas/journey";

export function OrcaDashboard() {
  const journey = useJourney();
  const assistant = useAssistant(publicConfig.assistantMode);
  const [locationTab, setLocationTab] = useState<"origin" | "destination">("origin");
  const [queryExpanded, setQueryExpanded] = useState(false);
  const [resultsExpanded, setResultsExpanded] = useState(true);
  const [focusedSource, setFocusedSource] = useState<MarineSourceName | null>(null);
  const [selectedResult, setSelectedResult] = useState<JourneyResponse | null>(null);
  const displayedResult = selectedResult ?? journey.result;
  const selectedEvidence = locationTab === "origin" ? displayedResult?.origin.evidence : displayedResult?.destination?.evidence;
  const focusEvidence = (reference: EvidenceReference) => {
    if (reference.source === "pfz") { document.getElementById("journey-result-panel")?.focus(); return; }
    setLocationTab(reference.location ?? "origin"); setFocusedSource(reference.source);
    window.setTimeout(() => document.getElementById(`evidence-${reference.source}`)?.focus(), 0);
  };
  const quickAction = (id: string, text: string) => {
    if (id === "find_pfz" || id === "open_advanced_parameters") { setQueryExpanded(true); assistant.addClarification(["location", "operational_limits"]); return; }
    if (id === "tomorrow_limits") { setQueryExpanded(true); assistant.addSystemNotice("Future model evidence can be checked with a timezone-aware request time and user-supplied limits. Official warning coverage remains incomplete, so this capability is partially available."); return; }
    if (id === "official_alerts") { assistant.addSystemNotice("Planned capability: authorized cyclone and lightning warning integrations are not available in this prototype. Verify current authority-issued advisories independently."); return; }
    if (id === "regional_indicators") { assistant.addSystemNotice("Planned capability: the current journey compares point evidence and does not provide regional SST or chlorophyll screening."); return; }
    if (id === "avoid_zones") { assistant.addSystemNotice("Planned capability: route-level avoidance and verified restricted-zone screening are not implemented. No avoidance answer can be produced yet."); return; }
    assistant.send(text, id);
  };
  const submitJourney = async (request: JourneyRequest) => { setSelectedResult(null); const result = await journey.submit(request); if (result) assistant.addDeterministicResult(result); };
  const loadConversation = async () => { if (assistant.loadDemonstration()) { const result = await journey.loadDemo(); if (result) setSelectedResult(result); } };
  return (
    <div className="min-h-dvh">
      <Header result={displayedResult} mode={journey.mode} assistantMode={publicConfig.assistantMode} presentationMode={publicConfig.presentationMode} />
      {(journey.isSubmitting || journey.pending || journey.error) && (
        <div className="mx-auto w-full max-w-[1800px] px-4 pt-4">
          <Card
            className={journey.error ? "border-[var(--danger)]" : "border-[var(--information)]"}
            role={journey.error ? "alert" : "status"}
            aria-live={journey.error ? "assertive" : "polite"}
          >
            <CardContent className="flex flex-wrap items-center gap-3 py-3">
              {journey.error
                ? journey.error.code === "NETWORK_UNAVAILABLE"
                  ? <WifiOff aria-hidden="true" className="size-5 text-[var(--danger)]" />
                  : <AlertTriangle aria-hidden="true" className="size-5 text-[var(--caution)]" />
                : <LoaderCircle aria-hidden="true" className="size-5 animate-spin text-[var(--information)]" />}
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {journey.error ? "Journey request could not be displayed" : journey.pending ? "Official data refresh in progress" : "Collecting marine evidence"}
                </p>
                <p className="text-sm text-[var(--muted-foreground)]">
                  {journey.error?.message ?? (journey.pending ? "You can continue using the dashboard while ORCA checks the refresh status." : "Independent sources may finish at different times.")}
                </p>
                {journey.error?.diagnostic && <details className="mt-2 text-xs"><summary className="cursor-pointer">Development diagnostic</summary><code className="long-token block">{journey.error.diagnostic}</code></details>}
              </div>
              {journey.error && <Button variant="secondary" onClick={journey.retry}><RefreshCw aria-hidden="true" className="size-4" />Retry</Button>}
            </CardContent>
          </Card>
        </div>
      )}
      <main id="main-content" className="dashboard-grid f1-dashboard-grid" tabIndex={-1}>
        <section className="chat-panel min-w-0"><AskOrcaPanel mode={publicConfig.assistantMode} presentationMode={publicConfig.presentationMode} messages={assistant.messages} busy={assistant.busy} fixtureError={assistant.fixtureError} onSend={assistant.send} onCancel={assistant.cancel} onReset={assistant.reset} onLoadDemo={loadConversation} onRetry={journey.retry} canRetry={Boolean(journey.error)} onQuickAction={quickAction} onEvidenceSelect={focusEvidence} onResultSelect={setSelectedResult} /></section>
        <section className="results-panel min-w-0" id="journey-result-panel" tabIndex={-1}>
          <button type="button" className="tablet-panel-toggle" aria-expanded={resultsExpanded} onClick={() => setResultsExpanded((value) => !value)}>PFZ journey and evidence<ChevronDown aria-hidden="true" className={`size-4 transition-transform ${resultsExpanded ? "rotate-180" : ""}`} /></button>
          <div className={resultsExpanded ? "tablet-panel-content space-y-3" : "tablet-panel-content tablet-collapsed"}><JourneyPanel result={displayedResult} demonstration={journey.mode === "demonstration"} />
          {displayedResult && <Card><CardHeader><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-bold">Marine evidence and explanation</h2><div className="flex rounded-md border border-[var(--border)] p-1" role="group" aria-label="Evidence location"><Button variant={locationTab === "origin" ? "primary" : "ghost"} className="min-h-9 px-2 py-1" aria-pressed={locationTab === "origin"} onClick={() => setLocationTab("origin")}>Origin</Button><Button variant={locationTab === "destination" ? "primary" : "ghost"} className="min-h-9 px-2 py-1" aria-pressed={locationTab === "destination"} onClick={() => setLocationTab("destination")}>PFZ</Button></div></div></CardHeader><CardContent>{selectedEvidence ? <EvidenceGrid evidence={selectedEvidence} focusedSource={focusedSource} /> : <div className="py-8 text-center"><FlaskConical aria-hidden="true" className="mx-auto size-8 text-[var(--muted-foreground)]" /><p className="mt-2">Evidence was not available for this location.</p></div>}</CardContent></Card>}
          <SpatialMapDialog result={displayedResult} /></div>
        </section>
        <section className="advanced-panel min-w-0"><button type="button" className="advanced-toggle" aria-expanded={queryExpanded} onClick={() => setQueryExpanded((value) => !value)}><Settings2 aria-hidden="true" className="size-4" />Advanced query parameters<ChevronDown aria-hidden="true" className={`ml-auto size-4 transition-transform ${queryExpanded ? "rotate-180" : ""}`} /></button><div className={queryExpanded ? "mt-3" : "hidden"}><JourneyForm onSubmit={submitJourney} onDemo={journey.loadDemo} onCancel={journey.cancel} submitting={journey.isSubmitting} demoEnabled={publicConfig.demoMode} onValidationIssues={(missing) => assistant.addClarification(missing)} /></div></section>
        <SourceDrawer result={displayedResult} />
      </main>
    </div>
  );
}
