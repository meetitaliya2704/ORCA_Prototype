import { z } from "zod";

const finiteNumber = z.number().finite();
const awareTimestamp = z.string().datetime({ offset: true });
const optionalLimit = finiteNumber.positive().nullable().optional();

export const operationalLimitsSchema = z.object({
  maximum_significant_wave_height_m: optionalLimit,
  maximum_wind_speed_m_s: optionalLimit,
  maximum_surface_current_speed_m_s: optionalLimit,
});

export const journeyRequestSchema = z
  .object({
    origin: z.object({
      latitude: finiteNumber.min(-90).max(90),
      longitude: finiteNumber.min(-180).max(180),
    }),
    at: awareTimestamp.nullable().optional(),
    operational_limits: operationalLimitsSchema,
    near_limit_percentage: finiteNumber.positive().max(100).nullable().optional(),
    include_origin_evidence: z.boolean().default(true),
    include_destination_evidence: z.boolean().default(true),
    include_geojson: z.boolean().default(true),
  })
  .superRefine((value, context) => {
    const limits = Object.values(value.operational_limits);
    if (!limits.some((limit) => limit !== null && limit !== undefined)) {
      context.addIssue({
        code: "custom",
        path: ["operational_limits"],
        message: "Supply at least one operational limit.",
      });
    }
  });

const evidenceStateSchema = z.enum([
  "available",
  "degraded",
  "pending",
  "unavailable",
  "not_requested",
]);

const chlorophyllQualitySchema = z.object({
  flag_value: z.number().int().nonnegative(),
  land: z.boolean(),
  interpolated: z.boolean(),
  uncertainty_percent: finiteNumber.nonnegative().nullable(),
  evidence_quality: z.enum(["normal", "degraded"]),
});

const sourceDataSchema = z.looseObject({
  provider: z.string().optional(),
  product_id: z.string().optional(),
  dataset_id: z.string().optional(),
  dataset_version: z.string().optional(),
  valid_time: awareTimestamp.optional(),
  analysis_time: awareTimestamp.optional(),
  retrieved_at: awareTimestamp.optional(),
  cache_status: z.string().optional(),
  quality: z.union([z.string(), chlorophyllQualitySchema]).optional(),
  sampling_quality: z.string().optional(),
  evidence_quality: z.string().optional(),
  warnings: z.array(z.string()).optional(),
  attribution: z.string().optional(),
  notice: z.string().optional(),
});

const evidenceItemSchema = z.object({
  state: evidenceStateSchema,
  data: sourceDataSchema.nullable().optional(),
});

const evidenceSourcesSchema = z.object({
  pfz: evidenceItemSchema,
  sst: evidenceItemSchema,
  chlorophyll: evidenceItemSchema,
  waves: evidenceItemSchema,
  wind: evidenceItemSchema,
  currents: evidenceItemSchema,
  sea_level: evidenceItemSchema,
});

export const marineEvidenceSchema = z.object({
  request: z.object({
    latitude: finiteNumber.min(-90).max(90),
    longitude: finiteNumber.min(-180).max(180),
    at: awareTimestamp,
  }),
  generated_at: awareTimestamp,
  status: z.enum(["complete", "partial", "unavailable"]),
  summary: z.object({
    requested_sources: z.number().int().min(1).max(7),
    available_sources: z.number().int().min(0).max(7),
    unavailable_sources: z.number().int().min(0).max(7),
    degraded_sources: z.number().int().min(0).max(7),
    pending_sources: z.number().int().min(0).max(7),
  }),
  evidence: evidenceSourcesSchema,
  failures: z.array(z.looseObject({
    source: z.string(),
    state: z.enum(["pending", "unavailable"]),
    code: z.string(),
    message: z.string(),
  })).default([]),
  notices: z.array(z.string()).default([]),
});

const assessmentSchema = z.looseObject({
  generated_at: awareTimestamp,
  outcome: z.enum([
    "WITHIN_CONFIGURED_LIMITS",
    "CAUTION",
    "LIMIT_EXCEEDED",
    "INSUFFICIENT_EVIDENCE",
    "POLICY_NOT_CONFIGURED",
  ]),
  evidence_confidence: z.enum(["NORMAL", "DEGRADED", "INSUFFICIENT"]),
  rules: z.array(z.looseObject({
    rule_id: z.string(),
    observed_value: finiteNumber.nullable(),
    unit: z.string(),
    configured_limit: finiteNumber.positive(),
    outcome: z.enum(["within_limit", "near_limit", "exceeded", "unknown"]),
    evidence_quality: z.enum(["normal", "degraded", "insufficient"]),
  })),
  reasons: z.array(z.looseObject({ code: z.string(), message: z.string() })),
  official_warning_coverage: z.literal("not_integrated"),
  notices: z.array(z.string()),
});

