"use client";

import { useEffect, useState } from "react";
import MarineMap from "@/components/map/MarineMap";
import { mockMapMarkers, userModeConfigs } from "@/lib/mockData";
import { useUserMode } from "@/lib/context";
import { AlertTriangle, Ship, Navigation, Anchor, RotateCcw, Loader2 } from "lucide-react";
import { publicConfig } from "@/lib/config";
import type { SpatialResult } from "@/lib/geojson/spatial";
import type { JourneyResponse } from "@/lib/schemas/journey";

export default function MarineMapPage() {
  const { mode } = useUserMode();
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const [spatialResult, setSpatialResult] = useState<SpatialResult | null>(null);
  const [loadingPfz, setLoadingPfz] = useState(false);
  const activeConfig = userModeConfigs[mode] || userModeConfigs.fisherman;

  useEffect(() => {
    try {
      const saved = sessionStorage.getItem("orca_active_spatial_result");
      if (saved) {
        setSpatialResult(JSON.parse(saved));
      }
    } catch {
      // Ignore storage errors
    }
  }, []);

  const handleFetchLivePfz = async () => {
    setLoadingPfz(true);
    try {
      const response = await fetch(`${publicConfig.apiBaseUrl}/v1/journey`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin: { latitude: 20.5, longitude: 72.9 },
          operational_limits: { wave_height_max: 2.0, wind_speed_max: 12.0, current_speed_max: 1.0 },
        }),
      });
      if (response.ok) {
        const data: JourneyResponse = await response.json();
        setSpatialResult(data);
        sessionStorage.setItem("orca_active_spatial_result", JSON.stringify(data));
      }
    } catch (err) {
      console.error("Failed to fetch live PFZ journey:", err);
    } finally {
      setLoadingPfz(false);
    }
  };

  const handleClearSpatial = () => {
    setSpatialResult(null);
    sessionStorage.removeItem("orca_active_spatial_result");
  };

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
              MapLibre GL Nautical
            </span>
          </div>
          <p className="text-text-muted text-xs md:text-sm mt-1">
            Real-time nautical vector chart with bathymetric layers, INCOIS PFZ advisory targets, and live vessel corridors.
          </p>
        </div>

        {/* Action Buttons & Filter Pills */}
        <div className="flex flex-wrap items-center gap-2">
          {spatialResult ? (
            <button
              onClick={handleClearSpatial}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-surface border border-border hover:bg-surface-light text-text-muted hover:text-text-primary flex items-center gap-1.5 transition-all"
            >
              <RotateCcw size={12} />
              <span>Clear PFZ Route</span>
            </button>
          ) : (
            <button
              onClick={handleFetchLivePfz}
              disabled={loadingPfz}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan text-bg hover:bg-cyan/90 font-bold flex items-center gap-1.5 transition-all shadow-sm disabled:opacity-50"
            >
              {loadingPfz ? <Loader2 size={12} className="animate-spin" /> : <Anchor size={12} />}
              <span>Fetch Live INCOIS PFZ</span>
            </button>
          )}

          <div className="h-4 w-px bg-border hidden sm:block" />

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

      {/* Main MapLibre GL Vector Map View */}
      <MarineMap
        result={spatialResult}
        markers={filteredMarkers}
        height="h-[500px] lg:h-[600px]"
        showControls={true}
      />

      {/* Quick Marker Roster & Telemetry Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {mockMapMarkers.map((marker) => {
          const lng = 68.2 + (marker.x / 100) * 8.5;
          const lat = 23.5 - (marker.y / 100) * 12.0;

          return (
            <div
              key={marker.id}
              className="p-3.5 rounded-xl border border-border bg-surface hover:border-cyan/40 transition-all shadow-sm"
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] uppercase tracking-wider font-mono font-bold text-cyan">
                  {marker.type}
                </span>
                <span className="text-[10px] text-text-muted font-mono">
                  {lat.toFixed(2)}°N, {lng.toFixed(2)}°E
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
          );
        })}
      </div>
    </div>
  );
}