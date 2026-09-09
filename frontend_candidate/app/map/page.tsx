"use client";

import MarineMap from "@/components/map/MarineMap";
import { mockMapMarkers, userModeConfigs } from "@/lib/mockData";
import { useUserMode } from "@/lib/context";
import { AlertTriangle, Ship, Navigation } from "lucide-react";
import { useState } from "react";

export default function MarineMapPage() {
  const { mode } = useUserMode();
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const activeConfig = userModeConfigs[mode] || userModeConfigs.fisherman;

  const filteredMarkers = mockMapMarkers.filter((m) => {
    if (activeFilter === "all") return true;
    if (activeFilter === "hazard") return m.type === "hazard";
    if (activeFilter === "vessel") return m.type === "vessel";
    if (activeFilter === "route") return m.type === "route";
    if (activeFilter === "sensor") return m.type === "sensor" || m.type === "port";
    return true;
  });

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-4 md:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-display font-black text-2xl md:text-3xl text-text-primary">
              Marine Geospatial Explorer
            </h1>
            <span className="text-xs px-2 py-0.5 rounded-full bg-cyan/10 text-cyan border border-cyan/30 font-semibold font-mono">
              Live Chart 2.0
            </span>
          </div>
          <p className="text-text-muted text-xs md:text-sm mt-1">
            Real-time nautical chart with bathymetric layers, Doppler radar, and live AIS vessel telemetry.
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          <button
            onClick={() => setActiveFilter("all")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeFilter === "all"
                ? "bg-cyan text-bg font-bold shadow-sm"
                : "bg-surface-light text-text-muted hover:text-text-primary"
            }`}
          >
            All Markers ({mockMapMarkers.length})
          </button>
          <button
            onClick={() => setActiveFilter("hazard")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1 ${
              activeFilter === "hazard"
                ? "bg-avoid text-white font-bold"
                : "bg-surface-light text-avoid hover:bg-avoid/20"
            }`}
          >
            <AlertTriangle size={12} />
            <span>Hazards</span>
          </button>
          <button
            onClick={() => setActiveFilter("vessel")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1 ${
              activeFilter === "vessel"
                ? "bg-cyan text-bg font-bold"
                : "bg-surface-light text-cyan hover:bg-cyan/20"
            }`}
          >
            <Ship size={12} />
            <span>AIS Traffic</span>
          </button>
          <button
            onClick={() => setActiveFilter("route")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1 ${
              activeFilter === "route"
                ? "bg-go text-bg font-bold"
                : "bg-surface-light text-go hover:bg-go/20"
            }`}
          >
            <Navigation size={12} />
            <span>Safe Routes</span>
          </button>
        </div>
      </div>

      {/* Main Map View */}
      <MarineMap markers={filteredMarkers} height="h-[500px] lg:h-[580px]" showControls={true} />

      {/* Quick Marker Roster & Telemetry Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {mockMapMarkers.map((marker) => (
          <div
            key={marker.id}
            className="p-3.5 rounded-xl border border-border bg-surface hover:border-cyan/40 transition-all"
          >
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] uppercase tracking-wider font-mono font-bold text-cyan">
                {marker.type}
              </span>
              <span className="text-[10px] text-text-muted font-mono">
                {marker.x}%, {marker.y}%
              </span>
            </div>
            <h4 className="text-sm font-bold text-text-primary">{marker.label}</h4>
            {marker.subtitle && (
              <p className="text-xs text-text-muted mt-0.5">{marker.subtitle}</p>
            )}
            {marker.details?.warning && (
              <p className="text-[11px] text-avoid font-medium mt-1">⚠️ {marker.details.warning}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}