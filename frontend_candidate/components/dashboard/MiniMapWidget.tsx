"use client";

import { useMemo } from "react";
import MarineMap, { type ResearchLayerType } from "@/components/map/MarineMap";
import { mockMapMarkers } from "@/lib/mockData";

export type { ResearchLayerType };

interface MiniMapWidgetProps {
  locationName?: string;
  center?: [number, number];
  zoom?: number;
  showHazards?: boolean;
  showFishingZones?: boolean;
  showSafeRoute?: boolean;
  showVessels?: boolean;
  className?: string;
  activeLayer?: ResearchLayerType;
}

export default function MiniMapWidget({
  locationName = "Veraval, Gujarat",
  center = [70.36, 20.90],
  zoom = 7.0,
  className = "h-[420px]",
  activeLayer,
}: MiniMapWidgetProps) {
  const layerLabel = useMemo(() => {
    switch (activeLayer) {
      case "salinity":
        return "Sea Surface Salinity (PSU)";
      case "chlorophyll":
        return "Chlorophyll-a Biomass (mg/m³)";
      case "anomalies":
        return "Thermal Anomaly SSTA (Δ°C)";
      case "trends":
        return "Decadal Warming Trend (°C/dec)";
      case "sst":
      default:
        return "Ocean Surface Thermal Field (°C)";
    }
  }, [activeLayer]);

  return (
    <div
      className={`w-full ${className} rounded-3xl overflow-hidden relative shadow-sm border border-slate-200`}
      style={{ minHeight: "360px" }}
    >
      <MarineMap
        markers={mockMapMarkers}
        center={center}
        zoom={zoom}
        locationName={locationName}
        height="h-full w-full"
        showControls={true}
        researchLayer={activeLayer}
      />

      {/* Top-Right Surface Telemetry HUD Pill */}
      {activeLayer && (
        <div className="absolute top-3.5 right-3.5 z-20 pointer-events-none flex items-center gap-2 px-3 py-1.5 rounded-xl bg-white/95 backdrop-blur-md border border-slate-200 shadow-sm text-xs font-bold text-slate-800">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span>{layerLabel}</span>
        </div>
      )}
    </div>
  );
}
