"use client";

import { mockAgentPipelines, mockEvidenceSources } from "@/lib/mockData";
import {
  Database,
  Bot,
  CheckCircle2,
  Cpu,
  Server,
  Radio,
  Zap,
  RefreshCw,
} from "lucide-react";
import { useState } from "react";
import EvidencePanel from "@/components/shared/EvidencePanel";

export default function DataPage() {
  const [syncing, setSyncing] = useState(false);

  const triggerSync = () => {
    setSyncing(true);
    setTimeout(() => {
      setSyncing(false);
    }, 1200);
  };

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-cyan/10 border border-cyan/30 flex items-center justify-center text-cyan">
              <Database size={18} />
            </div>
            <h1 className="font-display font-black text-2xl md:text-3xl text-text-primary">
              Data Pipeline & Agent Registry
            </h1>
          </div>
          <p className="text-text-muted text-xs md:text-sm mt-1">
            Telemetry ingestion pipelines, autonomous agents, and verified marine sensor networks.
          </p>
        </div>

        <button
          onClick={triggerSync}
          disabled={syncing}
          className="px-4 py-2 rounded-xl bg-surface-light hover:bg-surface border border-border text-xs font-semibold text-cyan hover:border-cyan/40 transition-all flex items-center gap-2 shadow-sm"
        >
          <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
          <span>{syncing ? "Pinging Agents..." : "Sync Agent Registry"}</span>
        </button>
      </div>

      {/* Pipeline Performance Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        <div className="p-4 rounded-xl border border-border bg-surface">
          <div className="flex items-center justify-between text-text-muted text-xs mb-1">
            <span>Active Agents</span>
            <Bot size={16} className="text-cyan" />
          </div>
          <p className="text-2xl font-display font-bold text-text-primary">5 / 5</p>
          <p className="text-[11px] text-go font-medium mt-0.5">● All nodes operational</p>
        </div>

        <div className="p-4 rounded-xl border border-border bg-surface">
          <div className="flex items-center justify-between text-text-muted text-xs mb-1">
            <span>Mean Pipeline Latency</span>
            <Zap size={16} className="text-wait" />
          </div>
          <p className="text-2xl font-display font-bold text-text-primary">256 ms</p>
          <p className="text-[11px] text-cyan font-medium mt-0.5">99.4% SLA adherence</p>
        </div>

        <div className="p-4 rounded-xl border border-border bg-surface">
          <div className="flex items-center justify-between text-text-muted text-xs mb-1">
            <span>Sensor Feeds Ingested</span>
            <Radio size={16} className="text-go" />
          </div>
          <p className="text-2xl font-display font-bold text-text-primary">12 Feeds</p>
          <p className="text-[11px] text-text-muted mt-0.5">INCOIS, NOAA, IMD, AIS</p>
        </div>

        <div className="p-4 rounded-xl border border-border bg-surface">
          <div className="flex items-center justify-between text-text-muted text-xs mb-1">
            <span>Consensus Accuracy</span>
            <CheckCircle2 size={16} className="text-cyan" />
          </div>
          <p className="text-2xl font-display font-bold text-text-primary">99.2%</p>
          <p className="text-[11px] text-go font-medium mt-0.5">Cross-validated</p>
        </div>
      </div>

      {/* Autonomous Multi-Agent Registry */}
      <div>
        <h2 className="text-sm uppercase tracking-wider font-bold text-text-muted mb-3 flex items-center gap-2">
          <Cpu size={15} className="text-cyan" />
          <span>Registered Autonomous Agents</span>
        </h2>

        <div className="space-y-3">
          {mockAgentPipelines.map((agent) => (
            <div
              key={agent.id}
              className="p-4 rounded-2xl border border-border bg-surface hover:border-cyan/40 transition-all flex flex-col md:flex-row md:items-center justify-between gap-3"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-text-primary">{agent.name}</h3>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-go/10 text-go border border-go/30 font-bold uppercase font-mono">
                    {agent.status}
                  </span>
                </div>
                <p className="text-xs text-text-muted mt-0.5 leading-relaxed">{agent.role}</p>
                <p className="text-[11px] text-cyan font-mono mt-1">Feeds: {agent.dataFeed}</p>
              </div>

              <div className="flex items-center gap-4 text-xs font-mono shrink-0 pt-2 md:pt-0 border-t md:border-t-0 border-border/40">
                <div className="text-right">
                  <span className="text-[10px] text-text-muted block">Avg Latency</span>
                  <span className="text-text-primary font-bold">{agent.avgLatency}</span>
                </div>
                <div className="text-right">
                  <span className="text-[10px] text-text-muted block">Accuracy</span>
                  <span className="text-go font-bold">{agent.accuracy}</span>
                </div>
                <div className="text-right">
                  <span className="text-[10px] text-text-muted block">Last Sync</span>
                  <span className="text-text-muted">{agent.lastSync}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Verified Telemetry Feeds */}
      <div>
        <h2 className="text-sm uppercase tracking-wider font-bold text-text-muted mb-3 flex items-center gap-2">
          <Server size={15} className="text-cyan" />
          <span>Active Sensor & Satellite Telemetry Sources</span>
        </h2>
        <EvidencePanel sources={mockEvidenceSources} />
      </div>
    </div>
  );
}