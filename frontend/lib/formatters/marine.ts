import type { EvidenceItem } from "@/lib/schemas/journey";

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : undefined;
}

export function nestedValue(value: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((current, key) => object(current)?.[key], value);
}

function firstNumber(value: unknown, paths: string[]) {
  for (const path of paths) {
    const candidate = nestedValue(value, path);
    if (typeof candidate === "number" && Number.isFinite(candidate)) return candidate;
  }
}

function firstString(value: unknown, paths: string[]) {
  for (const path of paths) {
    const candidate = nestedValue(value, path);
    if (typeof candidate === "string" && candidate) return candidate;
  }
}

const definitions = {
  sst: { label: "Sea surface temperature", paths: ["temperature_celsius", "temperature.value", "value"], unit: "°C" },
  chlorophyll: { label: "Chlorophyll-a", paths: ["chlorophyll_a.value", "chlorophyll_mg_m3", "chlorophyll.value", "value"], unit: "mg/m³" },
  waves: { label: "Significant wave height", paths: ["significant_wave_height.value"], unit: "m" },
  wind: { label: "Wind speed", paths: ["wind_speed.value", "wind_speed_mps", "speed_mps"], unit: "m/s" },
  currents: { label: "Total surface current", paths: ["total_current.speed_mps", "speed_mps"], unit: "m/s" },
  sea_level: { label: "Total modelled sea level", paths: ["total_modelled_sea_level_m"], unit: "m" },
} as const;

export type MarineSourceName = keyof typeof definitions;

export function summarizeEvidence(source: MarineSourceName, item: EvidenceItem) {
  const data = item.data;
  const definition = definitions[source];
  return {
    label: definition.label,
    value: firstNumber(data, [...definition.paths]),
    unit: definition.unit,
    validTime: firstString(data, ["valid_time", "analysis_time", "provider_valid_time"]),
    freshness: firstString(data, ["snapshot.status", "cache_status", "freshness"]),
    quality: firstString(data, ["evidence_quality", "quality.evidence_quality", "quality", "sampling_quality", "spatial_representativeness"]),
    provider: firstString(data, ["provider", "source.name", "source.provider"]),
    product: firstString(data, ["product_id", "source.product_id"]),
    dataset: firstString(data, ["dataset_id", "source.dataset_id"]),
    datasetVersion: firstString(data, ["dataset_version", "source.dataset_version"]),
    sampledLatitude: firstNumber(data, ["sampled_location.latitude", "sampled_latitude"]),
    sampledLongitude: firstNumber(data, ["sampled_location.longitude", "sampled_longitude"]),
    distance: firstNumber(data, ["distance_km", "sample_distance_km"]),
    uncertainty: firstNumber(data, ["quality.uncertainty_percent", "uncertainty_percent", "chlorophyll_uncertainty_percent"]),
    direction: source === "wind"
      ? firstString(data, ["wind_direction_from.compass", "compass_direction_from"])
      : source === "currents"
        ? firstString(data, ["total_current.direction_toward_compass"])
        : undefined,
    directionSemantics: source === "wind" ? "direction-from" : source === "currents" ? "direction-toward" : undefined,
    warnings: Array.isArray(object(data)?.warnings) ? object(data)?.warnings as string[] : [],
    attribution: firstString(data, ["attribution", "source.attribution"]),
    notice: firstString(data, ["notice"]),
  };
}

export function formatNumber(value: number | undefined, maximumFractionDigits = 2) {
  return value === undefined ? "Unavailable" : new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(value);
}

export function formatTime(value: string | undefined) {
  return value ? new Date(value).toLocaleString() : "Not supplied";
}