const locationResultSchema = z.object({
  location: z.object({ latitude: finiteNumber, longitude: finiteNumber }),
  state: z.enum(["available", "unavailable"]),
  evidence: marineEvidenceSchema.nullable().optional(),
  assessment: assessmentSchema.nullable().optional(),
  failure: z.looseObject({ code: z.string(), message: z.string() }).nullable().optional(),
});

const nearestPfzSchema = z.looseObject({
  sector_code: z.string(),
  region_name: z.string(),
  landing_centre: z.string(),
  latitude: finiteNumber,
  longitude: finiteNumber,
  distance_km: finiteNumber.nonnegative(),
  bearing_deg: finiteNumber.min(0).max(360),
  direction: z.string(),
  distance_min_km: finiteNumber.nullable().optional(),
  distance_max_km: finiteNumber.nullable().optional(),
  depth_min_m: finiteNumber.nullable().optional(),
  depth_max_m: finiteNumber.nullable().optional(),
  distance_from_coast_km: z.object({
    minimum: finiteNumber.nonnegative().nullable(),
    maximum: finiteNumber.nonnegative().nullable(),
  }).optional(),
  depth_m: z.object({
    minimum: finiteNumber.nonnegative().nullable(),
    maximum: finiteNumber.nonnegative().nullable(),
  }).optional(),
});

const featureSchema = z.looseObject({
  type: z.literal("Feature"),
  geometry: z.discriminatedUnion("type", [
    z.object({ type: z.literal("Point"), coordinates: z.tuple([finiteNumber, finiteNumber]) }),
    z.object({
      type: z.literal("LineString"),
      coordinates: z.array(z.tuple([finiteNumber, finiteNumber])).min(2),
    }),
  ]),
  properties: z.looseObject({ feature_type: z.string() }),
});

export const journeyResponseSchema = z.object({
  request: z.looseObject({
    origin: z.object({ latitude: finiteNumber, longitude: finiteNumber }),
    at: awareTimestamp,
  }),
  generated_at: awareTimestamp,
  journey_status: z.enum([
    "PFZ_AVAILABLE_WITHIN_CONFIGURED_LIMITS",
    "PFZ_AVAILABLE_CAUTION",
    "PFZ_AVAILABLE_LIMIT_EXCEEDED",
    "PFZ_AVAILABLE_INSUFFICIENT_EVIDENCE",
    "NO_VALID_PFZ",
    "PFZ_REFRESH_PENDING",
    "PFZ_SOURCE_UNAVAILABLE",
    "POLICY_NOT_CONFIGURED",
  ]),
  pfz_resolution: z.object({
    status: z.enum(["PFZ_FOUND", "NO_VALID_PFZ", "PFZ_REFRESH_PENDING", "PFZ_SOURCE_UNAVAILABLE"]),
    failure: z.looseObject({
      code: z.string(),
      message: z.string(),
      retryable: z.boolean(),
      retry_after_seconds: z.number().int().positive().nullable().optional(),
      refresh_job_id: z.string().nullable().optional(),
    }).nullable().optional(),
  }),
  pfz: z.looseObject({
    nearest_pfz: nearestPfzSchema,
    valid_from: awareTimestamp,
    valid_until: awareTimestamp,
    forecast_date: z.string(),
    cache_status: z.string(),
    warnings: z.array(z.string()).default([]),
    notice: z.string().optional(),
  }).nullable(),
  origin: locationResultSchema,
  destination: locationResultSchema.nullable(),
  distance: z.object({
    kilometres: finiteNumber.nonnegative(),
    bearing_degrees: finiteNumber.min(0).max(360),
    direction: z.string(),
  }).nullable(),
  reasons: z.array(z.object({ code: z.string(), message: z.string() })),
  reason_codes: z.array(z.string()),
  notices: z.array(z.string()),
  limitations: z.object({
    route_evaluated: z.boolean(),
    geofences_evaluated: z.boolean(),
    official_warning_coverage: z.string(),
  }),
  geojson: z.object({
    type: z.literal("FeatureCollection"),
    features: z.array(featureSchema),
  }).nullable(),
});

export type JourneyRequest = z.input<typeof journeyRequestSchema>;
export type JourneyResponse = z.infer<typeof journeyResponseSchema>;
export type MarineEvidence = z.infer<typeof marineEvidenceSchema>;
export type EvidenceItem = z.infer<typeof evidenceItemSchema>;
export type SourceData = z.infer<typeof sourceDataSchema>;
