import { orcaFetch, OrcaApiError } from "./client";
import { journeyRequestSchema, journeyResponseSchema, type JourneyRequest } from "@/lib/schemas/journey";

export async function postJourney(request: JourneyRequest, signal?: AbortSignal) {
  const payload = journeyRequestSchema.parse(request);
  return orcaFetch("/v1/decision-support/pfz-journey", journeyResponseSchema, {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function waitForJourneyRefresh(
  request: JourneyRequest,
  options: {
    signal?: AbortSignal;
    maxAttempts: number;
    intervalMs: number;
    initialRetryAfterSeconds?: number;
    sleep?: (milliseconds: number, signal?: AbortSignal) => Promise<void>;
  },
): Promise<Awaited<ReturnType<typeof postJourney>>> {
  const sleep = options.sleep ?? ((milliseconds, signal) => new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, milliseconds);
    signal?.addEventListener("abort", () => {
      window.clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
  }));
  let delay = options.initialRetryAfterSeconds
    ? options.initialRetryAfterSeconds * 1000
    : options.intervalMs;
  for (let attempt = 0; attempt < options.maxAttempts; attempt += 1) {
    await sleep(delay, options.signal);
    const result = await postJourney(request, options.signal);
    if (result.status !== 202) return result;
    delay = result.data.pfz_resolution.failure?.retry_after_seconds
      ? result.data.pfz_resolution.failure.retry_after_seconds * 1000
      : result.retryAfterSeconds
        ? result.retryAfterSeconds * 1000
      : options.intervalMs;
  }
  throw new OrcaApiError("REFRESH_POLL_LIMIT", "The refresh is taking longer than expected.", 202);
}
