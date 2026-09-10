"use client";

import { AlertTriangle, ChevronDown, FlaskConical, LoaderCircle, RefreshCw, Settings2, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";
import { Header } from "./header";
import { WorkspaceSidebar } from "./workspace-sidebar";
import { AskOrcaPanel } from "@/components/conversation/ask-orca-panel";
import { AssistantResultPanel } from "@/components/evidence/assistant-result-panel";
import { EvidenceGrid } from "@/components/evidence/evidence-grid";
import { SourceDrawer } from "@/components/evidence/source-drawer";
import { JourneyForm } from "@/components/journey/journey-form";
import { JourneyPanel } from "@/components/journey/journey-panel";
import { SpatialMapDialog } from "@/components/map/spatial-map-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useAssistant } from "@/hooks/use-assistant";
import { useJourney } from "@/hooks/use-journey";
import { publicConfig } from "@/lib/config";
import type { MarineSourceName } from "@/lib/formatters/marine";
import type { EvidenceReference } from "@/lib/schemas/assistant";
import type { AssistantContextValues, AssistantLanguage } from "@/lib/schemas/assistant-api";
import type { JourneyRequest, JourneyResponse } from "@/lib/schemas/journey";

const defaultContext: AssistantContextValues = {
  latitude: "20.5000",
  longitude: "72.9000",
  requestedTimeLocal: "",
  waveLimit: "2.0",
  windLimit: "12.0",
  currentLimit: "1.0",
};

export function OrcaDashboard() {
  const journey = useJourney();
  const [language, setLanguage] = useState<AssistantLanguage>("en");
  const [assistantContext, setAssistantContext] = useState<AssistantContextValues>(defaultContext);
  const assistant = useAssistant(publicConfig.assistantMode, language, assistantContext);
  const [locationTab, setLocationTab] = useState<"origin" | "destination">("origin");
  const [queryExpanded, setQueryExpanded] = useState(false);
  const [contextOpen, setContextOpen] = useState(true);
  const [resultsExpanded, setResultsExpanded] = useState(true);
  const [focusedSource, setFocusedSource] = useState<MarineSourceName | null>(null);
  const [selectedResult, setSelectedResult] = useState<JourneyResponse | null>(null);
  const [resultView, setResultView] = useState<"assistant" | "journey">("assistant");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const displayedResult = selectedResult ?? journey.result;
  const selectedEvidence = locationTab === "origin" ? displayedResult?.origin.evidence : displayedResult?.destination?.evidence;
  const spatialResult = resultView === "assistant" && assistant.latestResponse?.geojson ? assistant.latestResponse : displayedResult;

  useEffect(() => { document.documentElement.lang = language; }, [language]);

  const focusEvidence = (reference: EvidenceReference) => {
    if (reference.source === "pfz") {
      document.getElementById("answer-evidence-panel")?.focus();
      return;
    }
    if (displayedResult) {
      setResultView("journey");
      setLocationTab(reference.location ?? "origin");
      setFocusedSource(reference.source);
      window.setTimeout(() => document.getElementById(`evidence-${reference.source}`)?.focus(), 0);
    } else {
      document.getElementById("assistant-result-panel")?.focus();
    }
  };

  const sendAssistant = (text: string, actionId?: string) => {
    setResultView("assistant");
    assistant.send(text, actionId);
  };

  const quickAction = (id: string, text: string) => {
    if (publicConfig.assistantMode === "live" || publicConfig.assistantMode === "demo") {
      sendAssistant(text, id);
      return;
    }
    if (id === "find_pfz" || id === "assess_limits") {
      setQueryExpanded(true);
      setContextOpen(true);
      assistant.addClarification(["location", "operational_limits"]);
      return;
    }
    assistant.send(text, id);
  };

  const submitJourney = async (request: JourneyRequest) => {
    setSelectedResult(null);
    setResultView("journey");
    const result = await journey.submit(request);
    if (result) assistant.addDeterministicResult(result);
  };

  const loadConversation = async () => {
    if (assistant.loadDemonstration()) {
      const result = await journey.loadDemo();
      if (result) {
        setSelectedResult(result);
        setResultView("journey");
      }
    }
  };

  const startNewAnalysis = () => {
    assistant.reset();
    journey.reset();
    setSelectedResult(null);
    setFocusedSource(null);
    setResultView("assistant");
    setAssistantContext(defaultContext);
    document.getElementById("assistant-message")?.focus();
  };

  const navigationAction = (id: "new" | "conversation" | "demo" | "sources") => {
    if (id === "new") startNewAnalysis();
    if (id === "conversation") {
      setResultView("assistant");
      document.getElementById("assistant-workspace")?.scrollIntoView({ behavior: "smooth" });
      document.getElementById("assistant-message")?.focus();
    }
    if (id === "demo") loadConversation();
    if (id === "sources") document.getElementById("source-provenance")?.scrollIntoView({ behavior: "smooth" });
  };

  return <div className={`workspace-shell ${sidebarCollapsed ? "sidebar-is-collapsed" : ""}`}>
    <WorkspaceSidebar collapsed={sidebarCollapsed} onCollapsedChange={setSidebarCollapsed} mobileOpen={mobileNavigationOpen} onMobileOpenChange={setMobileNavigationOpen} onAction={navigationAction} conversationActive={assistant.messages.length > 0} demoEnabled={publicConfig.demoMode || publicConfig.assistantMode === "demo"} />
    <div className="workspace-content min-w-0">
      <Header result={displayedResult} assistantResponse={assistant.latestResponse} mode={journey.mode} assistantMode={publicConfig.assistantMode} presentationMode={publicConfig.presentationMode} language={language} onLanguageChange={setLanguage} selectedTime={assistantContext.requestedTimeLocal} />

      {(journey.isSubmitting || journey.pending || journey.error) && <div className="mx-auto w-full max-w-[1720px] px-3 pt-3 sm:px-5">
        <Card className={journey.error ? "border-[var(--danger)]" : "border-[var(--information)]"} role={journey.error ? "alert" : "status"} aria-live={journey.error ? "assertive" : "polite"}>
          <CardContent className="flex flex-wrap items-center gap-3 py-3">
            {journey.error ? journey.error.code === "NETWORK_UNAVAILABLE" ? <WifiOff aria-hidden="true" className="size-5 text-[var(--danger)]" /> : <AlertTriangle aria-hidden="true" className="size-5 text-[var(--caution)]" /> : <LoaderCircle aria-hidden="true" className="size-5 animate-spin text-[var(--information)]" />}
            <div className="min-w-0 flex-1"><p className="font-semibold">{journey.error ? "Journey request could not be displayed" : journey.pending ? "Official data refresh in progress" : "Collecting marine evidence"}</p><p className="text-sm text-[var(--muted-foreground)]">{journey.error?.message ?? (journey.pending ? "You can continue using the workspace while ORCA checks refresh status." : "Independent sources may finish at different times.")}</p>{journey.error?.diagnostic && <details className="mt-2 text-xs"><summary className="cursor-pointer">Development diagnostic</summary><code className="long-token block">{journey.error.diagnostic}</code></details>}</div>
            {journey.error && <Button variant="secondary" onClick={journey.retry}><RefreshCw aria-hidden="true" className="size-4" />Retry</Button>}
          </CardContent>
        </Card>
      </div>}

      <main id="main-content" className="professional-dashboard-grid" tabIndex={-1}>
        <section id="assistant-workspace" className="chat-panel min-w-0">
          <AskOrcaPanel
            mode={publicConfig.assistantMode}
            presentationMode={publicConfig.presentationMode}
            messages={assistant.messages}
            busy={assistant.busy}
            fixtureError={assistant.fixtureError}
            context={assistantContext}
            contextOpen={contextOpen}
            conversationId={assistant.conversationId}
            sessions={assistant.sessions}
            activeSessionId={assistant.activeSessionId}
            onSwitchSession={(id) => {
              assistant.switchSession(id);
              setResultView("assistant");
            }}
            onDeleteSession={assistant.deleteSession}
            onContextChange={setAssistantContext}
            onContextOpenChange={setContextOpen}
            onSend={sendAssistant}
            onCancel={assistant.cancel}
            onReset={startNewAnalysis}
            onLoadDemo={loadConversation}
            onRetry={assistant.retry}
            canRetry={Boolean(assistant.lastError)}
            onQuickAction={quickAction}
            onEvidenceSelect={focusEvidence}
            onResultSelect={(result) => { setSelectedResult(result); setResultView("journey"); }}
          />
        </section>

        <section id="answer-evidence-panel" className="results-panel min-w-0" tabIndex={-1}>
          <button type="button" className="tablet-panel-toggle" aria-expanded={resultsExpanded} onClick={() => setResultsExpanded((value) => !value)}>Answer and evidence<ChevronDown aria-hidden="true" className={`size-4 transition-transform ${resultsExpanded ? "rotate-180" : ""}`} /></button>
          <div className={resultsExpanded ? "tablet-panel-content space-y-3" : "tablet-panel-content tablet-collapsed"}>
            <div id="assistant-result-panel" tabIndex={-1}>{resultView === "assistant" ? <AssistantResultPanel response={assistant.latestResponse} /> : <JourneyPanel result={displayedResult} demonstration={journey.mode === "demonstration"} />}</div>
            {resultView === "journey" && displayedResult && <Card><CardHeader><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-bold">Marine evidence and explanation</h2><div className="flex rounded-md border border-[var(--border)] p-1" role="group" aria-label="Evidence location"><Button variant={locationTab === "origin" ? "primary" : "ghost"} className="min-h-9 px-2 py-1" aria-pressed={locationTab === "origin"} onClick={() => setLocationTab("origin")}>Origin</Button><Button variant={locationTab === "destination" ? "primary" : "ghost"} className="min-h-9 px-2 py-1" aria-pressed={locationTab === "destination"} onClick={() => setLocationTab("destination")}>PFZ</Button></div></div></CardHeader><CardContent>{selectedEvidence ? <EvidenceGrid evidence={selectedEvidence} focusedSource={focusedSource} /> : <div className="py-8 text-center"><FlaskConical aria-hidden="true" className="mx-auto size-8 text-[var(--muted-foreground)]" /><p className="mt-2">Evidence was not available for this location.</p></div>}</CardContent></Card>}
            <SpatialMapDialog result={spatialResult} />
          </div>
        </section>

        <section className="advanced-panel min-w-0"><button type="button" className="advanced-toggle" aria-expanded={queryExpanded} onClick={() => setQueryExpanded((value) => !value)}><Settings2 aria-hidden="true" className="size-4" />Advanced query parameters<ChevronDown aria-hidden="true" className={`ml-auto size-4 transition-transform ${queryExpanded ? "rotate-180" : ""}`} /></button><div className={queryExpanded ? "mt-3" : "hidden"}><JourneyForm onSubmit={submitJourney} onDemo={journey.loadDemo} onCancel={journey.cancel} submitting={journey.isSubmitting} demoEnabled={publicConfig.demoMode} onValidationIssues={(missing) => assistant.addClarification(missing)} /></div></section>
        <div id="source-provenance"><SourceDrawer result={displayedResult} /></div>
      </main>
    </div>
  </div>;
}
