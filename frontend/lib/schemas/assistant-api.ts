import { z } from "zod";
import { operationalLimitsSchema } from "./journey";

const finiteNumber = z.number().finite();
const awareTimestamp = z.string().datetime({ offset: true });

export const assistantLanguageSchema = z.enum(["en", "hi", "gu", "mr", "ta", "te", "ml", "bn"]);
export const assistantApiModeSchema = z.enum(["live", "demonstration"]);

export const assistantIntentSchema = z.enum([
  "nearest_pfz",
  "operational_conditions",
  "marine_conditions",
  "official_alerts",
  "habitat_screening",
  "lower_risk_route",
  "productivity_analysis",
  "avoidance_zones",
  "source_explanation",
  "clarification_required",
  "unsupported",
]);

export const requiredInformationSchema = z.enum([
  "location",
  "requested_time",
  "operational_limits",
]);

export const assistantConversationMessageSchema = z.object({
  role: z.enum(["user", "assistant"]),
  content: z.string().min(1).max(4000),
});

export const assistantApiRequestSchema = z.object({
  conversation_id: z.string().uuid().nullable().optional(),
  message: z.string().trim().min(1).max(4000),
  preferred_language: assistantLanguageSchema.default("en"),
  latitude: finiteNumber.min(-90).max(90).nullable().optional(),
  longitude: finiteNumber.min(-180).max(180).nullable().optional(),
  requested_time: awareTimestamp.nullable().optional(),
  operational_limits: operationalLimitsSchema.default({}),
  mode: assistantApiModeSchema.default("live"),
  recent_messages: z.array(assistantConversationMessageSchema).max(20).default([]),
}).superRefine((value, context) => {
  if ((value.latitude == null) !== (value.longitude == null)) {
    context.addIssue({
      code: "custom",
      path: [value.latitude == null ? "latitude" : "longitude"],
      message: "Latitude and longitude must be supplied together.",
    });
  }
});

const assistantSourceSchema = z.object({
  source: z.enum(["pfz", "sst", "chlorophyll", "waves", "wind", "currents", "sea_level"]),
  state: z.enum(["available", "degraded", "pending", "unavailable"]),
  provider: z.string().max(200).nullable().optional(),
  product_id: z.string().max(300).nullable().optional(),
  dataset_id: z.string().max(300).nullable().optional(),
  valid_time: awareTimestamp.nullable().optional(),
  freshness: z.string().max(64).nullable().optional(),
});

const assistantWarningSchema = z.object({
  code: z.string().regex(/^[A-Z][A-Z0-9_]{0,99}$/),
  message: z.string().min(1).max(500),
  retryable: z.boolean().default(false),
  retry_after_seconds: z.number().int().positive().max(3600).nullable().optional(),
});

const pointGeometrySchema = z.object({
  type: z.literal("Point"),
  coordinates: z.tuple([finiteNumber.min(-180).max(180), finiteNumber.min(-90).max(90)]),
});

const lineGeometrySchema = z.object({
  type: z.literal("LineString"),
  coordinates: z.array(z.tuple([finiteNumber.min(-180).max(180), finiteNumber.min(-90).max(90)])).min(2),
});

export const assistantGeoJsonFeatureSchema = z.object({
  type: z.literal("Feature"),
  geometry: z.union([pointGeometrySchema, lineGeometrySchema]),
  properties: z.record(z.string(), z.unknown()),
});

export const assistantGeoJsonSchema = z.union([
  assistantGeoJsonFeatureSchema,
  z.object({
    type: z.literal("FeatureCollection"),
    features: z.array(assistantGeoJsonFeatureSchema),
  }),
]);

