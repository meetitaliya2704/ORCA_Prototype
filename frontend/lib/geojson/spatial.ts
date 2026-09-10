import type { AssistantApiResponse } from "@/lib/schemas/assistant-api";
import type { JourneyResponse } from "@/lib/schemas/journey";

export type SpatialResult = JourneyResponse | AssistantApiResponse;
export type SpatialFeature = {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] } | { type: "LineString"; coordinates: [number, number][] };
  properties: Record<string, unknown>;
};

export function spatialFeatures(result: SpatialResult | null): SpatialFeature[] {
  const geojson = result?.geojson;
  if (!geojson) return [];
  return (geojson.type === "FeatureCollection" ? geojson.features : [geojson]) as SpatialFeature[];
}

export function spatialPoint(result: SpatialResult | null, type: "origin" | "pfz_destination") {
  return spatialFeatures(result).find((feature) =>
    feature.geometry.type === "Point" && (
      feature.properties.feature_type === type
      || type === "pfz_destination" && "landing_centre" in feature.properties
    ),
  );
}

export function isJourneyResponse(result: SpatialResult): result is JourneyResponse {
  return "journey_status" in result;
}
