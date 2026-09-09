"use client";

import { EvidenceSource } from "@/lib/types";
import { Database, ShieldCheck, Radio, Satellite, Waves, Eye, X } from "lucide-react";

interface EvidencePanelProps {
  sources: EvidenceSource[];
  onClose?: () => void;
  inline?: boolean;
}

const categoryIcons = {
  weather: Radio,
  satellite: Satellite,
  ocean: Waves,
  gis: ShieldCheck,
  ais: Eye,
};

export default function EvidencePanel({ sources, onClose, inline = false }: EvidencePanelProps) {
  return (
    <div className={`rounded-xl border border-border bg-surface-light/80 p-4 ${inline ? "" : "shadow-xl"}`}>
      <div className="flex items-center justify-between pb-3 border-b border-border/60 mb-3">
        <div className="flex items-center gap-2">
          <Database size={16} className="text-cyan" />
          <h3 className="text-xs uppercase tracking-wider text-text-muted font-bold">
            Telemetry & Evidence Verification
          </h3>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary p-1 rounded-md hover:bg-surface"
          >
            <X size={14} />
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {sources.map((source) => {
          const CategoryIcon = categoryIcons[source.category] || Database;
          return (
            <div
              key={source.id || source.label}
              className="p-3 rounded-lg bg-surface border border-border flex flex-col justify-between gap-2"
            >
              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5 text-cyan">
                    <CategoryIcon size={14} />
                    <span className="text-[11px] font-semibold uppercase">{source.category}</span>
                  </div>
                  <span className="text-[10px] bg-go/10 text-go border border-go/30 px-1.5 py-0.5 rounded font-medium">
                    {source.confidence}% Conf.
                  </span>
                </div>
                <h4 className="text-xs font-semibold text-text-primary">{source.sourceName || source.label}</h4>
                <p className="text-[11px] text-text-muted mt-0.5">{source.label}</p>
              </div>

              <div className="pt-2 border-t border-border/40 flex items-center justify-between text-[10px]">
                <span className="font-mono text-cyan/90 font-medium">{source.metric}</span>
                <span className="text-text-muted">{source.fetchedAgo}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}