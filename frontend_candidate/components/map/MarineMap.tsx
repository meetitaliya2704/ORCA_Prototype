"use client";

import { LngLatBounds, type Map as MapLibreMap } from "maplibre-gl";
import {
  AlertTriangle,
  Anchor,
  Compass,
  Layers3,
  MapPin,
  Navigation,
  Radio,
  Route,
  Ship,
  Wind,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Card } from "@/components/ui/card";
import {
  Map as MapCanvas,
  MapControls,
  MapMarker as LibreMarker,
  MarkerContent,
  MarkerPopup,
  useMap,
} from "@/components/ui/map";
import { publicConfig } from "@/lib/config";
import { assertGeoJsonCoordinateOrder } from "@/lib/geojson/journey";
import { isJourneyResponse, spatialFeatures, type SpatialFeature, type SpatialResult } from "@/lib/geojson/spatial";
import { fetchMarineHazards, type HazardGeoJsonFeature } from "@/lib/api/warnings";
import type { MapMarker } from "@/lib/types";
import {
  RESEARCH_STATIONS,
  RESEARCH_ZONES,
  type ResearchLayerType,
} from "@/lib/researchMapData";

export type { ResearchLayerType } from "@/lib/researchMapData";


const markerConfig = {
  hazard: { icon: AlertTriangle, color: "text-avoid", bg: "bg-avoid/20", border: "border-avoid/50" },
  vessel: { icon: Ship, color: "text-cyan", bg: "bg-cyan/20", border: "border-cyan/50" },
  route: { icon: Navigation, color: "text-go", bg: "bg-go/20", border: "border-go/50" },
  user: { icon: MapPin, color: "text-wait", bg: "bg-wait/20", border: "border-wait/50" },
  sensor: { icon: Radio, color: "text-cyan", bg: "bg-cyan/20", border: "border-cyan/50" },
  port: { icon: Anchor, color: "text-text-primary", bg: "bg-surface-light", border: "border-border" },
};

function markerLngLat(m: MapMarker): [number, number] {
  // If specific coordinates are provided, use them; otherwise map normalized x/y to Arabian Sea / Indian West Coast
  const lng = m.longitude ?? 68.2 + (m.x / 100) * 8.5;
  const lat = m.latitude ?? 23.5 - (m.y / 100) * 12.0;
  return [lng, lat];
}

export function fitJourneyGeoJson(
  instance: MapLibreMap,
  result: SpatialResult | null,
  reducedMotion: boolean,
) {
  if (!result?.geojson) return false;
  if (isJourneyResponse(result) && !assertGeoJsonCoordinateOrder(result)) return false;
  const points = spatialFeatures(result).flatMap((feature) =>
    feature.geometry.type === "Point" ? [feature.geometry.coordinates] : [],
  );
  if (points.length > 0) {
    const bounds = points.reduce(
      (box, coordinate) => box.extend(coordinate as [number, number]),
      new LngLatBounds(points[0] as [number, number], points[0] as [number, number]),
    );
    instance.fitBounds(bounds, {
      padding: 72,
      maxZoom: 10,
      duration: reducedMotion ? 0 : 500,
    });
    return true;
  }
  return false;
}

