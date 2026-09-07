"use client";

import MarineMap from "./marine-map";
import type { JourneyResponse } from "@/lib/schemas/journey";

export function MapPanel({ result }: { result: JourneyResponse | null }) {
  return <MarineMap result={result} />;
}
