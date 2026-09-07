import demo from "@/public/demo/pfz-journey.json";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { useJourney } from "@/hooks/use-journey";
import { journeyRequestSchema } from "@/lib/schemas/journey";

const pending = {
  ...demo,
  journey_status: "PFZ_REFRESH_PENDING",
  pfz_resolution: {
    status: "PFZ_REFRESH_PENDING",
    failure: {
      code: "PFZ_DATA_PENDING",
      message: "PFZ data is refreshing",
      retryable: true,
      refresh_job_id: "safe-job",
    },
  },
  pfz: null,
  destination: null,
  distance: null,
  geojson: null,
};

test("pending polling is cancelled when the dashboard unmounts", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    return new Response(JSON.stringify(pending), {
      status: 202,
      headers: { "Content-Type": "application/json" },
    });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result, unmount } = renderHook(() => useJourney(), { wrapper });
  const request = journeyRequestSchema.parse(demo.request);

  act(() => { void result.current.submit(request); });
  await waitFor(() => expect(result.current.pending).toBe(true));
  const callsBeforeUnmount = fetchMock.mock.calls.length;
  unmount();
  await new Promise((resolve) => window.setTimeout(resolve, 30));
  expect(fetchMock).toHaveBeenCalledTimes(callsBeforeUnmount);
});

test("a live-shaped 200 response updates the journey result", async () => {
  const liveShape = structuredClone(demo) as unknown as Record<string, unknown>;
  const origin = liveShape.origin as Record<string, unknown>;
  const evidenceBundle = origin.evidence as Record<string, unknown>;
  const evidence = evidenceBundle.evidence as Record<string, unknown>;
  const chlorophyll = evidence.chlorophyll as Record<string, unknown>;
  const data = chlorophyll.data as Record<string, unknown>;
  data.quality = {
    flag_value: 4,
    land: false,
    interpolated: true,
    uncertainty_percent: 54,
    evidence_quality: "degraded",
  };

  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(liveShape), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result } = renderHook(() => useJourney(), { wrapper });

  await act(async () => {
    await result.current.submit(journeyRequestSchema.parse(demo.request));
  });

  expect(result.current.error).toBeNull();
  expect(result.current.result?.journey_status).toBe("PFZ_AVAILABLE_CAUTION");
});
