import { z } from "zod";
import { orcaFetch } from "./client";

export const hazardFeaturePropertiesSchema = z.looseObject({
  hazard_type: z.enum(["cyclone_cone", "cyclone_track", "port_warning", "coastal_warning"]),
  title: z.string(),
  severity: z.enum(["INFO", "WATCH", "ALERT", "WARNING", "DANGER"]),
  signal_number: z.number().nullable().optional(),
  details: z.string(),
  issued_at: z.string(),
  valid_until: z.string().nullable().optional(),
  extra: z.record(z.string(), z.unknown()).optional(),
});

export const hazardGeoJsonFeatureSchema = z.looseObject({
  type: z.literal("Feature"),
  geometry: z.looseObject({
    type: z.string(),
    coordinates: z.unknown(),
  }),
  properties: hazardFeaturePropertiesSchema,
});

export const imdMarineHazardCollectionSchema = z.looseObject({
  type: z.literal("FeatureCollection"),
  features: z.array(hazardGeoJsonFeatureSchema),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

export type IMDMarineHazardCollection = z.infer<typeof imdMarineHazardCollectionSchema>;
export type HazardGeoJsonFeature = z.infer<typeof hazardGeoJsonFeatureSchema>;

export const coastalBulletinItemSchema = z.looseObject({
  coastal_zone: z.string(),
  wind_direction: z.string().nullable().optional(),
  wind_speed_knots_min: z.number().nullable().optional(),
  wind_speed_knots_max: z.number().nullable().optional(),
  wind_gusts_knots: z.number().nullable().optional(),
  sea_condition: z.string().nullable().optional(),
  fishermen_warning: z.boolean().default(false),
  advisory_text: z.string(),
  valid_from: z.string().nullable().optional(),
  valid_to: z.string().nullable().optional(),
});

export const coastalBulletinResponseSchema = z.looseObject({
  status: z.string(),
  bulletin_number: z.string().nullable().optional(),
  issued_at: z.string().nullable().optional(),
  bulletins: z.array(coastalBulletinItemSchema),
});

export type CoastalBulletinItem = z.infer<typeof coastalBulletinItemSchema>;
export type CoastalBulletinResponse = z.infer<typeof coastalBulletinResponseSchema>;

export interface UnifiedAlertItem {
  id: string;
  source: "IMD_COASTAL" | "IMD_PORT" | "IMD_CYCLONE";
  severity: "high" | "medium" | "low";
  priorityLabel: string;
  title: string;
  region: string;
  issuedAt: string;
  description: string;
  category: "cyclone" | "port_signal" | "squall" | "wind" | "general";
  targetModes: ("fisherman" | "authority" | "operator" | "researcher")[];
  coordinates?: string;
  metrics?: {
    windKnots?: string;
    windGustsKnots?: number;
    seaCondition?: string;
    signalNumber?: number;
    signalType?: string;
  };
  fishermenWarning?: boolean;
}

export async function fetchMarineHazards(signal?: AbortSignal): Promise<IMDMarineHazardCollection> {
  const { data } = await orcaFetch("/v1/marine/warnings", imdMarineHazardCollectionSchema, { signal });
  return data;
}

export async function fetchCoastalBulletins(signal?: AbortSignal): Promise<CoastalBulletinResponse> {
  const { data } = await orcaFetch("/v1/marine/warnings/coastal", coastalBulletinResponseSchema, { signal });
  return data;
}

export async function fetchUnifiedAlerts(signal?: AbortSignal): Promise<UnifiedAlertItem[]> {
  const [hazardsRes, coastalRes] = await Promise.allSettled([
    fetchMarineHazards(signal),
    fetchCoastalBulletins(signal),
  ]);

  const alerts: UnifiedAlertItem[] = [];

  // 1. Process Cyclone Cones and Port Warnings from GeoJSON hazards
  if (hazardsRes.status === "fulfilled" && hazardsRes.value?.features) {
    for (const feat of hazardsRes.value.features) {
      const p = feat.properties;
      const coords = feat.geometry?.coordinates;
      const coordsStr =
        Array.isArray(coords) && typeof coords[0] === "number" && typeof coords[1] === "number"
          ? `${coords[1].toFixed(2)}° N, ${coords[0].toFixed(2)}° E`
          : undefined;

      if (p.hazard_type === "cyclone_cone") {
        alerts.push({
          id: `cyclone-${p.title.toLowerCase().replace(/[^a-z0-9]/g, "-")}`,
          source: "IMD_CYCLONE",
          severity: "high",
          priorityLabel: "CRITICAL DANGER",
          title: p.title,
          region: "Bay of Bengal / Adjoining Basin",
          issuedAt: p.issued_at,
          description: p.details,
          category: "cyclone",
          targetModes: ["fisherman", "operator", "authority"],
          coordinates: coordsStr,
          metrics: { seaCondition: "Phenomenal / Extreme Swells" },
        });
      } else if (p.hazard_type === "port_warning" && (p.signal_number ?? 0) > 0) {
        const sigNum = p.signal_number ?? 1;
        const isHigh = sigNum >= 3;
        alerts.push({
          id: `port-${p.title.toLowerCase().replace(/[^a-z0-9]/g, "-")}`,
          source: "IMD_PORT",
          severity: isHigh ? "high" : "medium",
          priorityLabel: isHigh ? "PORT DANGER SIGNAL" : "PORT CAUTION",
          title: p.title,
          region: typeof p.extra?.state === "string" ? p.extra.state : "Coastal Port",
          issuedAt: p.issued_at,
          description: p.details,
          category: "port_signal",
          targetModes: ["fisherman", "operator", "authority"],
          coordinates: coordsStr,
          metrics: { signalNumber: sigNum, signalType: `Signal ${sigNum}` },
        });
      }
    }
  }

  // 2. Process Regional Coastal Bulletins
  if (coastalRes.status === "fulfilled" && coastalRes.value?.bulletins) {
    for (const b of coastalRes.value.bulletins) {
      const isSquall = b.fishermen_warning || (b.wind_gusts_knots != null && b.wind_gusts_knots >= 35);
      const isRough = b.sea_condition?.toLowerCase().includes("rough") ?? false;
      const isMod = b.sea_condition?.toLowerCase().includes("moderate") ?? false;

      const severity = isSquall || isRough ? "high" : isMod ? "medium" : "low";
      const priorityLabel = isSquall
        ? "FISHERMEN NO-SAIL WARNING"
        : severity === "high"
        ? "ROUGH SEA ALERT"
        : severity === "medium"
        ? "CAUTION ADVISORY"
        : "ROUTINE BULLETIN";

      alerts.push({
        id: `coastal-${b.coastal_zone.toLowerCase().replace(/[^a-z0-9]/g, "-")}`,
        source: "IMD_COASTAL",
        severity,
        priorityLabel,
        title: `${b.coastal_zone} Coastal Advisory`,
        region: b.coastal_zone,
        issuedAt: b.valid_from || new Date().toISOString(),
        description: b.advisory_text,
        category: isSquall ? "squall" : "wind",
        targetModes: ["fisherman", "operator"],
        metrics: {
          windKnots:
            b.wind_speed_knots_min && b.wind_speed_knots_max
              ? `${b.wind_speed_knots_min}–${b.wind_speed_knots_max} kts`
              : undefined,
          windGustsKnots: b.wind_gusts_knots || undefined,
          seaCondition: b.sea_condition || undefined,
        },
        fishermenWarning: b.fishermen_warning,
      });
    }
  }

  return alerts;
}

