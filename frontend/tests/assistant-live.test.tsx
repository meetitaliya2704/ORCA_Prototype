import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssistantResultPanel } from "@/components/evidence/assistant-result-panel";
import { HttpAssistantTransport } from "@/lib/assistant/transport";
import { assistantApiRequestSchema, assistantApiResponseSchema } from "@/lib/schemas/assistant-api";
import { useAssistant } from "@/hooks/use-assistant";

const responseFixture = {
  conversation_id: "11111111-1111-4111-8111-111111111111",
  user_message_id: "22222222-2222-4222-8222-222222222222",
  assistant_message_id: "33333333-3333-4333-8333-333333333333",
  run_id: "44444444-4444-4444-8444-444444444444",
  detected_intent: "marine_conditions",
  capability_status: "available",
  completion_status: "partial",
  answer: "Marine evidence was collected from the configured deterministic services. One source is degraded.",
  required_information: [],
  evidence_summary: {
    status: "partial",
    available_sources: 4,
    degraded_sources: 1,
    pending_sources: 0,
    unavailable_sources: 1,
    assessment_outcome: "CAUTION",
    evidence_confidence: "DEGRADED",
    pfz_status: null,
  },
  sources: [
    { source: "sst", state: "available", provider: "Copernicus Marine", product_id: "SST_PRODUCT", dataset_id: "SST_DATASET", valid_time: "2026-09-10T05:00:00Z", freshness: "fresh" },
    { source: "chlorophyll", state: "degraded", provider: "Copernicus Marine", product_id: "CHL_PRODUCT", dataset_id: "CHL_DATASET", valid_time: "2026-09-09T00:00:00Z", freshness: "stale" },
  ],
  warnings: [{ code: "EVIDENCE_DEGRADED", message: "Chlorophyll uncertainty is elevated.", retryable: false, retry_after_seconds: null }],
  geojson: null,
  routing_mode: "deterministic_fallback",
  model: null,
  demonstration: null,
  geofences_evaluated: false,
  generated_at: "2026-09-10T06:00:00Z",
} as const;

const context = { latitude: "20.5", longitude: "72.9", requestedTimeLocal: "", waveLimit: "", windLimit: "", currentLimit: "" };
const jsonResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

test("assistant request schema preserves decimal coordinates and rejects incomplete pairs", () => {
  expect(assistantApiRequestSchema.parse({ message: "Check conditions", latitude: 20.5, longitude: 72.9 }).latitude).toBe(20.5);
  expect(assistantApiRequestSchema.safeParse({ message: "Check conditions", latitude: 20.5 }).success).toBe(false);
});

test("live response is runtime validated and rendered as structured evidence", () => {
  const response = assistantApiResponseSchema.parse(responseFixture);
  render(<AssistantResultPanel response={response} />);
  expect(screen.getByRole("heading", { name: "Analysis Result" })).toBeInTheDocument();
  expect(screen.getByText("CAUTION")).toBeInTheDocument();
  expect(screen.getByText("DEGRADED")).toBeInTheDocument();
  expect(screen.getByText("SST_DATASET")).toBeInTheDocument();
  expect(screen.queryByText(/^Safe$/i)).not.toBeInTheDocument();
});

test("HTTP transport sends language, context and conversation continuation", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(responseFixture));
  const transport = new HttpAssistantTransport();
  const result = await transport.send({
    text: "મારા સ્થાન નજીક સમુદ્રની સ્થિતિ કેવી છે?",
    preferredLanguage: "gu",
    conversationId: responseFixture.conversation_id,
    context,
  }, new AbortController().signal);
  const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
  expect(body).toMatchObject({ preferred_language: "gu", conversation_id: responseFixture.conversation_id, latitude: 20.5, longitude: 72.9 });
  expect(result.response?.conversation_id).toBe(responseFixture.conversation_id);
  expect(result.messages[0].kind).toBe("assistant_result");
});

test("assistant hook reuses the returned conversation ID on the next turn", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(responseFixture));
  const { result } = renderHook(() => useAssistant("live", "en", context));
  await act(async () => { await result.current.send("Check marine conditions"); });
  await waitFor(() => expect(result.current.conversationId).toBe(responseFixture.conversation_id));
  await act(async () => { await result.current.send("Explain the sources"); });
  const secondBody = JSON.parse(String(fetchMock.mock.calls[1][1]?.body));
  expect(secondBody.conversation_id).toBe(responseFixture.conversation_id);
  expect(secondBody.recent_messages).toEqual(expect.arrayContaining([expect.objectContaining({ role: "user", content: "Check marine conditions" })]));
});

test("clarification response becomes structured missing-information UI", async () => {
  const clarification = {
    ...responseFixture,
    completion_status: "clarification_required",
    answer: "Please provide your location.",
    required_information: ["location"],
    evidence_summary: { ...responseFixture.evidence_summary, status: "not_collected", available_sources: 0, degraded_sources: 0, unavailable_sources: 0 },
    sources: [],
    warnings: [],
  };
  vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(clarification));
  const { result } = renderHook(() => useAssistant("live", "hi", { ...context, latitude: "", longitude: "" }));
  await act(async () => { await result.current.send("मेरे पास पीएफ़ज़ेड कहाँ है?"); });
  expect(result.current.messages.at(-1)).toMatchObject({ kind: "clarification", missing_fields: ["location"] });
});

test("503 and timeout errors stay sanitized and expose retry", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: { code: "ASSISTANT_GRAPH_TIMEOUT", message: "The assistant request timed out" } }, 503));
  const { result } = renderHook(() => useAssistant("live", "en", context));
  await act(async () => { await result.current.send("Check conditions"); });
  expect(result.current.lastError?.code).toBe("ASSISTANT_GRAPH_TIMEOUT");
  expect(result.current.messages.at(-1)?.content).toMatch(/timed out|too long|could not be displayed|coordinating/i);
  expect(result.current.messages.at(-1)).toMatchObject({ kind: "error", retryable: true });
});

test("transport cancellation aborts the browser request", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((_url, init) => new Promise((_resolve, reject) => init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")))));
  const transport = new HttpAssistantTransport();
  const pending = transport.send({ text: "Check conditions", context }, new AbortController().signal);
  transport.cancel();
  await expect(pending).rejects.toMatchObject({ code: "REQUEST_CANCELLED" });
});

test("assistant evidence never invents numeric marine values absent from the API", async () => {
  const user = userEvent.setup();
  render(<AssistantResultPanel response={assistantApiResponseSchema.parse(responseFixture)} />);
  expect(screen.getAllByText("Provider pending")).toHaveLength(4);
  expect(screen.queryByText(/safe route/i)).not.toBeInTheDocument();
  await user.tab();
  expect(document.activeElement).toBeInstanceOf(HTMLElement);
});
