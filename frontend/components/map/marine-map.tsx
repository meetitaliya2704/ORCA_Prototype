"use client";

import { LngLatBounds, type Map as MapLibreMap } from "maplibre-gl";
import {
  AlertTriangle,
  Anchor,
  Layers3,
  MapPin,
  Navigation,
  Route,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Card } from "@/components/ui/card";
import {
  Map as MapCanvas,
  MapControls,
  MapMarker,
  MarkerContent,
  MarkerPopup,
  useMap,
} from "@/components/ui/map";
import { publicConfig } from "@/lib/config";
import { assertGeoJsonCoordinateOrder } from "@/lib/geojson/journey";
import { isJourneyResponse, spatialFeatures, type SpatialFeature, type SpatialResult } from "@/lib/geojson/spatial";
import { fetchMarineHazards, type HazardGeoJsonFeature } from "@/lib/api/warnings";

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
  }
  return true;
}

function featureLabel(feature: SpatialFeature) {
  return feature.properties.feature_type === "origin" ? "Origin" : "PFZ destination";
}

function JourneyMapContent({
  result,
  onReady,
  onError,
}: {
  result: SpatialResult | null;
  onReady: () => void;
  onError: () => void;
}) {
  const { map } = useMap();
  const [linePoints, setLinePoints] = useState<string | null>(null);
  const [hazardFeatures, setHazardFeatures] = useState<HazardGeoJsonFeature[]>([]);
  const [conePolygons, setConePolygons] = useState<{ id: string; points: string; title: string; details: string; center: [number, number] }[]>([]);
  const [trackPolylines, setTrackPolylines] = useState<{ id: string; points: string; title: string }[]>([]);

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
  }, [map, referenceLine, hazardFeatures]);

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
    fitJourneyGeoJson(
      map,
      result,
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    );
    const frame = window.requestAnimationFrame(() => {
      updateOverlays();
      onReady();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [map, onReady, result, updateOverlays]);

  return (
    <>
      {/* Official IMD Route Veto Alert Banner */}
      {isVetoed && vetoReason && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-30 max-w-md w-[92%] rounded-xl border border-red-500/60 bg-white/95 p-3.5 shadow-2xl backdrop-blur-md flex items-start gap-3 animate-in fade-in slide-in-from-top duration-300">
          <div className="p-2 rounded-lg bg-red-500/20 text-red-500 shrink-0 mt-0.5">
            <AlertTriangle size={18} className="animate-pulse" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase font-mono font-bold bg-red-500/20 text-red-500 px-1.5 py-0.5 rounded border border-red-500/30">
                Official IMD Veto
              </span>
              <span className="text-xs font-bold text-red-500">Route Unsafe</span>
            </div>
            <p className="mt-1 text-xs text-stone-900 leading-relaxed font-medium">
              {vetoReason.message}
            </p>
          </div>
        </div>
      )}

      {pointFeatures.length > 0 && <div className="pointer-events-none absolute left-3 top-3 z-10 rounded-lg border border-white/70 bg-white/95 p-2.5 shadow-sm backdrop-blur-sm">
        <p className="mb-2 text-[0.6875rem] font-bold uppercase tracking-[0.12em] text-[var(--muted-foreground)]">
          Journey features
        </p>
        <div className="grid gap-1.5 text-xs font-semibold text-[var(--foreground)]">
          <span className="flex items-center gap-2"><span className="size-2.5 rounded-full bg-[var(--primary)] ring-2 ring-white" />Origin</span>
          <span className="flex items-center gap-2"><span className="size-2.5 rounded-full bg-[var(--secondary)] ring-2 ring-white" />PFZ destination</span>
          <span className="flex items-center gap-2"><span className={`w-5 border-t-2 border-dashed ${isVetoed ? "border-red-500" : "border-[var(--caution)]"}`} />{isVetoed ? "Vetoed route" : "Reference only"}</span>
        </div>
      </div>}

      <svg
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-[3] size-full overflow-hidden"
      >
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

        {linePoints && (
          <polyline
            points={linePoints}
            fill="none"
            stroke={isVetoed ? "#ef4444" : "#0ea5e9"}
            strokeWidth="3"
            strokeDasharray={isVetoed ? "6 4" : "8 7"}
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>

      {/* Cyclone Cone Center Labels */}
      {conePolygons.map((cp) => (
        <MapMarker
          key={`cone-marker-${cp.id}`}
          longitude={cp.center[0]}
          latitude={cp.center[1]}
          anchor="center"
        >
          <MarkerContent>
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-red-500/20 border border-red-500/60 text-red-600 font-bold text-[10px] shadow-lg backdrop-blur-md animate-pulse cursor-pointer">
              <AlertTriangle size={12} className="text-red-600" />
              <span>{cp.title}</span>
            </div>
          </MarkerContent>
          <MarkerPopup closeButton offset={15}>
            <div className="w-64 rounded-xl border border-red-500/40 bg-white p-3 text-stone-900 shadow-2xl backdrop-blur-md">
              <span className="text-[10px] uppercase font-mono font-bold bg-red-500/20 text-red-600 px-1.5 py-0.5 rounded">
                Official Cyclone Cone
              </span>
              <h4 className="mt-1 text-sm font-bold text-red-600">{cp.title}</h4>
              <p className="mt-1 text-xs text-stone-600">{cp.details}</p>
            </div>
          </MarkerPopup>
        </MapMarker>
      ))}

      {pointFeatures.map((feature) => {
        if (feature.geometry.type !== "Point") return null;
        const [longitude, latitude] = feature.geometry.coordinates;
        const origin = feature.properties.feature_type === "origin";
        return (
          <MapMarker
            key={String(feature.properties.feature_type ?? `${longitude}:${latitude}`)}
            longitude={longitude}
            latitude={latitude}
            anchor="center"
          >
            <MarkerContent>
              <button
                type="button"
                aria-label={`Inspect ${featureLabel(feature)}`}
                className="group flex size-11 items-center justify-center rounded-full focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
              >
                <span className={`flex size-8 items-center justify-center rounded-full border-[3px] border-white text-white shadow-md transition-transform group-hover:scale-105 ${origin ? "bg-[var(--primary)]" : "bg-[var(--secondary)]"}`}>
                  {origin ? <Navigation aria-hidden="true" className="size-4" /> : <Anchor aria-hidden="true" className="size-4" />}
                </span>
              </button>
            </MarkerContent>
            <MarkerPopup closeButton offset={20}>
              <div className="w-64 rounded-lg border border-[var(--border)] bg-white p-3 text-[var(--foreground)] shadow-lg">
                <p className="flex items-center gap-2 font-bold">
                  {origin ? <Navigation aria-hidden="true" className="size-4 text-[var(--primary)]" /> : <Anchor aria-hidden="true" className="size-4 text-[var(--secondary)]" />}
                  {featureLabel(feature)}
                </p>
                <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                  {latitude.toFixed(5)}, {longitude.toFixed(5)}
                </p>
                {!origin && journeyPfz && (
                  <p className="mt-2 border-t border-[var(--border)] pt-2 text-xs">
                    {journeyPfz.landing_centre} · {journeyPfz.region_name}
                  </p>
                )}
              </div>
            </MarkerPopup>
          </MapMarker>
        );
      })}

      {/* Official IMD Hazard Overlays (Port Warnings, Gale Signals) */}
      {hazardFeatures.map((hf, idx) => {
        if (hf.geometry.type !== "Point" || !Array.isArray(hf.geometry.coordinates)) return null;
        const [lon, lat] = hf.geometry.coordinates as [number, number];
        const isSevere = hf.properties.severity === "DANGER" || hf.properties.severity === "ALERT";
        return (
          <MapMarker
            key={`hazard-${idx}-${lon}-${lat}`}
            longitude={lon}
            latitude={lat}
            anchor="bottom"
          >
            <MarkerContent>
              <button
                type="button"
                aria-label={`Official IMD Warning: ${hf.properties.title}`}
                className="group flex size-9 items-center justify-center rounded-full focus-visible:outline focus-visible:outline-2"
              >
                <span className={`flex size-7 items-center justify-center rounded-full border-2 border-white text-white shadow-md animate-pulse ${isSevere ? "bg-red-600" : "bg-amber-500"}`}>
                  <AlertTriangle aria-hidden="true" className="size-3.5" />
                </span>
              </button>
            </MarkerContent>
            <MarkerPopup closeButton offset={15}>
              <div className="w-72 rounded-lg border border-red-200 bg-white p-3 text-[var(--foreground)] shadow-xl">
                <div className="flex items-center gap-2 border-b border-red-100 pb-2">
                  <span className="rounded bg-red-100 px-1.5 py-0.5 text-[0.625rem] font-bold text-red-700 uppercase">
                    IMD Official Warning
                  </span>
                  {hf.properties.signal_number && (
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[0.625rem] font-bold text-amber-800">
                      Signal {hf.properties.signal_number}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-xs font-bold text-red-950">
                  {hf.properties.title}
                </p>
                <p className="mt-1 text-xs text-[var(--muted-foreground)] leading-relaxed">
                  {hf.properties.details}
                </p>
                <p className="mt-2 text-[0.625rem] text-[var(--muted-foreground)] border-t border-gray-100 pt-1">
                  Issued: {new Date(hf.properties.issued_at).toLocaleString()}
                </p>
              </div>
            </MarkerPopup>
          </MapMarker>
        );
      })}


      <MapControls
        position="top-right"
        showZoom
        showCompass
        showLocate
        showFullscreen
      />
      {referenceLine && <div className="pointer-events-none absolute bottom-3 left-3 z-10 flex max-w-[calc(100%-5rem)] items-center gap-2 rounded-md border border-[var(--border)] bg-white/95 px-3 py-2 text-xs font-semibold text-[var(--caution)] shadow-sm">
        <Route aria-hidden="true" className="size-4 shrink-0" />
        <span>Reference line — route not evaluated</span>
      </div>}
    </>
  );
}

export default function MarineMap({ result }: { result: SpatialResult | null }) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const features = useMemo(() => spatialFeatures(result), [result]);
  const markReady = useCallback(() => {
    setError(null);
    setLoaded(true);
  }, []);
  const markError = useCallback(() => {
    if (!loaded) setError("The configured map style could not be loaded.");
  }, [loaded]);

  const unavailable = !publicConfig.mapStyleUrl || Boolean(error);
  return (
    <Card className="map-panel overflow-hidden" aria-label="Marine journey map panel">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--border)] px-4 py-3">
        <div>
          <h2 className="flex items-center gap-2 font-bold">
            <Layers3 aria-hidden="true" className="size-5 text-[var(--secondary)]" />
            Marine map
          </h2>
          <p id="map-description" className="mt-0.5 text-sm text-[var(--muted-foreground)]">
            Explore the origin and PFZ advisory destination on the MapLibre basemap.
          </p>
        </div>
        <span className="inline-flex min-h-8 items-center gap-1.5 rounded-full bg-[var(--caution-surface)] px-3 py-1 text-xs font-semibold text-[var(--caution)]">
          <Route aria-hidden="true" className="size-3.5" />
          Reference line — route not evaluated
        </span>
      </div>

      <div className="map-frame relative bg-[#dcebed]" aria-describedby="map-description">
        {!unavailable && (
          <MapCanvas
            className="orca-map-container"
            theme="light"
            styles={{
              light: publicConfig.mapStyleUrl,
              dark: publicConfig.mapStyleUrl,
            }}
            center={[72.3, 19.5]}
            zoom={4.6}
            maxZoom={15}
            minZoom={2}
            cooperativeGestures
          >
            <JourneyMapContent result={result} onReady={markReady} onError={markError} />
          </MapCanvas>
        )}

        {unavailable && (
          <div role="alert" className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center">
            <AlertTriangle aria-hidden="true" className="size-8 text-[var(--caution)]" />
            <h3 className="mt-2 font-bold">Map unavailable</h3>
            <p className="mt-1 max-w-md text-sm">
              {error ?? "Set NEXT_PUBLIC_MAP_STYLE_URL to a MapLibre-compatible style. Journey evidence remains available below."}
            </p>
          </div>
        )}
      </div>

      {features.some((feature) => feature.geometry.type === "Point") && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-[var(--border)] bg-[var(--surface-muted)]/50 px-4 py-3 text-xs text-[var(--muted-foreground)]">
          <span className="flex items-center gap-1.5"><MapPin aria-hidden="true" className="size-3.5" />Select a marker for details</span>
          <span>Scroll to zoom; drag to explore</span>
          {!loaded && <span role="status">Preparing interactive map…</span>}
        </div>
      )}
    </Card>
  );
}