export const assistantApiResponseSchema = z.object({
  conversation_id: z.string().uuid(),
  user_message_id: z.string().uuid(),
  assistant_message_id: z.string().uuid(),
  run_id: z.string().uuid(),
  detected_intent: assistantIntentSchema,
  capability_status: z.enum(["available", "planned_or_partial", "planned", "not_applicable"]),
  completion_status: z.enum(["completed", "partial", "clarification_required", "capability_not_available", "failed"]),
  answer: z.string().min(1).max(4000),
  required_information: z.array(requiredInformationSchema).default([]),
  evidence_summary: z.object({
    status: z.enum(["complete", "partial", "unavailable", "not_collected"]),
    available_sources: z.number().int().min(0).max(7),
    degraded_sources: z.number().int().min(0).max(7),
    pending_sources: z.number().int().min(0).max(7),
    unavailable_sources: z.number().int().min(0).max(7),
    assessment_outcome: z.enum([
      "WITHIN_CONFIGURED_LIMITS",
      "CAUTION",
      "LIMIT_EXCEEDED",
      "INSUFFICIENT_EVIDENCE",
      "POLICY_NOT_CONFIGURED",
    ]).nullable().optional(),
    evidence_confidence: z.enum(["NORMAL", "DEGRADED", "INSUFFICIENT"]).nullable().optional(),
    pfz_status: z.enum(["PFZ_FOUND", "NO_VALID_PFZ", "PFZ_REFRESH_PENDING", "PFZ_SOURCE_UNAVAILABLE"]).nullable().optional(),
  }),
  sources: z.array(assistantSourceSchema).default([]),
  warnings: z.array(assistantWarningSchema).default([]),
  geojson: assistantGeoJsonSchema.nullable().optional(),
  routing_mode: z.enum(["gemini_function_call", "deterministic_fallback", "demonstration_fixture"]),
  model: z.string().max(100).nullable().optional(),
  demonstration: z.object({
    label: z.literal("Demonstration Snapshot"),
    original_retrieval_time: awareTimestamp,
    created_at: awareTimestamp,
  }).nullable().optional(),
  geofences_evaluated: z.literal(false),
  generated_at: awareTimestamp,
});

export const assistantContextValuesSchema = z.object({
  latitude: z.string(),
  longitude: z.string(),
  requestedTimeLocal: z.string(),
  waveLimit: z.string(),
  windLimit: z.string(),
  currentLimit: z.string(),
}).superRefine((value, context) => {
  const coordinate = (field: "latitude" | "longitude", minimum: number, maximum: number) => {
    const raw = value[field].trim();
    if (!raw) return;
    const parsed = Number(raw);
    if (!Number.isFinite(parsed) || parsed < minimum || parsed > maximum) {
      context.addIssue({ code: "custom", path: [field], message: `Enter a value from ${minimum} to ${maximum}.` });
    }
  };
  coordinate("latitude", -90, 90);
  coordinate("longitude", -180, 180);
  if (Boolean(value.latitude.trim()) !== Boolean(value.longitude.trim())) {
    context.addIssue({ code: "custom", path: [value.latitude.trim() ? "longitude" : "latitude"], message: "Supply both latitude and longitude." });
  }
  for (const field of ["waveLimit", "windLimit", "currentLimit"] as const) {
    const raw = value[field].trim();
    if (raw && (!Number.isFinite(Number(raw)) || Number(raw) <= 0)) {
      context.addIssue({ code: "custom", path: [field], message: "Enter a number greater than zero." });
    }
  }
  if (value.requestedTimeLocal && Number.isNaN(new Date(value.requestedTimeLocal).getTime())) {
    context.addIssue({ code: "custom", path: ["requestedTimeLocal"], message: "Enter a valid date and time." });
  }
});

export type AssistantLanguage = z.infer<typeof assistantLanguageSchema>;
export type AssistantApiMode = z.infer<typeof assistantApiModeSchema>;
export type AssistantApiRequest = z.infer<typeof assistantApiRequestSchema>;
export type AssistantApiResponse = z.infer<typeof assistantApiResponseSchema>;
export type AssistantSourceSummary = z.infer<typeof assistantSourceSchema>;
export type AssistantContextValues = z.infer<typeof assistantContextValuesSchema>;

export function contextValuesToApiFields(values: AssistantContextValues) {
  const parsed = assistantContextValuesSchema.parse(values);
  const numberOrNull = (value: string) => value.trim() ? Number(value) : null;
  return {
    latitude: numberOrNull(parsed.latitude),
    longitude: numberOrNull(parsed.longitude),
    requested_time: parsed.requestedTimeLocal ? new Date(parsed.requestedTimeLocal).toISOString() : null,
    operational_limits: {
      maximum_significant_wave_height_m: numberOrNull(parsed.waveLimit),
      maximum_wind_speed_m_s: numberOrNull(parsed.windLimit),
      maximum_surface_current_speed_m_s: numberOrNull(parsed.currentLimit),
    },
  };
}
