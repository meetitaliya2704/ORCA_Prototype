import { z } from "zod";
import { publicConfig } from "@/lib/config";

export class OrcaApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
    public readonly retryAfterSeconds?: number,
    public readonly diagnostic?: string,
  ) {
    super(message);
    this.name = "OrcaApiError";
  }
}

const errorBodySchema = z.looseObject({
  detail: z.union([
    z.string(),
    z.looseObject({
      code: z.string().optional(),
      message: z.string().optional(),
      retry_after_seconds: z.number().int().positive().optional(),
    }),
    z.array(z.unknown()),
  ]).optional(),
});

function safeError(body: unknown, status: number, retryAfter?: number) {
  const parsed = errorBodySchema.safeParse(body);
  const detail = parsed.success ? parsed.data.detail : undefined;
  if (detail && !Array.isArray(detail) && typeof detail === "object") {
    return new OrcaApiError(
      detail.code ?? `HTTP_${status}`,
      detail.message ?? "ORCA could not complete this request.",
      status,
      detail.retry_after_seconds ?? retryAfter,
      publicConfig.devDiagnostics ? `HTTP ${status}` : undefined,
    );
  }
  const message = status === 422
    ? "Check the highlighted coordinates, time, and operational limits."
    : status >= 500
      ? "ORCA’s backend or a required data source is temporarily unavailable."
      : "ORCA could not complete this request.";
  return new OrcaApiError(`HTTP_${status}`, message, status, retryAfter);
}

export async function orcaFetch<T>(
  path: string,
  schema: z.ZodType<T>,
  init: RequestInit = {},
  timeoutMs = publicConfig.requestTimeoutMs,
): Promise<{ data: T; status: number; retryAfterSeconds?: number }> {
  if (!publicConfig.apiBaseUrl) {
    throw new OrcaApiError("API_NOT_CONFIGURED", "The ORCA API address is not configured.", 0);
  }
  const timeout = new AbortController();
  const timer = window.setTimeout(() => timeout.abort("timeout"), timeoutMs);
  const externalSignal = init.signal;
  const abortExternal = () => timeout.abort(externalSignal?.reason);
  externalSignal?.addEventListener("abort", abortExternal, { once: true });
  try {
    const response = await fetch(`${publicConfig.apiBaseUrl}${path}`, {
      ...init,
      signal: timeout.signal,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
    const retryHeader = Number(response.headers.get("Retry-After"));
    const retryAfterSeconds = Number.isFinite(retryHeader) && retryHeader > 0
      ? retryHeader
      : undefined;
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok && response.status !== 202) {
      throw safeError(body, response.status, retryAfterSeconds);
    }
    const parsed = schema.safeParse(body);
    if (!parsed.success) {
      throw new OrcaApiError(
        "INVALID_ORCA_RESPONSE",
        "ORCA returned data in an unexpected format.",
        502,
        undefined,
        publicConfig.devDiagnostics ? parsed.error.message : undefined,
      );
    }
    return { data: parsed.data, status: response.status, retryAfterSeconds };
  } catch (error) {
    if (error instanceof OrcaApiError) throw error;
    if (timeout.signal.aborted) {
      const cancelled = externalSignal?.aborted;
      throw new OrcaApiError(
        cancelled ? "REQUEST_CANCELLED" : "REQUEST_TIMEOUT",
        cancelled ? "The request was cancelled." : "The request timed out. Try again.",
        0,
      );
    }
    throw new OrcaApiError("NETWORK_UNAVAILABLE", "The ORCA backend could not be reached.", 0);
  } finally {
    window.clearTimeout(timer);
    externalSignal?.removeEventListener("abort", abortExternal);
  }
}
