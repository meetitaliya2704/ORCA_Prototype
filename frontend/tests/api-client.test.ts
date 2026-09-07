import demo from "@/public/demo/pfz-journey.json";
import { waitForJourneyRefresh } from "@/lib/api/journey";
import { OrcaApiError, orcaFetch } from "@/lib/api/client";
import { journeyRequestSchema, journeyResponseSchema } from "@/lib/schemas/journey";

const response = (body: unknown, status = 200, headers?: HeadersInit) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

test("typed E3 success is parsed", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(response(demo));
  const result = await orcaFetch("/v1/decision-support/pfz-journey", journeyResponseSchema);
  expect(result.data.journey_status).toBe("PFZ_AVAILABLE_CAUTION");
});

test("202 response and Retry-After metadata are preserved", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(response(demo, 202, { "Retry-After": "7" }));
  const result = await orcaFetch("/v1/decision-support/pfz-journey", journeyResponseSchema);
  expect(result.status).toBe(202);
  expect(result.retryAfterSeconds).toBe(7);
});

test("polling is bounded", async () => {
  const pending = { ...demo, journey_status: "PFZ_REFRESH_PENDING", pfz_resolution: { status: "PFZ_REFRESH_PENDING", failure: { code: "PFZ_DATA_PENDING", message: "Refreshing", retryable: true, retry_after_seconds: 1, refresh_job_id: "job-safe" } }, pfz: null, destination: null, distance: null, geojson: null };
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => response(pending, 202));
  await expect(waitForJourneyRefresh(journeyRequestSchema.parse(demo.request), { maxAttempts: 3, intervalMs: 1, sleep: async () => undefined })).rejects.toMatchObject({ code: "REFRESH_POLL_LIMIT" });
  expect(fetchMock).toHaveBeenCalledTimes(3);
});

test("polling stops after success", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(response({ ...demo, journey_status: "PFZ_REFRESH_PENDING", pfz_resolution: { status: "PFZ_REFRESH_PENDING", failure: { code: "PFZ_DATA_PENDING", message: "Refreshing", retryable: true } }, pfz: null, destination: null, distance: null, geojson: null }, 202))
    .mockResolvedValueOnce(response(demo));
  const result = await waitForJourneyRefresh(journeyRequestSchema.parse(demo.request), { maxAttempts: 4, intervalMs: 1, sleep: async () => undefined });
  expect(result.data.journey_status).toBe("PFZ_AVAILABLE_CAUTION");
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("provider error text is replaced by a sanitized message", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ detail: "token at C:/private/file" }, 503));
  await expect(orcaFetch("/v1/test", journeyResponseSchema)).rejects.toMatchObject({
    message: "ORCA’s backend or a required data source is temporarily unavailable.",
  });
});

test("abort cleans up a pending request", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((_url: RequestInfo | URL, init?: RequestInit) => new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
  }));
  const controller = new AbortController();
  const request = orcaFetch("/v1/test", journeyResponseSchema, { signal: controller.signal });
  controller.abort();
  await expect(request).rejects.toBeInstanceOf(OrcaApiError);
});
