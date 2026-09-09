"use client";

import { MapMarker } from "@/lib/types";
import { useUserMode } from "@/lib/context";
import {
  AlertTriangle,
  Ship,
  Navigation,
  MapPin,
  Radio,
  ZoomIn,
  ZoomOut,
  Anchor,
  Compass,
  X,
  Wind,
} from "lucide-react";
import { useState } from "react";

const markerConfig = {
  hazard: { icon: AlertTriangle, color: "text-avoid", bg: "bg-avoid/20", border: "border-avoid/50" },
  vessel: { icon: Ship, color: "text-cyan", bg: "bg-cyan/20", border: "border-cyan/50" },
  route: { icon: Navigation, color: "text-go", bg: "bg-go/20", border: "border-go/50" },
  user: { icon: MapPin, color: "text-wait", bg: "bg-wait/20", border: "border-wait/50" },
  sensor: { icon: Radio, color: "text-cyan", bg: "bg-cyan/20", border: "border-cyan/50" },
  port: { icon: Anchor, color: "text-text-primary", bg: "bg-surface-light", border: "border-border" },
};

export default function MarineMap({
  markers,
  height = "h-72 md:h-96",
  showControls = true,
}: {
  markers: MapMarker[];
  height?: string;
  showControls?: boolean;
}) {
  const { mode } = useUserMode();
  const [selectedMarker, setSelectedMarker] = useState<MapMarker | null>(null);
  const [activeLayers, setActiveLayers] = useState({
    radar: true,
    ais: true,
    hazards: true,
    routes: true,
    grid: true,
  });
  const [zoomLevel, setZoomLevel] = useState(1);

  const toggleLayer = (layerKey: keyof typeof activeLayers) => {
    setActiveLayers((prev) => ({ ...prev, [layerKey]: !prev[layerKey] }));
  };

  const visibleMarkers = markers.filter((m) => {
    if (m.type === "hazard" && !activeLayers.hazards) return false;
    if (m.type === "vessel" && !activeLayers.ais) return false;
    if (m.type === "route" && !activeLayers.routes) return false;
    if (m.visibleForModes && !m.visibleForModes.includes(mode)) return false;
    return true;
  });

  return (
    <div
      className={`relative w-full ${height} rounded-2xl overflow-hidden border border-border group select-none shadow-xl`}
      style={{
        background:
          "radial-gradient(ellipse at 35% 25%, #16304F 0%, #0c1a2e 50%, #060e1a 100%)",
      }}
    >
      {/* Dynamic Nautical Chart Contours */}
      <svg className="absolute inset-0 w-full h-full opacity-20 pointer-events-none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 0,120 Q 200,80 450,160 T 900,100" fill="none" stroke="#22D3EE" strokeWidth="1" strokeDasharray="4 4" />
        <path d="M 0,220 Q 250,190 500,280 T 1000,190" fill="none" stroke="#22D3EE" strokeWidth="1" />
        <path d="M 0,320 Q 300,310 600,360 T 1200,280" fill="none" stroke="#22D3EE" strokeWidth="1" strokeDasharray="6 6" />
        <circle cx="45%" cy="50%" r="28%" fill="none" stroke="#22D3EE" strokeWidth="0.5" strokeDasharray="2 4" />
      </svg>

      {/* Grid lines */}
      {activeLayers.grid && (
        <div className="absolute inset-0 opacity-15 pointer-events-none">
          {[...Array(6)].map((_, i) => (
            <div
              key={`h-${i}`}
              className="absolute left-0 right-0 border-t border-cyan/60"
              style={{ top: `${(i + 1) * 14}%` }}
            />
          ))}
          {[...Array(8)].map((_, i) => (
            <div
              key={`v-${i}`}
              className="absolute top-0 bottom-0 border-l border-cyan/60"
              style={{ left: `${(i + 1) * 12}%` }}
            />
          ))}
        </div>
      )}

      {/* Weather Radar Overlay Simulation */}
      {activeLayers.radar && (
        <div
          className="absolute right-[20%] top-[15%] w-56 h-56 rounded-full opacity-30 pointer-events-none animate-pulse"
          style={{
            background: "radial-gradient(circle, rgba(239,68,68,0.6) 0%, rgba(245,158,11,0.4) 40%, rgba(34,211,238,0.15) 75%, transparent 100%)",
          }}
        />
      )}

      {/* Simulated safe passage route line */}
      {activeLayers.routes && (
        <svg className="absolute inset-0 w-full h-full pointer-events-none">
          <path
            d="M 320,140 Q 400,220 440,260 T 560,340"
            fill="none"
            stroke="#10B981"
            strokeWidth="2.5"
            strokeDasharray="6 4"
            className="animate-pulse"
          />
        </svg>
      )}

      {/* Map Markers */}
      {visibleMarkers.map((marker) => {
        const config = markerConfig[marker.type] || markerConfig.user;
        const Icon = config.icon;
        const isSelected = selectedMarker?.id === marker.id;

        return (
          <div
            key={marker.id}
            onClick={() => setSelectedMarker(marker)}
            className={`absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center gap-1 cursor-pointer z-10 transition-transform ${
              isSelected ? "scale-125 z-20" : "hover:scale-110"
            }`}
            style={{ left: `${marker.x}%`, top: `${marker.y}%` }}
          >
            <div
              className={`w-8 h-8 rounded-full ${config.bg} border ${config.border} flex items-center justify-center shadow-lg backdrop-blur-sm relative`}
            >
              <Icon size={16} className={config.color} />
              {marker.type === "hazard" && (
                <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-avoid rounded-full animate-ping" />
              )}
              {marker.type === "user" && (
                <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-wait rounded-full animate-ping" />
              )}
            </div>

            <span
              className={`text-[10px] font-medium px-2 py-0.5 rounded shadow-md whitespace-nowrap transition-all ${
                isSelected
                  ? "bg-surface border border-cyan text-cyan opacity-100"
                  : "bg-surface/90 text-text-primary opacity-0 group-hover:opacity-100"
              }`}
            >
              {marker.label}
            </span>
          </div>
        );
      })}

      {/* Marker Detail Popup */}
      {selectedMarker && (
        <div className="absolute bottom-12 left-4 right-4 md:right-auto md:w-80 bg-surface/95 border border-border p-3.5 rounded-xl shadow-2xl z-30 backdrop-blur-md">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wider font-bold text-cyan">
                {selectedMarker.type}
              </span>
              <span className="text-[10px] text-text-muted font-mono">
                {selectedMarker.x}%, {selectedMarker.y}%
              </span>
            </div>
            <button
              onClick={() => setSelectedMarker(null)}
              className="text-text-muted hover:text-text-primary p-0.5"
            >
              <X size={14} />
            </button>
          </div>

          <h4 className="text-sm font-bold text-text-primary mt-1">{selectedMarker.label}</h4>
          {selectedMarker.subtitle && (
            <p className="text-xs text-text-muted">{selectedMarker.subtitle}</p>
          )}

          {selectedMarker.details && (
            <div className="mt-2.5 pt-2 border-t border-border/60 grid grid-cols-2 gap-2 text-[11px]">
              {selectedMarker.details.speed && (
                <div>
                  <span className="text-text-muted">Speed:</span>{" "}
                  <span className="text-text-primary font-mono">{selectedMarker.details.speed}</span>
                </div>
              )}
              {selectedMarker.details.waveHeight && (
                <div>
                  <span className="text-text-muted">Wave:</span>{" "}
                  <span className="text-cyan font-mono">{selectedMarker.details.waveHeight}</span>
                </div>
              )}
              {selectedMarker.details.warning && (
                <div className="col-span-2 text-avoid font-medium">
                  ⚠️ {selectedMarker.details.warning}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Layer Toggles & Map Controls */}
      {showControls && (
        <div className="absolute top-3 right-3 flex flex-col gap-1.5 z-20">
          <div className="bg-surface/90 backdrop-blur border border-border p-1 rounded-xl shadow-lg flex flex-col gap-1">
            <button
              onClick={() => setZoomLevel((z) => Math.min(z + 0.2, 2))}
              className="p-1.5 hover:bg-surface-light rounded-lg text-text-muted hover:text-text-primary"
              title="Zoom In"
            >
              <ZoomIn size={15} />
            </button>
            <button
              onClick={() => setZoomLevel((z) => Math.max(z - 0.2, 0.8))}
              className="p-1.5 hover:bg-surface-light rounded-lg text-text-muted hover:text-text-primary"
              title="Zoom Out"
            >
              <ZoomOut size={15} />
            </button>
          </div>

          <div className="bg-surface/90 backdrop-blur border border-border p-1.5 rounded-xl shadow-lg flex flex-col gap-1 text-[11px]">
            <button
              onClick={() => toggleLayer("radar")}
              className={`px-2 py-1 rounded text-left flex items-center gap-1.5 ${
                activeLayers.radar ? "bg-cyan/10 text-cyan font-bold" : "text-text-muted"
              }`}
            >
              <Wind size={12} />
              <span>Radar</span>
            </button>
            <button
              onClick={() => toggleLayer("ais")}
              className={`px-2 py-1 rounded text-left flex items-center gap-1.5 ${
                activeLayers.ais ? "bg-cyan/10 text-cyan font-bold" : "text-text-muted"
              }`}
            >
              <Ship size={12} />
              <span>AIS</span>
            </button>
            <button
              onClick={() => toggleLayer("hazards")}
              className={`px-2 py-1 rounded text-left flex items-center gap-1.5 ${
                activeLayers.hazards ? "bg-avoid/10 text-avoid font-bold" : "text-text-muted"
              }`}
            >
              <AlertTriangle size={12} />
              <span>Hazards</span>
            </button>
          </div>
        </div>
      )}

      {/* Compass rose */}
      <div className="absolute top-3 left-3 bg-surface/80 border border-border/80 px-2.5 py-1.5 rounded-xl flex items-center gap-2 text-xs font-mono text-cyan backdrop-blur">
        <Compass size={14} className="animate-spin" style={{ animationDuration: "20s" }} />
        <span>Arabian Sea / Sector 4</span>
      </div>

      {/* Footer disclaimer badge */}
      <div className="absolute bottom-3 right-3 text-[10px] text-text-muted bg-surface/80 border border-border/60 px-2.5 py-1 rounded-lg backdrop-blur">
        🛰️ Geospatial GIS Vector Stream • Live AIS & NOAA Telemetry
      </div>
    </div>
  );
}