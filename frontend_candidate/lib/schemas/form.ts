import { z } from "zod";
import { journeyRequestSchema, type JourneyRequest } from "./journey";

const optionalPositiveString = z.string().trim().refine(
  (value) => value === "" || (Number.isFinite(Number(value)) && Number(value) > 0),
  "Enter a number greater than zero.",
);

export const journeyFormSchema = z.object({
  latitude: z.string().trim().refine(
    (value) => Number.isFinite(Number(value)) && Number(value) >= -90 && Number(value) <= 90,
    "Enter a latitude from -90 to 90.",
  ),
  longitude: z.string().trim().refine(
    (value) => Number.isFinite(Number(value)) && Number(value) >= -180 && Number(value) <= 180,
    "Enter a longitude from -180 to 180.",
  ),
  atLocal: z.string(),
  waveLimit: optionalPositiveString,
  windLimit: optionalPositiveString,
  currentLimit: optionalPositiveString,
}).superRefine((value, context) => {
  if (![value.waveLimit, value.windLimit, value.currentLimit].some(Boolean)) {
    context.addIssue({
      code: "custom",
      path: ["waveLimit"],
      message: "Supply at least one operational limit.",
    });
  }
  if (value.atLocal && Number.isNaN(new Date(value.atLocal).getTime())) {
    context.addIssue({ code: "custom", path: ["atLocal"], message: "Enter a valid date and time." });
  }
});

export type JourneyFormValues = z.infer<typeof journeyFormSchema>;

export function formValuesToRequest(values: JourneyFormValues): JourneyRequest {
  const limit = (value: string) => value === "" ? null : Number(value);
  return journeyRequestSchema.parse({
    origin: { latitude: Number(values.latitude), longitude: Number(values.longitude) },
    at: values.atLocal ? new Date(values.atLocal).toISOString() : null,
    operational_limits: {
      maximum_significant_wave_height_m: limit(values.waveLimit),
      maximum_wind_speed_m_s: limit(values.windLimit),
      maximum_surface_current_speed_m_s: limit(values.currentLimit),
    },
    include_origin_evidence: true,
    include_destination_evidence: true,
    include_geojson: true,
  });
}
