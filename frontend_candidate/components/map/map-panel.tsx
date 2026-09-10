"use client";

import MarineMap from "./marine-map";
import type { SpatialResult } from "@/lib/geojson/spatial";

export function MapPanel({ result }: { result: SpatialResult | null }) {
  return <MarineMap result={result} />;
}
