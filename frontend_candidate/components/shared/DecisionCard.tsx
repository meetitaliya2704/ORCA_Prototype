"use client";

import { DecisionData, RiskLevel } from "@/lib/types";
import { CheckCircle2, AlertTriangle, XCircle, Shield, Info } from "lucide-react";
import { useState } from "react";
import EvidencePanel from "./EvidencePanel";
import { mockEvidenceSources } from "@/lib/mockData";

type StatusConfig = {
  color: string;
  badgeBg: string;
  bg: string;
  border: string;
  barColor: string;
  icon: typeof CheckCircle2;
  label: string;
  sublabel: string;
};

const statusConfig: Record<RiskLevel, StatusConfig> = {
  GO: {
    color: "text-go",
    badgeBg: "bg-go text-bg font-bold",
    bg: "bg-go/10",
    border: "border-go/40",
    barColor: "bg-go",
    icon: CheckCircle2,
    label: "GO",
    sublabel: "Conditions Favorable & Safe",
  },
  WAIT: {
    color: "text-wait",
    badgeBg: "bg-wait text-bg font-bold",
    bg: "bg-wait/10",
    border: "border-wait/40",
    barColor: "bg-wait",
    icon: AlertTriangle,
    label: "WAIT",
    sublabel: "Moderate Risk / Monitor Squalls",
  },
  AVOID: {
    color: "text-avoid",
    badgeBg: "bg-avoid text-white font-bold",
    bg: "bg-avoid/10",
    border: "border-avoid/40",
    barColor: "bg-avoid",
    icon: XCircle,
    label: "AVOID",
    sublabel: "Dangerous Conditions / No Sail",
  },
};

export default function DecisionCard({
  decision,
  onViewEvidence,
  showEvidenceButton = true,
}: {
  decision: DecisionData;
  onViewEvidence?: () => void;
  showEvidenceButton?: boolean;
}) {
  const [internalEvidenceOpen, setInternalEvidenceOpen] = useState(false);
  const config = statusConfig[decision.status] || statusConfig.GO;
  const Icon = config.icon;

  const handleEvidenceClick = () => {
    if (onViewEvidence) {
      onViewEvidence();
    } else {
      setInternalEvidenceOpen((prev) => !prev);
    }
  };

  return (
    <div className={`rounded-2xl border ${config.border} ${config.bg} p-5 md:p-6 backdrop-blur-sm relative overflow-hidden transition-all shadow-lg`}>
      {/* Background glow accent */}
      <div className={`absolute -right-12 -top-12 w-36 h-36 rounded-full ${config.bg} blur-3xl pointer-events-none`} />

      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Shield size={16} className={config.color} />
          <span className="text-xs uppercase tracking-wider text-text-muted font-bold">
            Autonomous Marine Decision
          </span>
        </div>
        <span className="text-xs font-mono text-text-muted">{decision.updatedAt}</span>
      </div>

      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex items-center gap-3.5">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${config.bg} border ${config.border}`}>
            <Icon className={config.color} size={30} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className={`font-display font-black text-3xl md:text-4xl tracking-tight ${config.color}`}>
                {config.label}
              </span>
              <span className={`text-[11px] px-2 py-0.5 rounded-full ${config.badgeBg} uppercase tracking-wider`}>
                Score: {decision.riskScore ?? 35}/100
              </span>
            </div>
            <p className="text-xs text-text-muted mt-0.5">{config.sublabel}</p>
          </div>
        </div>
      </div>

      <p className="text-sm font-semibold text-text-primary mb-1">{decision.headline}</p>
      {decision.location && (
        <p className="text-xs text-cyan font-mono mb-4">📍 {decision.location}</p>
      )}

      {decision.summary && (
        <p className="text-xs text-text-muted leading-relaxed mb-4 p-2.5 rounded-lg bg-surface/80 border border-border/50">
          {decision.summary}
        </p>
      )}

      {/* Risk metric bars */}
      <div className="space-y-3 mb-5">
        {decision.riskFactors.map((factor) => {
          const factorBarColor =
            factor.level === "AVOID"
              ? "bg-avoid"
              : factor.level === "WAIT"
              ? "bg-wait"
              : factor.level === "GO"
              ? "bg-go"
              : config.barColor;

          return (
            <div key={factor.label}>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-text-muted font-medium">{factor.label}</span>
                <span className="text-text-primary font-mono">{factor.value}</span>
              </div>
              <div className="h-2 rounded-full bg-surface-light overflow-hidden border border-border/40">
                <div
                  className={`h-full rounded-full ${factorBarColor} transition-all duration-500`}
                  style={{ width: `${factor.percent}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {decision.recommendation && (
        <div className="mb-4 flex items-start gap-2 p-2.5 rounded-lg bg-cyan/10 border border-cyan/30 text-cyan text-xs">
          <Info size={16} className="shrink-0 mt-0.5" />
          <p className="leading-snug">
            <span className="font-bold">Recommendation:</span> {decision.recommendation}
          </p>
        </div>
      )}

      {showEvidenceButton && (
        <button
          onClick={handleEvidenceClick}
          className={`w-full py-2.5 rounded-xl border ${config.border} ${config.color} text-xs font-bold uppercase tracking-wider hover:bg-surface-light/80 transition-all flex items-center justify-center gap-2`}
        >
          {internalEvidenceOpen ? "Hide Verification Evidence" : "View Multi-Agent Evidence"}
        </button>
      )}

      {internalEvidenceOpen && (
        <div className="mt-4">
          <EvidencePanel
            sources={mockEvidenceSources}
            onClose={() => setInternalEvidenceOpen(false)}
            inline
          />
        </div>
      )}
    </div>
  );
}