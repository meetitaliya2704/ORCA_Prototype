"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Expand, MapPinned, X } from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { Button } from "@/components/ui/button";
import { isJourneyResponse, spatialFeatures, spatialPoint, type SpatialResult } from "@/lib/geojson/spatial";

const LazyMapPanel = lazy(() => import("./map-panel").then((module) => ({ default: module.MapPanel })));

export function SpatialMapDialog({ result }: { result: SpatialResult | null }) {
  const [open, setOpen] = useState(false);
  if (!spatialFeatures(result).some((feature) => feature.geometry.type === "Point")) return null;
  const originFeature = spatialPoint(result, "origin");
  const pfzFeature = spatialPoint(result, "pfz_destination");
  const origin = result && isJourneyResponse(result)
    ? result.request.origin
    : originFeature?.geometry.type === "Point"
      ? { longitude: originFeature.geometry.coordinates[0], latitude: originFeature.geometry.coordinates[1] }
      : null;
  const pfz = result && isJourneyResponse(result)
    ? result.pfz?.nearest_pfz
    : pfzFeature?.geometry.type === "Point"
      ? { longitude: pfzFeature.geometry.coordinates[0], latitude: pfzFeature.geometry.coordinates[1] }
      : null;
  const distance = result && isJourneyResponse(result) ? result.distance : null;
  return <section className="map-summary" aria-label="Spatial result summary">
    <div className="min-w-0">
      <h3 className="flex items-center gap-2 font-semibold"><MapPinned aria-hidden="true" className="size-4 text-[var(--secondary)]" />Spatial context</h3>
      {origin && <p className="mt-1 font-data text-xs">Origin: {formatCoordinate(origin.latitude, "N", "S")}, {formatCoordinate(origin.longitude, "E", "W")}</p>}
      {pfz && <p className="font-data text-xs">Nearest PFZ: {formatCoordinate(pfz.latitude, "N", "S")}, {formatCoordinate(pfz.longitude, "E", "W")}</p>}
      {distance && <p className="mt-1 text-sm">{distance.kilometres} km · {distance.bearing_degrees}° {distance.direction}</p>}
      <p className="mt-1 text-xs text-[var(--muted-foreground)]">The map is a supporting visualization. All core PFZ and assessment details are available above.</p>
    </div>
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger asChild><Button variant="secondary"><Expand aria-hidden="true" className="size-4" />View on map</Button></DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-slate-950/60" />
        <DialogPrimitive.Content className="map-dialog fixed inset-0 z-50 flex min-h-0 flex-col bg-[var(--background)] p-3 focus:outline-none sm:inset-4 sm:rounded-xl sm:border sm:border-[var(--border)] sm:p-4 lg:left-auto lg:w-[min(62rem,72vw)]">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div><DialogPrimitive.Title className="text-lg font-bold">Supporting spatial visualization</DialogPrimitive.Title><DialogPrimitive.Description className="text-sm text-[var(--muted-foreground)]">Origin, PFZ destination, and Reference line — route not evaluated.</DialogPrimitive.Description></div>
            <DialogPrimitive.Close asChild><Button variant="ghost" size="icon" aria-label="Close map"><X aria-hidden="true" /></Button></DialogPrimitive.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-hidden"><Suspense fallback={<div role="status" className="flex h-full min-h-80 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--surface-muted)]">Loading supporting map…</div>}><LazyMapPanel result={result} /></Suspense></div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  </section>;
}

function formatCoordinate(value: number, positive: string, negative: string) {
  return `${Math.abs(value).toFixed(4)}° ${value >= 0 ? positive : negative}`;
}
