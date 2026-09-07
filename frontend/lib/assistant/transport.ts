import type { AssistantMessage, DemonstrationConversation } from "@/lib/schemas/assistant";

export type AssistantRequest = { text: string; actionId?: string };

export interface AssistantTransport {
  send(request: AssistantRequest, signal: AbortSignal): Promise<AssistantMessage[]>;
  cancel(): void;
}

export class DisabledAssistantTransport implements AssistantTransport {
  async send(_request: AssistantRequest, signal: AbortSignal): Promise<AssistantMessage[]> {
    if (signal.aborted) throw new DOMException("Request cancelled", "AbortError");
    return [{
      id: `disabled-${Date.now()}`,
      kind: "system_notice",
      role: "system",
      mode: "deterministic",
      content: "Conversational agent connection is not enabled. You can continue using ORCA’s deterministic journey tools.",
      created_at: new Date().toISOString(),
      evidence_references: [], warnings: [], suggested_actions: ["find_pfz"],
    }];
  }
  cancel() {}
}

export class DemoAssistantTransport implements AssistantTransport {
  private controller: AbortController | null = null;
  constructor(private readonly fixture: DemonstrationConversation) {}

  async send(request: AssistantRequest, signal: AbortSignal): Promise<AssistantMessage[]> {
    this.controller?.abort();
    this.controller = new AbortController();
    if (signal.aborted) throw new DOMException("Request cancelled", "AbortError");
    await Promise.resolve();
    if (signal.aborted || this.controller.signal.aborted) throw new DOMException("Request cancelled", "AbortError");
    const normalized = request.text.trim().toLowerCase();
    const matching = this.fixture.messages.filter((message) =>
      message.kind === "assistant_demo" && message.suggested_actions.some((action) => action === request.actionId || normalized.includes(action.replaceAll("_", " "))),
    );
    return matching.length > 0 ? matching : [this.fixture.messages.find((message) => message.kind === "assistant_demo")!];
  }
  cancel() { this.controller?.abort(); }
}
