"use client";

import { useMutation } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { postJourney, waitForJourneyRefresh } from "@/lib/api/journey";
import { OrcaApiError } from "@/lib/api/client";
import { publicConfig } from "@/lib/config";
import type { JourneyRequest, JourneyResponse } from "@/lib/schemas/journey";

export type JourneyMode = "live" | "demonstration";

export function useJourney() {
  const controller = useRef<AbortController | null>(null);
  const lastRequest = useRef<JourneyRequest | null>(null);
  const [result, setResult] = useState<JourneyResponse | null>(null);
  const [mode, setMode] = useState<JourneyMode>("live");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<OrcaApiError | null>(null);

  const mutation = useMutation({ mutationFn: ({ request, signal }: { request: JourneyRequest; signal: AbortSignal }) => postJourney(request, signal) });

  const submit = useCallback(async (request: JourneyRequest) => {
    controller.current?.abort();
    const active = new AbortController();
    controller.current = active;
    lastRequest.current = request;
    setMode("live");
    setError(null);
    setPending(false);
    try {
      const response = await mutation.mutateAsync({ request, signal: active.signal });
      setResult(response.data);
      if (response.status !== 202) return response.data;
      setPending(true);
      const failure = response.data.pfz_resolution.failure;
      const refreshed = await waitForJourneyRefresh(request, {
        signal: active.signal,
        maxAttempts: publicConfig.pollMaxAttempts,
        intervalMs: publicConfig.pollIntervalMs,
        initialRetryAfterSeconds: failure?.retry_after_seconds ?? response.retryAfterSeconds,
      });
      setResult(refreshed.data);
      setPending(false);
      return refreshed.data;
    } catch (caught) {
      if (caught instanceof OrcaApiError && caught.code === "REQUEST_CANCELLED") return null;
      setError(caught instanceof OrcaApiError ? caught : new OrcaApiError("UNEXPECTED_ERROR", "An unexpected frontend error occurred.", 0));
      setPending(false);
      return null;
    }
  }, [mutation]);

  const loadDemo = useCallback(async () => {
    controller.current?.abort();
    setError(null);
    try {
      const response = await fetch("/demo/pfz-journey.json");
      const { journeyResponseSchema } = await import("@/lib/schemas/journey");
      const parsed = journeyResponseSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("invalid fixture");
      setResult(parsed.data);
      setMode("demonstration");
      setPending(false);
      return parsed.data;
    } catch {
      setError(new OrcaApiError("DEMO_UNAVAILABLE", "The demonstration snapshot could not be loaded.", 0));
      return null;
    }
  }, []);

  const reset = useCallback(() => {
    controller.current?.abort();
    lastRequest.current = null;
    setResult(null);
    setMode("live");
    setPending(false);
    setError(null);
    mutation.reset();
  }, [mutation]);

  useEffect(() => () => controller.current?.abort(), []);

  return {
    result,
    mode,
    pending,
    error,
    isSubmitting: mutation.isPending,
    submit,
    retry: () => lastRequest.current && submit(lastRequest.current),
    cancel: () => controller.current?.abort(),
    loadDemo,
    reset,
  };
}