function JourneyMapContent({
  result,
  markers = [],
  activeLayers,
  researchLayer,
  onReady,
  onError,
}: {
  result: SpatialResult | null;
  markers?: MapMarker[];
  activeLayers: { radar: boolean; ais: boolean; hazards: boolean; routes: boolean };
  researchLayer?: ResearchLayerType;
  onReady: () => void;
  onError: () => void;
}) {
  const { map } = useMap();
  const [linePoints, setLinePoints] = useState<string | null>(null);
  const [hazardFeatures, setHazardFeatures] = useState<HazardGeoJsonFeature[]>([]);
  const [conePolygons, setConePolygons] = useState<{ id: string; points: string; title: string; details: string; center: [number, number] }[]>([]);
  const [trackPolylines, setTrackPolylines] = useState<{ id: string; points: string; title: string }[]>([]);
  const [projectedResearchPolygons, setProjectedResearchPolygons] = useState<{
    id: string;
    points: string;
    color: string;
    opacity: number;
    stroke: string;
    label: string;
  }[]>([]);

  useEffect(() => {
    let active = true;
    fetchMarineHazards()
      .then((res) => {
        if (active && res?.features) {
          setHazardFeatures(res.features);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const pointFeatures = useMemo(
    () => spatialFeatures(result).filter((feature) => feature.geometry.type === "Point"),
    [result],
  );

  const referenceLine = useMemo(
    () => spatialFeatures(result).find((feature) => feature.geometry.type === "LineString"),
    [result],
  );

  const journeyPfz = result && isJourneyResponse(result) ? result.pfz?.nearest_pfz : null;

  const isVetoed = useMemo(() => {
    if (!result || !isJourneyResponse(result)) return false;
    const hasVetoStatus = result.journey_status === "PFZ_AVAILABLE_LIMIT_EXCEEDED";
    const hasWarningCode = (result.reason_codes ?? []).some((code) =>
      [
        "OFFICIAL_IMD_CYCLONE_WARNING",
        "OFFICIAL_IMD_PORT_WARNING",
        "OFFICIAL_IMD_FISHERMEN_WARNING",
        "ROUTE_HAZARD_INTERSECTION",
      ].includes(code),
    );
    return hasVetoStatus && hasWarningCode;
  }, [result]);

  const vetoReason = useMemo(() => {
    if (!result || !isJourneyResponse(result) || !isVetoed) return null;
    return (result.reasons ?? []).find((r) =>
      [
        "OFFICIAL_IMD_CYCLONE_WARNING",
        "OFFICIAL_IMD_PORT_WARNING",
        "OFFICIAL_IMD_FISHERMEN_WARNING",
        "ROUTE_HAZARD_INTERSECTION",
      ].includes(r.code),
    );
  }, [result, isVetoed]);

  const updateOverlays = useCallback(() => {
    if (!map) return;

    // 1. Reference route line
    if (referenceLine?.geometry.type === "LineString") {
      setLinePoints(
        referenceLine.geometry.coordinates
          .map((coordinate) => {
            const point = map.project(coordinate as [number, number]);
            return `${point.x},${point.y}`;
          })
          .join(" "),
      );
    } else {
      setLinePoints(null);
    }

    // 2. Cyclone cones & tracks
    const cones: { id: string; points: string; title: string; details: string; center: [number, number] }[] = [];
    const tracks: { id: string; points: string; title: string }[] = [];

    hazardFeatures.forEach((hf, idx) => {
      if (hf.geometry.type === "Polygon" && Array.isArray(hf.geometry.coordinates)) {
        const ring = (hf.geometry.coordinates as [number, number][][])[0];
        if (ring && ring.length >= 3) {
          const pts = ring
            .map((coord) => {
              const p = map.project(coord);
              return `${p.x},${p.y}`;
            })
            .join(" ");

          let sumLon = 0, sumLat = 0;
          ring.forEach((c) => { sumLon += c[0]; sumLat += c[1]; });
          const center: [number, number] = [sumLon / ring.length, sumLat / ring.length];

          cones.push({
            id: `cone-${idx}`,
            points: pts,
            title: hf.properties.title,
            details: hf.properties.details,
            center,
          });
        }
      } else if (hf.geometry.type === "LineString" && Array.isArray(hf.geometry.coordinates)) {
        const coords = hf.geometry.coordinates as [number, number][];
        if (coords.length >= 2) {
          const pts = coords
            .map((c) => {
              const p = map.project(c);
              return `${p.x},${p.y}`;
            })
            .join(" ");
          tracks.push({
            id: `track-${idx}`,
            points: pts,
            title: hf.properties.title,
          });
        }
      }
    });

    setConePolygons(cones);
    setTrackPolylines(tracks);

    // 3. Research Layer Oceanic Zones (projected to current screen pixels)
    if (researchLayer) {
      const rPolys = RESEARCH_ZONES.map((rz) => {
        const pts = rz.coordinates
          .map((coord) => {
            const p = map.project(coord);
            return `${p.x},${p.y}`;
          })
          .join(" ");

        return {
          id: rz.id,
          points: pts,
          color: rz.color[researchLayer],
          opacity: rz.fillOpacity[researchLayer],
          stroke: rz.stroke[researchLayer],
          label: rz.label[researchLayer],
        };
      });
      setProjectedResearchPolygons(rPolys);
    } else {
      setProjectedResearchPolygons([]);
    }
  }, [map, referenceLine, hazardFeatures, researchLayer]);

  useEffect(() => {
    if (!map) return;
    const handleError = () => {
      if (!map.isStyleLoaded()) onError();
    };
    const startupTimer = window.setTimeout(() => {
      if (!map.isStyleLoaded()) onError();
    }, 15_000);

    map.on("error", handleError);
    map.on("move", updateOverlays);
    map.on("resize", updateOverlays);

    return () => {
      window.clearTimeout(startupTimer);
      map.off("error", handleError);
      map.off("move", updateOverlays);
      map.off("resize", updateOverlays);
    };
  }, [map, onError, updateOverlays]);

  useEffect(() => {
    if (!map) return;
    map.resize();
    const hasFitted = fitJourneyGeoJson(
      map,
      result,
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    );
    if (!hasFitted && markers.length > 0) {
      const bounds = markers.reduce(
        (box, m) => box.extend(markerLngLat(m)),
        new LngLatBounds(markerLngLat(markers[0]), markerLngLat(markers[0])),
      );
      map.fitBounds(bounds, { padding: 60, maxZoom: 8, duration: 400 });
    }
    const frame = window.requestAnimationFrame(() => {
      updateOverlays();
      onReady();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [map, onReady, result, markers, updateOverlays]);

  const visibleMarkers = markers.filter((m) => {
    if (m.type === "hazard" && !activeLayers.hazards) return false;
    if (m.type === "vessel" && !activeLayers.ais) return false;
    if (m.type === "route" && !activeLayers.routes) return false;
    return true;
  });

  return (
    <>
      {/* Official IMD Route Veto Alert Banner */}
      {isVetoed && vetoReason && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-30 max-w-md w-[92%] rounded-xl border border-red-500/60 bg-surface/95 p-3.5 shadow-2xl backdrop-blur-md flex items-start gap-3 animate-in fade-in slide-in-from-top duration-300">
          <div className="p-2 rounded-lg bg-red-500/20 text-red-400 shrink-0 mt-0.5">
            <AlertTriangle size={18} className="animate-pulse" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase font-mono font-bold bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded border border-red-500/30">
                Official IMD Veto
              </span>
              <span className="text-xs font-bold text-red-400">Route Unsafe</span>
            </div>
            <p className="mt-1 text-xs text-text-primary leading-relaxed font-medium">
              {vetoReason.message}
            </p>
          </div>
        </div>
      )}

      {/* Journey Feature Legend if PFZ / Journey Result is Active */}
      {pointFeatures.length > 0 && (
        <div className="pointer-events-none absolute left-3 top-3 z-10 rounded-xl border border-border bg-surface/95 p-3 shadow-lg backdrop-blur-md">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-text-muted">
            Journey Features
          </p>
          <div className="grid gap-1.5 text-xs font-semibold text-text-primary">
            <span className="flex items-center gap-2">
              <span className="size-2.5 rounded-full bg-cyan ring-2 ring-white" />
              Origin Vessel
            </span>
            <span className="flex items-center gap-2">
              <span className="size-2.5 rounded-full bg-go ring-2 ring-white" />
              PFZ Destination
            </span>
            <span className="flex items-center gap-2">
              <span className={`w-5 border-t-2 border-dashed ${isVetoed ? "border-red-500" : "border-avoid"}`} />
              {isVetoed ? "Vetoed Route" : "Reference Bearing"}
            </span>
          </div>
        </div>
      )}

      {/* SVG Map Overlays: Cones, Tracks, Reference Route, and Research Oceanic Zones */}
      <svg aria-hidden="true" className="pointer-events-none absolute inset-0 z-[3] size-full overflow-hidden">
        {/* Research Oceanic Contour Polygons (projected dynamically on map move) */}
        {projectedResearchPolygons.map((rp) => (
          <polygon
            key={rp.id}
            points={rp.points}
            fill={rp.color}
            fillOpacity={rp.opacity}
            stroke={rp.stroke}
            strokeWidth="1.8"
            strokeDasharray="5 3"
          />
        ))}

        {/* Cyclone Cones */}
        {conePolygons.map((cp) => (
          <polygon
            key={cp.id}
            points={cp.points}
            fill="rgba(239, 68, 68, 0.22)"
            stroke="#ef4444"
            strokeWidth="2.5"
            strokeDasharray="6 4"
          />
        ))}

        {/* Cyclone Forecast Tracks */}
        {trackPolylines.map((tp) => (
          <polyline
            key={tp.id}
            points={tp.points}
            fill="none"
            stroke="#f59e0b"
            strokeWidth="2.5"
            strokeDasharray="5 4"
            strokeLinecap="round"
          />
        ))}

        {/* Route Line */}
        {linePoints && (
          <polyline
            points={linePoints}
            fill="none"
            stroke={isVetoed ? "#ef4444" : "#0ea5e9"}
            strokeWidth="3.5"
            strokeDasharray={isVetoed ? "6 4" : "8 6"}
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>

      {/* Cyclone Cone Center Labels */}
      {conePolygons.map((cp) => (
        <LibreMarker
          key={`cone-marker-${cp.id}`}
          longitude={cp.center[0]}
          latitude={cp.center[1]}
          anchor="center"
        >
          <MarkerContent>
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-red-500/20 border border-red-500/60 text-red-400 font-bold text-[10px] shadow-lg backdrop-blur-md animate-pulse cursor-pointer">
              <AlertTriangle size={12} className="text-red-400" />
              <span>{cp.title}</span>
            </div>
          </MarkerContent>
          <MarkerPopup closeButton offset={15}>
            <div className="w-64 rounded-xl border border-red-500/40 bg-surface p-3 text-text-primary shadow-2xl backdrop-blur-md">
              <span className="text-[10px] uppercase font-mono font-bold bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded">
                Official Cyclone Cone
              </span>
              <h4 className="mt-1 text-sm font-bold text-red-400">{cp.title}</h4>
              <p className="mt-1 text-xs text-text-muted">{cp.details}</p>
            </div>
          </MarkerPopup>
        </LibreMarker>
      ))}

      {/* Research Oceanic Observation Stations (anchored to geographic coordinates) */}
      {researchLayer &&
        RESEARCH_STATIONS.map((st) => {
          const val =
            researchLayer === "salinity"
              ? st.salinity
              : researchLayer === "chlorophyll"
              ? st.chlorophyll
              : researchLayer === "anomalies"
              ? st.anomalies
              : researchLayer === "trends"
              ? st.trends
              : st.sst;

          const color =
            researchLayer === "salinity"
              ? st.salinityColor
              : researchLayer === "chlorophyll"
              ? st.chlorophyllColor
              : researchLayer === "anomalies"
              ? st.anomalyColor
              : researchLayer === "trends"
              ? st.trendColor
              : st.sstColor;

          return (
            <LibreMarker
              key={`research-st-${st.id}`}
              longitude={st.longitude}
              latitude={st.latitude}
              anchor="center"
            >
              <MarkerContent>
                <div className="flex flex-col items-center gap-0.5 group cursor-pointer">
                  <div className="flex items-center gap-1 px-2 py-0.5 rounded-lg bg-slate-900/90 backdrop-blur-md border border-white/40 text-white font-mono text-[10px] font-bold shadow-lg transition-transform group-hover:scale-115">
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ backgroundColor: color }}
                    />
                    <span>{val}</span>
                  </div>
                  <span className="text-[8.5px] font-bold text-slate-800 bg-white/95 px-1 py-0.2 rounded shadow-2xs border border-slate-300 pointer-events-none whitespace-nowrap opacity-90 group-hover:opacity-100">
                    {st.name.split(" ")[0]}
                  </span>
                </div>
              </MarkerContent>
              <MarkerPopup closeButton offset={15}>
                <div className="w-56 p-2.5 rounded-xl bg-surface border border-border shadow-xl text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-cyan font-mono">
                      Ocean Sensor
                    </span>
                    <span className="text-[9px] text-text-muted font-mono">
                      Depth: {st.depth}
                    </span>
                  </div>
                  <h4 className="font-bold text-text-primary text-xs leading-tight">
                    {st.name}
                  </h4>
                  <p className="text-[10px] text-text-muted font-mono">
                    {st.latitude.toFixed(2)}°N, {st.longitude.toFixed(2)}°E
                  </p>
                  <div className="pt-1.5 border-t border-border grid grid-cols-2 gap-1 text-[10px]">
                    <div><span className="text-text-muted">SST:</span> <span className="font-bold font-mono text-amber-500">{st.sst}</span></div>
                    <div><span className="text-text-muted">Salinity:</span> <span className="font-bold font-mono text-blue-500">{st.salinity}</span></div>
                    <div><span className="text-text-muted">Chl-a:</span> <span className="font-bold font-mono text-emerald-500">{st.chlorophyll}</span></div>
                    <div><span className="text-text-muted">Anomaly:</span> <span className="font-bold font-mono text-rose-500">{st.anomalies}</span></div>
                  </div>
                </div>
              </MarkerPopup>
            </LibreMarker>
          );
        })}

      {/* Journey Result Markers (Origin & PFZ) */}
      {pointFeatures.map((feature) => {
        if (feature.geometry.type !== "Point") return null;
        const [longitude, latitude] = feature.geometry.coordinates;
        const isOrigin = feature.properties.feature_type === "origin";

        return (
          <LibreMarker
            key={`spatial-${feature.properties.feature_type ?? `${longitude}:${latitude}`}`}
            longitude={longitude}
            latitude={latitude}
            anchor="center"
          >
            <MarkerContent>
              <button
                type="button"
                className="group flex size-10 items-center justify-center rounded-full focus:outline-none"
              >
                <span
                  className={`flex size-8 items-center justify-center rounded-full border-2 border-white shadow-xl transition-transform group-hover:scale-110 ${
                    isOrigin ? "bg-cyan text-bg" : "bg-go text-bg"
                  }`}
                >
                  {isOrigin ? <Navigation size={16} /> : <Anchor size={16} />}
                </span>
              </button>
            </MarkerContent>
            <MarkerPopup closeButton offset={20}>
              <div className="w-64 rounded-xl border border-border bg-surface p-3.5 text-text-primary shadow-2xl backdrop-blur-md">
                <p className="flex items-center gap-2 font-bold text-sm">
                  {isOrigin ? <Navigation size={16} className="text-cyan" /> : <Anchor size={16} className="text-go" />}
                  {isOrigin ? "Origin Position" : "Nearest PFZ Destination"}
                </p>
                <p className="mt-1 text-xs text-text-muted font-mono">
                  {latitude.toFixed(4)}°N, {longitude.toFixed(4)}°E
                </p>
                {!isOrigin && journeyPfz && (
                  <div className="mt-2.5 pt-2 border-t border-border/60 text-xs space-y-1">
                    <p className="font-semibold text-cyan">
                      {journeyPfz.landing_centre} · {journeyPfz.region_name}
                    </p>
                    <p className="text-text-muted text-[11px]">
                      Direction: {journeyPfz.direction} · Bearing: {journeyPfz.bearing_deg}° · {journeyPfz.distance_km.toFixed(1)} km
                    </p>
                  </div>
                )}
              </div>
            </MarkerPopup>
          </LibreMarker>
        );
      })}

      {/* Live Official IMD Warning Overlays (Port Signals & Weather Cones) */}
      {hazardFeatures.map((hf, idx) => {
        if (hf.geometry.type !== "Point" || !Array.isArray(hf.geometry.coordinates)) return null;
        const [lon, lat] = hf.geometry.coordinates as [number, number];
        const isSevere = hf.properties.severity === "DANGER" || hf.properties.severity === "ALERT";

        return (
          <LibreMarker
            key={`imd-warning-${idx}-${lon}-${lat}`}
            longitude={lon}
            latitude={lat}
            anchor="bottom"
          >
            <MarkerContent>
              <button
                type="button"
                aria-label={`Official IMD Warning: ${hf.properties.title}`}
                className="group flex flex-col items-center gap-1 cursor-pointer focus:outline-none"
              >
                <div
                  className={`size-8 rounded-full ${
                    isSevere ? "bg-red-500/20 border-red-500" : "bg-amber-500/20 border-amber-500"
                  } border-2 flex items-center justify-center shadow-lg backdrop-blur-sm relative group-hover:scale-125 transition-transform animate-pulse`}
                >
                  <AlertTriangle size={15} className={isSevere ? "text-red-500" : "text-amber-500"} />
                  {isSevere && (
                    <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-red-500 rounded-full animate-ping" />
                  )}
                </div>
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-surface/95 border border-border text-red-400 opacity-0 group-hover:opacity-100 transition-opacity shadow-md whitespace-nowrap">
                  {hf.properties.title}
                </span>
              </button>
            </MarkerContent>
            <MarkerPopup closeButton offset={20}>
              <div className="w-72 rounded-xl border border-red-500/40 bg-surface p-3.5 text-text-primary shadow-2xl backdrop-blur-md">
                <div className="flex items-center justify-between mb-1.5 border-b border-border/60 pb-1.5">
                  <span className="text-[10px] uppercase font-mono font-bold bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded">
                    Official IMD Warning
                  </span>
                  {hf.properties.signal_number ? (
                    <span className="text-[10px] font-mono font-bold text-amber-400">
                      Signal {hf.properties.signal_number}
                    </span>
                  ) : null}
                </div>
                <h4 className="text-sm font-bold text-red-400">{hf.properties.title}</h4>
                <p className="mt-1 text-xs text-text-muted leading-relaxed">{hf.properties.details}</p>
                <p className="mt-2 text-[10px] text-text-muted border-t border-border/40 pt-1 font-mono">
                  Issued: {new Date(hf.properties.issued_at).toLocaleString()}
                </p>
              </div>
            </MarkerPopup>
          </LibreMarker>
        );
      })}

      {/* AIS & Coastal Telemetry Markers */}
      {visibleMarkers.map((marker) => {

        const [lng, lat] = markerLngLat(marker);
        const config = markerConfig[marker.type] || markerConfig.user;
        const Icon = config.icon;

        return (
          <LibreMarker key={`marker-${marker.id}`} longitude={lng} latitude={lat} anchor="center">
            <MarkerContent>
              <button
                type="button"
                className="group flex flex-col items-center gap-1 cursor-pointer focus:outline-none"
              >
                <div
                  className={`size-8 rounded-full ${config.bg} border ${config.border} flex items-center justify-center shadow-lg backdrop-blur-sm relative group-hover:scale-110 transition-transform`}
                >
                  <Icon size={15} className={config.color} />
                  {marker.type === "hazard" && (
                    <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-avoid rounded-full animate-ping" />
                  )}
                </div>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-surface/90 border border-border text-text-primary opacity-0 group-hover:opacity-100 transition-opacity shadow-md whitespace-nowrap">
                  {marker.label}
                </span>
              </button>
            </MarkerContent>
            <MarkerPopup closeButton offset={20}>
              <div className="w-64 rounded-xl border border-border bg-surface p-3 text-text-primary shadow-2xl backdrop-blur-md">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] uppercase font-mono font-bold text-cyan">
                    {marker.type}
                  </span>
                  <span className="text-[10px] text-text-muted font-mono">
                    {lat.toFixed(2)}°N, {lng.toFixed(2)}°E
                  </span>
                </div>
                <h4 className="text-sm font-bold">{marker.label}</h4>
                {marker.subtitle && <p className="text-xs text-text-muted mt-0.5">{marker.subtitle}</p>}
                {marker.details && (
                  <div className="mt-2 pt-2 border-t border-border/60 grid grid-cols-2 gap-1.5 text-[11px]">
                    {marker.details.speed && (
                      <div>
                        <span className="text-text-muted">Speed:</span>{" "}
                        <span className="font-mono text-cyan">{marker.details.speed}</span>
                      </div>
                    )}
                    {marker.details.waveHeight && (
                      <div>
                        <span className="text-text-muted">Wave:</span>{" "}
                        <span className="font-mono text-cyan">{marker.details.waveHeight}</span>
                      </div>
                    )}
                    {marker.details.warning && (
                      <div className="col-span-2 text-avoid font-semibold mt-1">
                        ⚠️ {marker.details.warning}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </MarkerPopup>
          </LibreMarker>
        );
      })}

      <MapControls position="top-right" showZoom showCompass showLocate showFullscreen />

      {referenceLine && (
        <div className="pointer-events-none absolute bottom-3 left-3 z-10 flex max-w-[calc(100%-5rem)] items-center gap-2 rounded-xl border border-border bg-surface/95 px-3 py-2 text-xs font-semibold text-avoid shadow-lg backdrop-blur-md">
          <Route size={15} className="shrink-0" />
          <span>Reference Line — Not Certified Navigation Route</span>
        </div>
      )}
    </>
  );
}

export default function MarineMap({
  result = null,
  markers = [],
  height = "h-[500px] lg:h-[580px]",
  showControls = true,
  center = [72.8, 19.2],
  zoom = 5.5,
  locationName = "Arabian Sea & Indian Coastline",
  researchLayer,
}: {
  result?: SpatialResult | null;
  markers?: MapMarker[];
  height?: string;
  showControls?: boolean;
  center?: [number, number];
  zoom?: number;
  locationName?: string;
  researchLayer?: ResearchLayerType;
}) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeLayers, setActiveLayers] = useState({
    radar: true,
    ais: true,
    hazards: true,
    routes: true,
  });

  const toggleLayer = (layerKey: keyof typeof activeLayers) => {
    setActiveLayers((prev) => ({ ...prev, [layerKey]: !prev[layerKey] }));
  };

  const markReady = useCallback(() => {
    setError(null);
    setLoaded(true);
  }, []);

  const markError = useCallback(() => {
    if (!loaded) setError("Map basemap style failed to load.");
  }, [loaded]);

  const unavailable = Boolean(error);
  const mapStyle = publicConfig.mapStyleUrl || "https://tiles.openfreemap.org/styles/liberty";

  return (
    <div className={`relative w-full ${height} rounded-2xl overflow-hidden border border-border shadow-xl bg-surface group`}>
      {/* Top Left Compass & Location Header */}
      <div className="absolute top-3 left-3 z-20 flex items-center gap-2 bg-surface/90 border border-border px-3 py-1.5 rounded-xl shadow-md backdrop-blur-md">
        <Compass size={16} className="text-cyan animate-spin" style={{ animationDuration: "25s" }} />
        <span className="text-xs font-bold text-text-primary">{locationName}</span>
        <span className="text-[10px] text-cyan font-mono bg-cyan/10 border border-cyan/30 px-1.5 py-0.2 rounded-md">
          INCOIS Grid
        </span>
      </div>

      {/* Layer Toggles */}
      {showControls && (
        <div className="absolute top-14 left-3 z-20 flex items-center gap-1.5 bg-surface/90 border border-border p-1 rounded-xl shadow-md backdrop-blur-md text-[11px]">
          <button
            onClick={() => toggleLayer("hazards")}
            className={`px-2 py-1 rounded-lg flex items-center gap-1 font-semibold transition-all ${
              activeLayers.hazards ? "bg-avoid/20 text-avoid border border-avoid/40" : "text-text-muted hover:text-text-primary"
            }`}
          >
            <AlertTriangle size={12} />
            <span>Hazards</span>
          </button>
          <button
            onClick={() => toggleLayer("ais")}
            className={`px-2 py-1 rounded-lg flex items-center gap-1 font-semibold transition-all ${
              activeLayers.ais ? "bg-cyan/20 text-cyan border border-cyan/40" : "text-text-muted hover:text-text-primary"
            }`}
          >
            <Ship size={12} />
            <span>AIS Traffic</span>
          </button>
          <button
            onClick={() => toggleLayer("routes")}
            className={`px-2 py-1 rounded-lg flex items-center gap-1 font-semibold transition-all ${
              activeLayers.routes ? "bg-go/20 text-go border border-go/40" : "text-text-muted hover:text-text-primary"
            }`}
          >
            <Navigation size={12} />
            <span>Corridors</span>
          </button>
        </div>
      )}

      {/* MapLibre Canvas Container */}
      {!unavailable && (
        <MapCanvas
          className="orca-map-container"
          theme="light"
          styles={{
            light: mapStyle,
            dark: mapStyle,
          }}
          center={center}
          zoom={zoom}
          maxZoom={14}
          minZoom={3}
          cooperativeGestures
        >
          <JourneyMapContent
            result={result}
            markers={markers}
            activeLayers={activeLayers}
            researchLayer={researchLayer}
            onReady={markReady}
            onError={markError}
          />
        </MapCanvas>
      )}

      {unavailable && (
        <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center bg-surface">
          <AlertTriangle size={32} className="text-avoid mb-2" />
          <h3 className="font-bold text-text-primary">Interactive Nautical Map Offline</h3>
          <p className="text-xs text-text-muted max-w-sm mt-1">
            {error ?? "Connecting to MapLibre tile services..."}
          </p>
        </div>
      )}

      {/* Bottom Provenance Disclaimer */}
      <div className="absolute bottom-3 right-3 z-10 text-[10px] text-text-muted bg-surface/90 border border-border px-2.5 py-1 rounded-lg backdrop-blur-md shadow-sm">
        MapLibre GL Vector • OpenFreeMap Nautical Tiles • INCOIS Spatial Boundary
      </div>
    </div>
  );
}