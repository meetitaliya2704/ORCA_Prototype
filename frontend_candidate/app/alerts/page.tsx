"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useUserMode } from "@/lib/context";
import {
  Bell,
  AlertTriangle,
  Search,
  CheckCircle2,
  RefreshCw,
  Wind,
  Waves,
  MapPin,
  Share2,
  ShieldAlert,
  Check,
  Anchor,
  Compass,
  AlertOctagon,
} from "lucide-react";
import { fetchUnifiedAlerts, type UnifiedAlertItem } from "@/lib/api/warnings";

export default function AlertsPage() {
  const { mode } = useUserMode();
  const [alerts, setAlerts] = useState<UnifiedAlertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterSeverity, setFilterSeverity] = useState<string>("all");
  const [filterCategory, setFilterCategory] = useState<string>("all");
  const [acknowledged, setAcknowledged] = useState<Record<string, boolean>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  const loadAlerts = async () => {
    setLoading(true);
    try {
      const data = await fetchUnifiedAlerts();
      setAlerts(data);
      setLastRefreshed(new Date());
    } catch (err) {
      console.error("Failed to load live IMD marine alerts:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    try {
      const savedAck = sessionStorage.getItem("orca_alerts_acknowledged");
      if (savedAck) {
        setAcknowledged(JSON.parse(savedAck));
      }
    } catch {
      // Ignore storage errors
    }
    loadAlerts();
  }, []);

  const toggleAcknowledge = (id: string) => {
    setAcknowledged((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      try {
        sessionStorage.setItem("orca_alerts_acknowledged", JSON.stringify(next));
      } catch {
        // Ignore storage errors
      }
      return next;
    });
  };

  const copyAdvisory = (alert: UnifiedAlertItem) => {
    const text = `[ORCA / IMD Alert] ${alert.title}\nSeverity: ${alert.priorityLabel}\nRegion: ${alert.region}\nIssued: ${alert.issuedAt}\n\n${alert.description}`;
    navigator.clipboard.writeText(text);
    setCopiedId(alert.id);
    setTimeout(() => setCopiedId(null), 2500);
  };

  // Severity counts
  const highCount = alerts.filter((a) => a.severity === "high").length;
  const mediumCount = alerts.filter((a) => a.severity === "medium").length;
  const lowCount = alerts.filter((a) => a.severity === "low").length;
  const ventureNoSailCount = alerts.filter((a) => a.fishermenWarning).length;

  const filteredAlerts = alerts.filter((alert) => {
    if (filterSeverity !== "all" && alert.severity !== filterSeverity) return false;
    if (filterCategory !== "all" && alert.category !== filterCategory) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const matchTitle = alert.title.toLowerCase().includes(q);
      const matchRegion = alert.region.toLowerCase().includes(q);
      const matchDesc = alert.description.toLowerCase().includes(q);
      if (!matchTitle && !matchRegion && !matchDesc) return false;
    }
    return true;
  });

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl bg-avoid/10 border border-avoid/30 flex items-center justify-center text-avoid">
              <ShieldAlert size={20} />
            </div>
            <div>
              <h1 className="font-display font-black text-2xl md:text-3xl text-text-primary">
                Marine Alerts & Advisories
              </h1>
              <p className="text-text-muted text-xs md:text-sm mt-0.5">
                Official IMD coastal weather bulletins, port danger signals, and cyclone advisories.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          {lastRefreshed && (
            <span className="text-[11px] text-text-muted font-mono hidden sm:inline">
              Synced {lastRefreshed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <button
            onClick={loadAlerts}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-surface-light border border-border hover:bg-surface text-text-muted hover:text-text-primary flex items-center gap-1.5 transition-all disabled:opacity-50"
            title="Refresh alerts"
          >
            <RefreshCw size={13} className={loading ? "animate-spin text-cyan" : ""} />
            <span>{loading ? "Syncing..." : "Refresh"}</span>
          </button>
        </div>
      </div>

      {/* KPI Stats Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-xl border border-border bg-surface shadow-sm">
          <span className="text-[11px] text-text-muted font-mono uppercase">Total Bulletins</span>
          <div className="text-2xl font-black text-text-primary mt-1">{alerts.length}</div>
          <span className="text-[10px] text-text-muted">Aggregated Official Feeds</span>
        </div>

        <div className="p-3.5 rounded-xl border border-red-500/40 bg-red-950/15 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-red-400 font-mono uppercase font-bold">High Danger</span>
            {highCount > 0 && (
              <span className="w-2 h-2 rounded-full bg-red-500 animate-ping" />
            )}
          </div>
          <div className="text-2xl font-black text-red-400 mt-1">{highCount}</div>
          <span className="text-[10px] text-red-300/80">Cyclones & Danger Signals</span>
        </div>

        <div className="p-3.5 rounded-xl border border-amber-500/40 bg-amber-950/15 shadow-sm">
          <span className="text-[11px] text-amber-400 font-mono uppercase font-bold">Caution Advisories</span>
          <div className="text-2xl font-black text-amber-400 mt-1">{mediumCount}</div>
          <span className="text-[10px] text-amber-300/80">Port Signals & Gust Fronts</span>
        </div>

        <div className="p-3.5 rounded-xl border border-cyan/30 bg-cyan/5 shadow-sm">
          <span className="text-[11px] text-cyan font-mono uppercase font-bold">No-Sail Warnings</span>
          <div className="text-2xl font-black text-cyan mt-1">{ventureNoSailCount}</div>
          <span className="text-[10px] text-text-muted">Fishermen Venture Warnings</span>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Severity Tabs */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => setFilterSeverity("all")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              filterSeverity === "all"
                ? "bg-cyan text-bg font-bold shadow-sm"
                : "bg-surface-light text-text-muted hover:text-text-primary"
            }`}
          >
            All ({alerts.length})
          </button>
          <button
            onClick={() => setFilterSeverity("high")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1 ${
              filterSeverity === "high"
                ? "bg-red-500 text-white font-bold"
                : "bg-surface-light text-red-400 hover:bg-red-500/10"
            }`}
          >
            <AlertOctagon size={12} />
            <span>High ({highCount})</span>
          </button>
          <button
            onClick={() => setFilterSeverity("medium")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1 ${
              filterSeverity === "medium"
                ? "bg-amber-500 text-bg font-bold"
                : "bg-surface-light text-amber-400 hover:bg-amber-500/10"
            }`}
          >
            <AlertTriangle size={12} />
            <span>Caution ({mediumCount})</span>
          </button>
          <button
            onClick={() => setFilterSeverity("low")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              filterSeverity === "low"
                ? "bg-surface-light text-text-primary font-bold border border-border"
                : "bg-surface-light text-text-muted hover:text-text-primary"
            }`}
          >
            Routine ({lowCount})
          </button>
        </div>

        {/* Search Input */}
        <div className="flex items-center gap-2 bg-surface-light border border-border rounded-xl px-3 py-1.5 text-xs w-full md:w-80 shadow-sm">
          <Search size={14} className="text-text-muted shrink-0" />
          <input
            type="text"
            placeholder="Search port, coastal zone, or warning..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-transparent outline-none text-text-primary placeholder:text-text-muted w-full text-xs"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="text-text-muted hover:text-text-primary text-xs"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Category Pills */}
      <div className="flex items-center gap-2 text-xs text-text-muted flex-wrap">
        <span className="font-mono text-[10px] uppercase">Category:</span>
        {[
          { id: "all", label: "All Types" },
          { id: "cyclone", label: "Cyclones" },
          { id: "port_signal", label: "Port Signals" },
          { id: "squall", label: "Squally Weather" },
        ].map((cat) => (
          <button
            key={cat.id}
            onClick={() => setFilterCategory(cat.id)}
            className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
              filterCategory === cat.id
                ? "bg-surface text-cyan border border-cyan/40 font-semibold"
                : "bg-surface/50 text-text-muted hover:text-text-primary"
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Loading Skeleton */}
      {loading && alerts.length === 0 && (
        <div className="space-y-4">
          {[1, 2, 3].map((n) => (
            <div
              key={`skel-${n}`}
              className="p-5 rounded-2xl border border-border bg-surface animate-pulse space-y-3"
            >
              <div className="h-4 bg-surface-light rounded w-1/3" />
              <div className="h-6 bg-surface-light rounded w-2/3" />
              <div className="h-12 bg-surface-light rounded w-full" />
            </div>
          ))}
        </div>
      )}

      {/* Alerts Feed */}
      <div className="space-y-4">
        {filteredAlerts.map((alert) => {
          const isAck = acknowledged[alert.id];
          const isHigh = alert.severity === "high";
          const isMed = alert.severity === "medium";
          const isCopied = copiedId === alert.id;

          return (
            <div
              key={alert.id}
              className={`p-5 rounded-2xl border transition-all shadow-md relative overflow-hidden ${
                isAck
                  ? "opacity-60 bg-surface/40 border-border"
                  : isHigh
                  ? "bg-red-950/15 border-red-500/40 hover:border-red-500/60"
                  : isMed
                  ? "bg-amber-950/15 border-amber-500/40 hover:border-amber-500/60"
                  : "bg-surface border-border hover:border-cyan/30"
              }`}
            >
              {/* Top Accent Strip */}
              <div
                className={`absolute top-0 left-0 right-0 h-1 ${
                  isHigh ? "bg-red-500" : isMed ? "bg-amber-500" : "bg-cyan/40"
                }`}
              />

              {/* Title & Priority Row */}
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-2.5">
                <div className="flex items-start gap-3">
                  <div
                    className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 mt-0.5 ${
                      isHigh
                        ? "bg-red-500 text-white"
                        : isMed
                        ? "bg-amber-500 text-bg font-bold"
                        : "bg-cyan/20 text-cyan"
                    }`}
                  >
                    {alert.category === "cyclone" ? (
                      <Compass size={18} />
                    ) : alert.category === "port_signal" ? (
                      <Anchor size={18} />
                    ) : (
                      <AlertTriangle size={18} />
                    )}
                  </div>

                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] uppercase font-bold tracking-wider font-mono text-text-muted">
                        {alert.region}
                      </span>
                      <span className="text-text-muted text-[10px]">•</span>
                      <span className="text-[10px] text-text-muted font-mono">
                        Issued: {new Date(alert.issuedAt).toLocaleString([], {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                    <h3 className="text-base font-bold text-text-primary mt-0.5">{alert.title}</h3>
                  </div>
                </div>

                <div className="flex items-center gap-2 self-start">
                  <span
                    className={`text-[10px] uppercase font-bold tracking-wider px-2.5 py-1 rounded-full font-mono ${
                      isHigh
                        ? "bg-red-500/20 text-red-400 border border-red-500/40"
                        : isMed
                        ? "bg-amber-500/20 text-amber-400 border border-amber-500/40"
                        : "bg-surface-light text-cyan border border-cyan/30"
                    }`}
                  >
                    {alert.priorityLabel}
                  </span>
                </div>
              </div>

              {/* Specific Marine Metrics Tags */}
              {alert.metrics && (
                <div className="flex items-center gap-2 flex-wrap mb-3 pl-0 sm:pl-12">
                  {alert.metrics.signalType && (
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-surface-light border border-border text-amber-400 font-bold flex items-center gap-1">
                      <Anchor size={11} />
                      {alert.metrics.signalType}
                    </span>
                  )}
                  {alert.metrics.windKnots && (
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-surface-light border border-border text-text-muted flex items-center gap-1">
                      <Wind size={11} />
                      Winds: {alert.metrics.windKnots}
                    </span>
                  )}
                  {alert.metrics.windGustsKnots && (
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-surface-light border border-border text-red-400 font-bold flex items-center gap-1">
                      <Wind size={11} />
                      Gusts: {alert.metrics.windGustsKnots} kts
                    </span>
                  )}
                  {alert.metrics.seaCondition && (
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-surface-light border border-border text-text-muted flex items-center gap-1">
                      <Waves size={11} />
                      Sea: {alert.metrics.seaCondition}
                    </span>
                  )}
                </div>
              )}

              {/* Advisory Details */}
              <p className="text-xs md:text-sm text-text-primary/90 leading-relaxed mb-4 pl-0 sm:pl-12">
                {alert.description}
              </p>

              {/* Footer Controls & Actions */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-3 border-t border-border/60 pl-0 sm:pl-12">
                <div className="flex items-center gap-2 flex-wrap">
                  {alert.coordinates && (
                    <Link
                      href="/map"
                      className="text-xs font-mono text-cyan hover:underline flex items-center gap-1"
                    >
                      <MapPin size={12} />
                      <span>{alert.coordinates} (View on Map)</span>
                    </Link>
                  )}
                  {!alert.coordinates && (
                    <span className="text-[11px] font-mono text-text-muted">
                      Source: India Meteorological Department (IMD)
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2 self-end sm:self-auto">
                  <button
                    onClick={() => copyAdvisory(alert)}
                    className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-surface-light border border-border hover:bg-surface text-text-muted hover:text-text-primary flex items-center gap-1 transition-all"
                    title="Copy advisory for fishermen broadcast"
                  >
                    {isCopied ? (
                      <>
                        <Check size={12} className="text-go" />
                        <span className="text-go font-semibold">Copied</span>
                      </>
                    ) : (
                      <>
                        <Share2 size={12} />
                        <span>Broadcast</span>
                      </>
                    )}
                  </button>

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

        {!loading && filteredAlerts.length === 0 && (
          <div className="p-12 text-center bg-surface border border-border rounded-2xl text-text-muted space-y-2">
            <CheckCircle2 size={32} className="mx-auto text-go/80" />
            <p className="text-sm font-semibold text-text-primary">
              No active alerts matching the selected filter.
            </p>
            <p className="text-xs text-text-muted">
              All coastal zones and ports are currently within normal baseline thresholds.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}