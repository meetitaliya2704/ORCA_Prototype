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
    fitJourneyGeoJson(
      map,
      result,
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    );
    const frame = window.requestAnimationFrame(() => {
      updateReferenceLine();
      onReady();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [map, onReady, result, updateReferenceLine]);

  return (
    <>
      {pointFeatures.length > 0 && <div className="pointer-events-none absolute left-3 top-3 z-10 rounded-lg border border-white/70 bg-white/95 p-2.5 shadow-sm backdrop-blur-sm">
        <p className="mb-2 text-[0.6875rem] font-bold uppercase tracking-[0.12em] text-[var(--muted-foreground)]">
          Journey features
        </p>
        <div className="grid gap-1.5 text-xs font-semibold text-[var(--foreground)]">
          <span className="flex items-center gap-2"><span className="size-2.5 rounded-full bg-[var(--primary)] ring-2 ring-white" />Origin</span>
          <span className="flex items-center gap-2"><span className="size-2.5 rounded-full bg-[var(--secondary)] ring-2 ring-white" />PFZ destination</span>
          <span className="flex items-center gap-2"><span className="w-5 border-t-2 border-dashed border-[var(--caution)]" />Reference only</span>
        </div>
      </div>}

      {linePoints && (
        <svg
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 z-[3] size-full overflow-hidden"
        >
          <polyline
            points={linePoints}
            fill="none"
            stroke="#9a5a00"
            strokeWidth="3"
            strokeDasharray="8 7"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      )}

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
