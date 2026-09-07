import type { JourneyResponse } from "@/lib/schemas/journey";

export function assertGeoJsonCoordinateOrder(response: JourneyResponse) {
  if (!response.geojson) return true;
  for (const feature of response.geojson.features) {
    const coordinates = feature.geometry.type === "Point"
      ? [feature.geometry.coordinates]
      : feature.geometry.coordinates;
    for (const [longitude, latitude] of coordinates) {
      if (longitude < -180 || longitude > 180 || latitude < -90 || latitude > 90) return false;
    }
  }
  return true;
}
