"use client";

import { useEffect, useState } from "react";
import MarineMap from "@/components/map/MarineMap";
import { userModeConfigs } from "@/lib/mockData";
import { useUserMode } from "@/lib/context";
import { AlertTriangle, Ship, Navigation, Anchor, RotateCcw, Loader2 } from "lucide-react";
import { publicConfig } from "@/lib/config";
import type { SpatialResult } from "@/lib/geojson/spatial";
import type { JourneyResponse } from "@/lib/schemas/journey";
import { postJourney } from "@/lib/api/journey";
import { fetchMarineHazards, type HazardGeoJsonFeature } from "@/lib/api/warnings";

export default function MarineMapPage() {
  const { mode } = useUserMode();
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const [spatialResult, setSpatialResult] = useState<SpatialResult | null>(null);
  const [loadingPfz, setLoadingPfz] = useState(false);
  const [liveHazards, setLiveHazards] = useState<HazardGeoJsonFeature[]>([]);
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

    // Fetch official live IMD hazards from FastAPI backend
    fetchMarineHazards()
      .then((res) => {
        if (res?.features) {
          setLiveHazards(res.features);
        }
      })
      .catch((err) => console.error("Error loading official IMD hazards:", err));
  }, []);

  const handleFetchLivePfz = async () => {
    setLoadingPfz(true);
    try {
      const result = await postJourney({
        origin: { latitude: 20.5, longitude: 72.9 },
        operational_limits: {
          maximum_significant_wave_height_m: 2.0,
          maximum_wind_speed_m_s: 12.0,
          maximum_surface_current_speed_m_s: 1.0,
        },
        include_geojson: true,
      });
      if (result?.data) {
        setSpatialResult(result.data);
        sessionStorage.setItem("orca_active_spatial_result", JSON.stringify(result.data));
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
            All Warnings ({liveHazards.length})
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
        markers={[]}
        height="h-[500px] lg:h-[600px]"
        showControls={true}
      />

      {/* Official IMD Warning Roster & Telemetry Summary */}
      <div className="space-y-2">
        <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
          <AlertTriangle size={15} className="text-red-500" />
          <span>Active Official IMD Maritime Warnings ({liveHazards.length})</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {liveHazards.map((hazard, hIdx) => {
            const coords = hazard.geometry.coordinates as [number, number];
            const isSevere = hazard.properties.severity === "DANGER" || hazard.properties.severity === "ALERT";

            return (
              <div
                key={`roster-${hIdx}`}
                className={`p-3.5 rounded-xl border ${
                  isSevere ? "border-red-500/40 bg-red-950/10" : "border-amber-500/30 bg-amber-950/10"
                } transition-all shadow-sm`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span
                    className={`text-[10px] uppercase font-mono font-bold px-1.5 py-0.5 rounded ${
                      isSevere ? "bg-red-500/20 text-red-400" : "bg-amber-500/20 text-amber-400"
                    }`}
                  >
                    {hazard.properties.hazard_type.replace("_", " ")}
                  </span>
                  {hazard.properties.signal_number ? (
                    <span className="text-[10px] font-mono font-bold text-amber-400">
                      Signal {hazard.properties.signal_number}
                    </span>
                  ) : (
                    <span className="text-[10px] font-mono text-text-muted">
                      {Array.isArray(coords) ? `${coords[1]?.toFixed(2)}°N, ${coords[0]?.toFixed(2)}°E` : ""}
                    </span>
                  )}
                </div>
                <h4 className="text-xs font-bold text-text-primary mt-1">{hazard.properties.title}</h4>
                <p className="text-[11px] text-text-muted mt-1 leading-relaxed line-clamp-3">
                  {hazard.properties.details}
                </p>
                <p className="mt-2 text-[10px] text-text-muted border-t border-border/40 pt-1 font-mono">
                  Issued: {new Date(hazard.properties.issued_at).toLocaleTimeString()}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}