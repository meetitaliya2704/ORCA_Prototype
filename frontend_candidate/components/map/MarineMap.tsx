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
import type { MapMarker } from "@/lib/types";

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
  onReady,
  onError,
}: {
  result: SpatialResult | null;
  markers?: MapMarker[];
  activeLayers: { radar: boolean; ais: boolean; hazards: boolean; routes: boolean };
  onReady: () => void;
  onError: () => void;
}) {
  const { map } = useMap();
  const [linePoints, setLinePoints] = useState<string | null>(null);

  const pointFeatures = useMemo(
    () => spatialFeatures(result).filter((feature) => feature.geometry.type === "Point"),
    [result],
  );

  const referenceLine = useMemo(
    () => spatialFeatures(result).find((feature) => feature.geometry.type === "LineString"),
    [result],
  );

  const journeyPfz = result && isJourneyResponse(result) ? result.pfz?.nearest_pfz : null;

  const updateReferenceLine = useCallback(() => {
    if (!map || referenceLine?.geometry.type !== "LineString") {
      setLinePoints(null);
      return;
    }
    setLinePoints(
      referenceLine.geometry.coordinates
        .map((coordinate) => {
          const point = map.project(coordinate as [number, number]);
          return `${point.x},${point.y}`;
        })
        .join(" "),
    );
  }, [map, referenceLine]);

  useEffect(() => {
    if (!map) return;
    const handleError = () => {
      if (!map.isStyleLoaded()) onError();
    };
    const startupTimer = window.setTimeout(() => {
      if (!map.isStyleLoaded()) onError();
    }, 15_000);

    map.on("error", handleError);
    map.on("move", updateReferenceLine);
    map.on("resize", updateReferenceLine);

    return () => {
      window.clearTimeout(startupTimer);
      map.off("error", handleError);
      map.off("move", updateReferenceLine);
      map.off("resize", updateReferenceLine);
    };
  }, [map, onError, updateReferenceLine]);

  useEffect(() => {
    if (!map) return;
    map.resize();
    const hasFitted = fitJourneyGeoJson(
      map,
      result,
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    );
    if (!hasFitted && markers.length > 0) {
      // Fit to markers if no journey result
      const bounds = markers.reduce(
        (box, m) => box.extend(markerLngLat(m)),
        new LngLatBounds(markerLngLat(markers[0]), markerLngLat(markers[0])),
      );
      map.fitBounds(bounds, { padding: 60, maxZoom: 8, duration: 400 });
    }
    const frame = window.requestAnimationFrame(() => {
      updateReferenceLine();
      onReady();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [map, onReady, result, markers, updateReferenceLine]);

  const visibleMarkers = markers.filter((m) => {
    if (m.type === "hazard" && !activeLayers.hazards) return false;
    if (m.type === "vessel" && !activeLayers.ais) return false;
    if (m.type === "route" && !activeLayers.routes) return false;
    return true;
  });

  return (
    <>
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
              <span className="w-5 border-t-2 border-dashed border-avoid" />
              Reference Bearing
            </span>
          </div>
        </div>
      )}

      {/* Reference Line */}
      {linePoints && (
        <svg aria-hidden="true" className="pointer-events-none absolute inset-0 z-[3] size-full overflow-hidden">
          <polyline
            points={linePoints}
            fill="none"
            stroke="#0ea5e9"
            strokeWidth="3"
            strokeDasharray="8 6"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      )}

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
}: {
  result?: SpatialResult | null;
  markers?: MapMarker[];
  height?: string;
  showControls?: boolean;
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
        <span className="text-xs font-bold text-text-primary">Arabian Sea & Indian Coastline</span>
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
          center={[72.8, 19.2]}
          zoom={5.5}
          maxZoom={14}
          minZoom={3}
          cooperativeGestures
        >
          <JourneyMapContent
            result={result}
            markers={markers}
            activeLayers={activeLayers}
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