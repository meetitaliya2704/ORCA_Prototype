import demo from "@/public/demo/pfz-journey.json";
import { assertGeoJsonCoordinateOrder } from "@/lib/geojson/journey";
import { formValuesToRequest, journeyFormSchema } from "@/lib/schemas/form";
import { journeyRequestSchema, journeyResponseSchema } from "@/lib/schemas/journey";

const validForm = {
  latitude: "20.5", longitude: "72.9", atLocal: "2026-09-04T12:00",
  waveLimit: "2", windLimit: "", currentLimit: "",
};

test("decimal coordinates are accepted", () => {
  expect(journeyFormSchema.parse(validForm).latitude).toBe("20.5");
});

test.each([["91", "72"], ["20", "181"], ["NaN", "72"], ["20", "Infinity"]])(
  "invalid coordinates are rejected: %s %s", (latitude, longitude) => {
    expect(journeyFormSchema.safeParse({ ...validForm, latitude, longitude }).success).toBe(false);
  },
);

test("local date-time is serialized as a timezone-aware timestamp", () => {
  const request = formValuesToRequest(validForm);
  expect(request.at).toMatch(/(?:Z|[+-]\d\d:\d\d)$/);
  expect(journeyRequestSchema.safeParse(request).success).toBe(true);
});

test.each(["0", "-1", "NaN", "Infinity"])("invalid operational limit %s is rejected", (waveLimit) => {
  expect(journeyFormSchema.safeParse({ ...validForm, waveLimit }).success).toBe(false);
});

test("at least one limit is required", () => {
  expect(journeyFormSchema.safeParse({ ...validForm, waveLimit: "" }).success).toBe(false);
});

test("runtime schema accepts the saved sanitized E3 fixture", () => {
  expect(journeyResponseSchema.safeParse(demo).success).toBe(true);
});

test("runtime schema accepts the live chlorophyll quality object", () => {
  const liveShape = structuredClone(demo) as unknown as Record<string, unknown>;
  const origin = liveShape.origin as Record<string, unknown>;
  const evidenceBundle = origin.evidence as Record<string, unknown>;
  const evidence = evidenceBundle.evidence as Record<string, unknown>;
  const chlorophyll = evidence.chlorophyll as Record<string, unknown>;
  const data = chlorophyll.data as Record<string, unknown>;
  data.chlorophyll_a = { value: 1.12, unit: "mg/m³" };
  data.analysis_time = "2026-08-26T00:00:00Z";
  data.quality = {
    flag_value: 4,
    land: false,
    interpolated: true,
    uncertainty_percent: 54,
    evidence_quality: "degraded",
  };

  expect(journeyResponseSchema.safeParse(liveShape).success).toBe(true);
});

test("runtime schema rejects malformed E3 data", () => {
  expect(journeyResponseSchema.safeParse({ ...demo, journey_status: "SAFE" }).success).toBe(false);
});

test("GeoJSON coordinates retain longitude latitude order", () => {
  const result = journeyResponseSchema.parse(demo);
  expect(assertGeoJsonCoordinateOrder(result)).toBe(true);
  expect(result.geojson?.features[0].geometry.coordinates).toEqual([72.9, 20.5]);
});

test("reversed invalid GeoJSON coordinates are detected", () => {
  const result = journeyResponseSchema.parse(demo);
  const changed = structuredClone(result);
  changed.geojson!.features[0].geometry.coordinates = [20.5, 190] as [number, number];
  expect(assertGeoJsonCoordinateOrder(changed)).toBe(false);
});
