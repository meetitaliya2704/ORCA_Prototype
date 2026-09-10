import conversation from "@/public/demo/conversation.json";
import journeyFixture from "@/public/demo/pfz-journey.json";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AskOrcaPanel } from "@/components/conversation/ask-orca-panel";
import { DemoAssistantTransport, DisabledAssistantTransport } from "@/lib/assistant/transport";
import { assistantMessageSchema, demonstrationConversationSchema } from "@/lib/schemas/assistant";
import { journeyResponseSchema } from "@/lib/schemas/journey";

const fixture = demonstrationConversationSchema.parse(conversation);
const journey = journeyResponseSchema.parse(journeyFixture);
const defaults = {
  mode: "demo" as const, presentationMode: false, messages: fixture.messages, busy: false, fixtureError: false,
  onSend: vi.fn(), onCancel: vi.fn(), onReset: vi.fn(), onLoadDemo: vi.fn(), onQuickAction: vi.fn(),
  onEvidenceSelect: vi.fn(), onResultSelect: vi.fn(),
  context: { latitude: "", longitude: "", requestedTimeLocal: "", waveLimit: "", windLimit: "", currentLimit: "" },
  contextOpen: false, onContextChange: vi.fn(), onContextOpenChange: vi.fn(),
};

test("demonstration fixture and every discriminated message validate at runtime", () => {
  expect(fixture.label).toBe("Demonstration Conversation");
  expect(fixture.original_data_timestamp).toBe(journey.generated_at);
  for (const message of fixture.messages) expect(assistantMessageSchema.safeParse(message).success).toBe(true);
});

test("disabled transport truthfully declines conversational generation", async () => {
  const messages = await new DisabledAssistantTransport().send({ text: "hello" }, new AbortController().signal);
  expect(messages.messages[0].content).toMatch(/initializing/i);
  expect(messages.messages[0].kind).toBe("system_notice");
});

test("demo transport replays saved fixture content and can be cancelled", async () => {
  const transport = new DemoAssistantTransport(fixture);
  const replay = await transport.send({ text: "Why is the evidence degraded?", actionId: "explain_degraded" }, new AbortController().signal);
  expect(replay.messages[0].kind).toBe("assistant_demo");
  const pending = transport.send({ text: "another" }, new AbortController().signal);
  transport.cancel();
  await expect(pending).rejects.toMatchObject({ name: "AbortError" });
});

test("assistant panel renders clean header and activity trace", () => {
  render(<AskOrcaPanel {...defaults} presentationMode />);
  expect(screen.getByText("Ask ORCA")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Processing activity" })).toBeInTheDocument();
  expect(screen.queryByText(/live agents/i)).not.toBeInTheDocument();
});

test("suggested PFZ action and advanced control are keyboard-operable", async () => {
  const user = userEvent.setup();
  const onQuickAction = vi.fn();
  render(<AskOrcaPanel {...defaults} messages={[]} onQuickAction={onQuickAction} />);
  expect(screen.getByRole("button", { name: /Suggested questions/i })).toHaveAttribute("aria-expanded", "true");
  await user.click(screen.getByRole("button", { name: /Find nearest PFZ advisory/ }));
  expect(onQuickAction).toHaveBeenCalledWith("find_pfz", "Find nearest PFZ advisory");
  expect(screen.getByRole("button", { name: /Suggested questions/i })).toHaveAttribute("aria-expanded", "false");
  await user.tab();
  expect(document.activeElement).toBeInstanceOf(HTMLElement);
});

test("existing messages receive the main viewport while suggestions remain available on demand", async () => {
  const user = userEvent.setup();
  const message = assistantMessageSchema.parse({
    id: "notice", kind: "system_notice", role: "system", mode: "deterministic",
    content: "Conversational agent connection is not enabled.", created_at: new Date().toISOString(),
    evidence_references: [], warnings: [], suggested_actions: [],
  });
  render(<AskOrcaPanel {...defaults} mode="disabled" messages={[message]} />);

  const history = screen.getByRole("log", { name: "ORCA conversation" });
  expect(history).toHaveClass("min-h-0", "flex-1", "overflow-y-auto");
  expect(screen.getByText("Conversational agent connection is not enabled.")).toBeVisible();
  expect(screen.getByRole("button", { name: /Suggested questions/i })).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("button", { name: /Find nearest PFZ advisory/ })).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /Suggested questions/i }));
  expect(screen.getByRole("button", { name: /Find nearest PFZ advisory/ })).toBeVisible();
});

test("message composer submits with Enter and exposes cancellation while busy", async () => {
  const user = userEvent.setup();
  const onSend = vi.fn();
  const { rerender } = render(<AskOrcaPanel {...defaults} messages={[]} mode="disabled" onSend={onSend} />);
  await user.type(screen.getByLabelText("Message Ask ORCA"), "Explain sources{enter}");
  expect(onSend).toHaveBeenCalledWith("Explain sources");
  rerender(<AskOrcaPanel {...defaults} messages={[]} busy onSend={onSend} />);
  expect(screen.getByRole("button", { name: "Cancel assistant request" })).toBeInTheDocument();
});

test("evidence chip selection links conversation to structured evidence", async () => {
  const user = userEvent.setup();
  const onEvidenceSelect = vi.fn();
  render(<AskOrcaPanel {...defaults} onEvidenceSelect={onEvidenceSelect} />);
  await user.click(screen.getByRole("button", { name: /Copernicus chlorophyll/i }));
  expect(onEvidenceSelect).toHaveBeenCalledWith(expect.objectContaining({ source: "chlorophyll", state: "degraded" }));
});

test("deterministic result message uses controlled wording and restores map state", async () => {
  const user = userEvent.setup();
  const message = assistantMessageSchema.parse({
    id: "result", kind: "deterministic_result", role: "assistant", mode: "deterministic",
    content: "Deterministic ORCA result: PFZ AVAILABLE WITHIN CONFIGURED LIMITS.", created_at: journey.generated_at,
    journey_result: { ...journey, journey_status: "PFZ_AVAILABLE_WITHIN_CONFIGURED_LIMITS" },
    tool_activity: [], evidence_references: [], warnings: [], suggested_actions: [],
  });
  const onResultSelect = vi.fn();
  render(<AskOrcaPanel {...defaults} mode="disabled" messages={[message]} onResultSelect={onResultSelect} />);
  expect(screen.getByText("ORCA")).toBeInTheDocument();
  expect(screen.getByText(/WITHIN CONFIGURED LIMITS/)).toBeInTheDocument();
  expect(screen.queryByText(/safe route/i)).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Restore this result on map" }));
  expect(onResultSelect).toHaveBeenCalledWith(expect.objectContaining({ generated_at: journey.generated_at }));
});

test("source explanation control operates normally", async () => {
  const user = userEvent.setup();
  render(<AskOrcaPanel {...defaults} messages={[]} />);
  await user.click(screen.getByRole("button", { name: /Explain evidence sources/ }));
  expect(defaults.onQuickAction).toHaveBeenCalledWith("explain_sources", expect.any(String));
});
