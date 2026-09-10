"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Bot, Languages, RadioTower, Sparkles } from "lucide-react";
import { AskOrcaPanel } from "@/components/conversation/ask-orca-panel";
import { AssistantResultPanel } from "@/components/evidence/assistant-result-panel";
import { SourceDrawer } from "@/components/evidence/source-drawer";
import { SpatialMapDialog } from "@/components/map/spatial-map-dialog";
import { useAssistant } from "@/hooks/use-assistant";
import { publicConfig } from "@/lib/config";
import type { EvidenceReference } from "@/lib/schemas/assistant";
import type { AssistantContextValues, AssistantLanguage } from "@/lib/schemas/assistant-api";
import type { JourneyResponse } from "@/lib/schemas/journey";

const languages: { value: AssistantLanguage; label: string }[] = [
  { value: "en", label: "English" },
  { value: "hi", label: "हिन्दी (Hindi)" },
  { value: "gu", label: "ગુજરાતી (Gujarati)" },
  { value: "mr", label: "मराठी (Marathi)" },
  { value: "ta", label: "தமிழ் (Tamil)" },
  { value: "te", label: "తెలుగు (Telugu)" },
  { value: "ml", label: "മലയാളം (Malayalam)" },
  { value: "bn", label: "বাংলা (Bengali)" },
];

const defaultContext: AssistantContextValues = {
  latitude: "20.5000",
  longitude: "72.9000",
  requestedTimeLocal: "",
  waveLimit: "2.0",
  windLimit: "12.0",
  currentLimit: "1.0",
};

export default function ChatWindow() {
  const router = useRouter();
  const [language, setLanguage] = useState<AssistantLanguage>("en");
  const [assistantContext, setAssistantContext] = useState<AssistantContextValues>(defaultContext);
  const [contextOpen, setContextOpen] = useState(false);
  const [selectedResult, setSelectedResult] = useState<JourneyResponse | null>(null);

  const assistant = useAssistant(publicConfig.assistantMode, language, assistantContext);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const handleResultSelect = (result: JourneyResponse) => {
    setSelectedResult(result);
    try {
      localStorage.setItem("orca_active_spatial_result", JSON.stringify(result));
    } catch {
      // Ignore storage failures
    }
    router.push("/map");
  };

  const handleEvidenceSelect = (reference: EvidenceReference) => {
    document.getElementById("assistant-result-panel")?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="max-w-6xl mx-auto p-3 md:p-6 space-y-6">
      {/* Top Bar with Language Selector and Telemetry */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-cyan/10 border border-cyan/30 flex items-center justify-center text-cyan shadow-sm">
            <Bot size={22} />
          </div>
          <div>
            <h1 className="font-display font-bold text-lg md:text-xl text-text-primary flex items-center gap-2">
              ORCA Marine Intelligence
              <span className="hidden sm:inline-flex items-center gap-1 text-[11px] font-mono font-semibold px-2 py-0.5 rounded-full bg-cyan/10 text-cyan border border-cyan/30">
                <RadioTower size={11} className="animate-pulse" />
                Live verified
              </span>
            </h1>
            <p className="text-xs text-text-muted">
              Evidence-backed coastal reasoning, official INCOIS PFZ bulletins & satellite marine feeds
            </p>
          </div>
        </div>

        {/* Language Selector Dropdown */}
        <div className="flex items-center gap-2 bg-surface border border-border rounded-xl px-3 py-1.5 shadow-sm">
          <Languages size={15} className="text-cyan shrink-0" />
          <label htmlFor="orca-language-select" className="sr-only">
            Select Language
          </label>
          <select
            id="orca-language-select"
            value={language}
            onChange={(e) => setLanguage(e.target.value as AssistantLanguage)}
            className="bg-transparent text-xs font-semibold text-text-primary outline-none cursor-pointer"
          >
            {languages.map((lang) => (
              <option key={lang.value} value={lang.value} className="bg-surface text-text-primary">
                {lang.label}
              </option>
            ))}
          </select>
          <span className="hidden lg:inline-block text-[10px] text-text-muted pl-1 border-l border-border font-mono">
            Auto-detects queries
          </span>
        </div>
      </div>

      {/* Main Conversation Panel */}
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
        onSwitchSession={assistant.switchSession}
        onDeleteSession={assistant.deleteSession}
        onContextChange={setAssistantContext}
        onContextOpenChange={setContextOpen}
        onSend={(text, actionId) => assistant.send(text, actionId)}
        onCancel={assistant.cancel}
        onReset={assistant.reset}
        onLoadDemo={assistant.loadDemonstration}
        onRetry={assistant.retry}
        canRetry={assistant.canRetry}
        onQuickAction={(id, text) => assistant.send(text, id)}
        onEvidenceSelect={handleEvidenceSelect}
        onResultSelect={handleResultSelect}
      />

      {/* Assistant Analysis Result & Spatial Context */}
      {assistant.latestResponse && (
        <div id="assistant-result-panel" className="space-y-4 pt-2">
          <SpatialMapDialog result={assistant.latestResponse.geojson ? assistant.latestResponse : null} />
          <AssistantResultPanel response={assistant.latestResponse} />
        </div>
      )}

      {/* Source Provenance Drawer */}
      <SourceDrawer result={selectedResult} />
    </div>
  );
}