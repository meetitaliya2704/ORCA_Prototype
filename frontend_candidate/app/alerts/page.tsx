"use client";

import { useState } from "react";
import { mockAlerts } from "@/lib/mockData";
import { useUserMode } from "@/lib/context";
import {
  Bell,
  AlertTriangle,
  Search,
  CheckCircle2,
} from "lucide-react";

export default function AlertsPage() {
  const { mode } = useUserMode();
  const [filterSeverity, setFilterSeverity] = useState<string>("all");
  const [acknowledged, setAcknowledged] = useState<Record<string, boolean>>({});
  const [searchQuery, setSearchQuery] = useState("");

  const toggleAcknowledge = (id: string) => {
    setAcknowledged((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const filteredAlerts = mockAlerts.filter((alert) => {
    if (filterSeverity !== "all" && alert.severity !== filterSeverity) return false;
    if (
      searchQuery &&
      !alert.title.toLowerCase().includes(searchQuery.toLowerCase()) &&
      !alert.region.toLowerCase().includes(searchQuery.toLowerCase())
    ) {
      return false;
    }
    return true;
  });

  return (
    <div className="p-4 md:p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-avoid/10 border border-avoid/30 flex items-center justify-center text-avoid">
              <Bell size={18} />
            </div>
            <h1 className="font-display font-black text-2xl md:text-3xl text-text-primary">
              Marine Alerts & Advisories
            </h1>
          </div>
          <p className="text-text-muted text-xs md:text-sm mt-1">
            Official coastal warnings, small craft advisories, and navigational hazard bulletins.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs bg-surface-light border border-border px-3 py-1.5 rounded-lg text-cyan font-mono">
            {mockAlerts.length} Active Bulletins
          </span>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {["all", "high", "medium", "low"].map((sev) => (
            <button
              key={sev}
              onClick={() => setFilterSeverity(sev)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wider transition-all ${
                filterSeverity === sev
                  ? "bg-cyan text-bg font-bold"
                  : "bg-surface-light text-text-muted hover:text-text-primary"
              }`}
            >
              {sev}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 bg-surface-light border border-border rounded-xl px-3 py-1.5 text-xs w-full sm:w-64">
          <Search size={14} className="text-text-muted shrink-0" />
          <input
            type="text"
            placeholder="Search region or advisory..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-transparent outline-none text-text-primary placeholder:text-text-muted w-full"
          />
        </div>
      </div>

      {/* Alerts List */}
      <div className="space-y-4">
        {filteredAlerts.map((alert) => {
          const isAck = acknowledged[alert.id];
          const isHigh = alert.severity === "high";
          const isMed = alert.severity === "medium";

          return (
            <div
              key={alert.id}
              className={`p-5 rounded-2xl border transition-all shadow-md ${
                isHigh
                  ? "bg-avoid/10 border-avoid/40"
                  : isMed
                  ? "bg-wait/10 border-wait/40"
                  : "bg-surface border-border"
              }`}
            >
              <div className="flex items-start justify-between gap-3 mb-2">
                <div className="flex items-center gap-2.5">
                  <div
                    className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                      isHigh ? "bg-avoid text-white" : isMed ? "bg-wait text-bg font-bold" : "bg-cyan/20 text-cyan"
                    }`}
                  >
                    <AlertTriangle size={16} />
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-bold tracking-wider font-mono text-text-muted">
                      {alert.region} • Issued {alert.issuedAt}
                    </span>
                    <h3 className="text-base font-bold text-text-primary">{alert.title}</h3>
                  </div>
                </div>

                <span
                  className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full ${
                    isHigh
                      ? "bg-avoid text-white"
                      : isMed
                      ? "bg-wait text-bg font-bold"
                      : "bg-surface-light text-cyan border border-cyan/30"
                  }`}
                >
                  {alert.severity} Priority
                </span>
              </div>

              <p className="text-xs md:text-sm text-text-primary/90 leading-relaxed mb-4 pl-10">
                {alert.description}
              </p>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-3 border-t border-border/60 pl-10">
                {alert.coordinates && (
                  <span className="text-xs font-mono text-text-muted">
                    📍 Coordinates: {alert.coordinates}
                  </span>
                )}

                <div className="flex items-center gap-2 self-end sm:self-auto">
                  <button
                    onClick={() => toggleAcknowledge(alert.id)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all ${
                      isAck
                        ? "bg-go text-bg font-bold"
                        : "bg-surface-light border border-border text-text-muted hover:text-text-primary"
                    }`}
                  >
                    <CheckCircle2 size={13} />
                    <span>{isAck ? "Acknowledged" : "Acknowledge"}</span>
                  </button>
                </div>
              </div>
            </div>
          );
        })}

        {filteredAlerts.length === 0 && (
          <div className="p-8 text-center bg-surface border border-border rounded-2xl text-text-muted">
            <p className="text-sm">No marine alerts found matching your filter criteria.</p>
          </div>
        )}
      </div>
    </div>
  );
}