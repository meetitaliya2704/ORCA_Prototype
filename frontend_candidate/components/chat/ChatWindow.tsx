"use client";

import { useState, useRef, useEffect } from "react";
import { ChatMessage as ChatMessageType, DecisionData, AgentStep } from "@/lib/types";
import { mockChatMessages, mockWaitDecision, mockAvoidDecision, mockDecision, mockEvidenceSources, userModeConfigs } from "@/lib/mockData";
import { useUserMode } from "@/lib/context";
import ChatMessage from "./ChatMessage";
import { Send, Sparkles, RefreshCw, Loader2, Bot } from "lucide-react";

export default function ChatWindow() {
  const { mode } = useUserMode();
  const [messages, setMessages] = useState<ChatMessageType[]>(mockChatMessages);
  const [inputQuery, setInputQuery] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messageIdCounter = useRef(0);
  const nextMessageId = (prefix: string) => `${prefix}-${++messageIdCounter.current}`;

  const activeConfig = userModeConfigs[mode] || userModeConfigs.fisherman;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isProcessing]);

  const suggestedQuestions = [
    activeConfig.defaultPrompt,
    mode === "fisherman" ? "Is there high swell near Ratnagiri reef?" : "Report high-density AIS lanes in Sector 3",
    mode === "researcher" ? "Check thermal anomalies & chlorophyll index" : "Find least-risk corridor avoiding storm front",
  ];

  const handleSend = async (queryText?: string) => {
    const textToSend = (queryText || inputQuery).trim();
    if (!textToSend || isProcessing) return;

    setInputQuery("");

    const userMsg: ChatMessageType = {
      id: nextMessageId("u"),
      role: "user",
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      userMode: mode,
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsProcessing(true);

    setTimeout(() => {
      let resultDecision: DecisionData = mockDecision;
      let summaryText = "";

      const lower = textToSend.toLowerCase();
      if (lower.includes("cyclone") || lower.includes("storm") || lower.includes("kandla") || lower.includes("danger") || lower.includes("sector 4")) {
        resultDecision = mockAvoidDecision;
        summaryText = "AVOID — High hazard warning active. Multi-agent consensus reports gale-force winds exceeding safe vessel tolerance in this sector.";
      } else if (lower.includes("tomorrow") || lower.includes("swell") || lower.includes("ratnagiri") || lower.includes("wait")) {
        resultDecision = mockWaitDecision;
        summaryText = "WAIT — Moderate coastal risk detected. Squall formation expected in the morning. Re-evaluating with next satellite pass.";
      } else {
        resultDecision = mockDecision;
        summaryText = "GO — Safe operational window confirmed. Buoy telemetry, Doppler radar, and GIS channel barriers indicate low risk.";
      }

      const agentPipeline: AgentStep[] = [
        { name: "Marine Data Agent", status: "completed", detail: "Synchronized INCOIS buoys & tide telemetry", latencyMs: 120 },
        { name: "Meteorological Weather Agent", status: "completed", detail: "Radar reflectivity & GFS wind vector aligned", latencyMs: 190 },
        { name: "Ocean Analytics Agent", status: "completed", detail: "Wave surge & current vector computed", latencyMs: 280 },
        { name: "GIS & Spatial Agent", status: "completed", detail: "Marine protected zone overlay verified", latencyMs: 160 },
        { name: "Risk Assessment Agent", status: "completed", detail: "Multi-agent consensus arbitration resolved", latencyMs: 410 },
      ];

      const assistantMsg: ChatMessageType = {
        id: nextMessageId("a"),
        role: "assistant",
        text: summaryText,
        decision: resultDecision,
        agents: agentPipeline,
        sources: mockEvidenceSources,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setIsProcessing(false);
    }, 1800);
  };

  const handleReset = () => {
    setMessages(mockChatMessages);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] md:h-[calc(100vh-5rem)] max-w-5xl mx-auto p-3 md:p-6">
      {/* Header bar */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-cyan/10 border border-cyan/30 flex items-center justify-center text-cyan">
            <Bot size={22} />
          </div>
          <div>
            <h1 className="font-display font-bold text-lg md:text-xl text-text-primary">
              ORCA Marine Co-Pilot
            </h1>
            <p className="text-xs text-text-muted">
              Live reasoning engine tailored for: <span className="text-cyan font-semibold">{activeConfig.label}</span>
            </p>
          </div>
        </div>

        <button
          onClick={handleReset}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-light hover:bg-surface border border-border text-xs text-text-muted hover:text-text-primary transition-colors"
        >
          <RefreshCw size={12} />
          <span className="hidden sm:inline">Reset Session</span>
        </button>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto pr-2 space-y-4">
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {isProcessing && (
          <div className="flex justify-start mb-6">
            <div className="max-w-[85%] w-full bg-surface border border-border rounded-2xl rounded-tl-sm p-4 space-y-3">
              <div className="flex items-center gap-2 text-cyan">
                <Loader2 size={16} className="animate-spin" />
                <span className="text-xs font-bold uppercase tracking-wider">
                  Agents Synthesizing Real-Time Telemetry...
                </span>
              </div>
              <div className="space-y-1.5 text-xs text-text-muted font-mono">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-go animate-ping" />
                  <span>Polling Doppler Weather & Satellite passes...</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-wait animate-pulse" />
                  <span>Evaluating GIS corridors & bathymetry barriers...</span>
                </div>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested prompts */}
      <div className="pt-3 pb-2 flex items-center gap-2 overflow-x-auto no-scrollbar">
        <Sparkles size={14} className="text-cyan shrink-0" />
        <span className="text-[11px] text-text-muted font-medium shrink-0">Try asking:</span>
        {suggestedQuestions.map((q, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(q)}
            className="text-xs px-3 py-1.5 rounded-full bg-surface-light hover:bg-surface border border-border/80 text-text-primary hover:border-cyan/40 shrink-0 transition-all text-left truncate max-w-xs"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Input container */}
      <div className="relative pt-2">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-2 bg-surface border border-border rounded-2xl p-2 focus-within:border-cyan shadow-xl transition-colors"
        >
          <input
            type="text"
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            placeholder="Ask ORCA about sea states, routes, hazards or fishing zones..."
            className="flex-1 bg-transparent px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none"
            disabled={isProcessing}
          />
          <button
            type="submit"
            disabled={!inputQuery.trim() || isProcessing}
            className="w-10 h-10 rounded-xl bg-cyan hover:bg-cyan/90 disabled:opacity-40 text-bg font-bold flex items-center justify-center transition-all shrink-0"
          >
            {isProcessing ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </form>
      </div>
    </div>
  );
}