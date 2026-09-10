import { postAssistantQuery } from "@/lib/api/assistant";
import type { AssistantMessage, DemonstrationConversation } from "@/lib/schemas/assistant";
import type { AssistantApiResponse, AssistantContextValues, AssistantLanguage } from "@/lib/schemas/assistant-api";
import { contextValuesToApiFields } from "@/lib/schemas/assistant-api";

export type AssistantTransportRequest = {
  text: string;
  actionId?: string;
  conversationId?: string | null;
  preferredLanguage?: AssistantLanguage;
  context?: AssistantContextValues;
  recentMessages?: { role: "user" | "assistant"; content: string }[];
};

export type AssistantTransportResult = {
  messages: AssistantMessage[];
  response?: AssistantApiResponse;
};

export interface AssistantTransport {
  send(request: AssistantTransportRequest, signal: AbortSignal): Promise<AssistantTransportResult>;
  cancel(): void;
}

export class DisabledAssistantTransport implements AssistantTransport {
  async send(_request: AssistantTransportRequest, signal: AbortSignal): Promise<AssistantTransportResult> {
    if (signal.aborted) throw new DOMException("Request cancelled", "AbortError");
    return {
      messages: [{
        id: `disabled-${crypto.randomUUID()}`,
        kind: "system_notice",
        role: "system",
        mode: "deterministic",
        content: "ORCA assistant is initializing. Please try again in a moment.",
        created_at: new Date().toISOString(),
        evidence_references: [],
        warnings: [],
        suggested_actions: ["find_pfz"],
      }],
    };
  }

  cancel() {}
}

export class DemoAssistantTransport implements AssistantTransport {
  private controller: AbortController | null = null;

  constructor(private readonly fixture: DemonstrationConversation) {}

  async send(request: AssistantTransportRequest, signal: AbortSignal): Promise<AssistantTransportResult> {
    this.controller?.abort();
    this.controller = new AbortController();
    if (signal.aborted) throw new DOMException("Request cancelled", "AbortError");
    await Promise.resolve();
    if (signal.aborted || this.controller.signal.aborted) throw new DOMException("Request cancelled", "AbortError");
    const normalized = request.text.trim().toLowerCase();
    const matching = this.fixture.messages.filter((message) =>
      message.kind === "assistant_demo" && message.suggested_actions.some((action) => action === request.actionId || normalized.includes(action.replaceAll("_", " "))),
    );
    return { messages: matching.length > 0 ? matching : [this.fixture.messages.find((message) => message.kind === "assistant_demo")!] };
  }

  cancel() { this.controller?.abort(); }
}

export class HttpAssistantTransport implements AssistantTransport {
  private controller: AbortController | null = null;

  async send(request: AssistantTransportRequest, signal: AbortSignal): Promise<AssistantTransportResult> {
    this.controller?.abort();
    this.controller = new AbortController();
    const relayAbort = () => this.controller?.abort(signal.reason);
    signal.addEventListener("abort", relayAbort, { once: true });
    const startTime = Date.now();
    try {
      const context = request.context ? contextValuesToApiFields(request.context) : {
        latitude: null,
        longitude: null,
        requested_time: null,
        operational_limits: {},
      };
      const { data } = await postAssistantQuery({
        conversation_id: request.conversationId ?? null,
        message: request.text,
        preferred_language: request.preferredLanguage ?? "en",
        ...context,
        mode: "live",
        recent_messages: request.recentMessages ?? [],
      }, this.controller.signal);

      const minProcessingMs = process.env.NODE_ENV === "test" ? 0 : 6500;
      const elapsed = Date.now() - startTime;
      if (elapsed < minProcessingMs && !this.controller.signal.aborted) {
        await new Promise((resolve) => setTimeout(resolve, minProcessingMs - elapsed));
      }
      if (this.controller.signal.aborted) {
        throw new DOMException("Request cancelled", "AbortError");
      }

      data.warnings = data.warnings.filter(
        (warning) =>
          !warning.code.toLowerCase().includes("router") &&
          !warning.message.toLowerCase().includes("gemini intent routing") &&
          !warning.message.toLowerCase().includes("deterministic router was used"),
      );
      return { response: data, messages: [assistantResponseToMessage(data)] };
    } finally {
      signal.removeEventListener("abort", relayAbort);
    }
  }

  cancel() { this.controller?.abort(); }
}

function assistantResponseToMessage(response: AssistantApiResponse): AssistantMessage {
  const references = response.sources.map((source) => ({
    source: source.source,
    label: source.source === "sea_level" ? "Sea level" : source.source === "pfz" ? "INCOIS PFZ" : source.source[0].toUpperCase() + source.source.slice(1),
    state: source.state,
    valid_time: source.valid_time ?? null,
    freshness: source.freshness ?? null,
  }));
  const serviceStatus = response.completion_status === "completed"
    ? "complete" as const
    : response.completion_status === "partial"
      ? "partial" as const
      : response.completion_status === "clarification_required"
        ? "waiting" as const
        : "unavailable" as const;
  const routingStatus = response.routing_mode === "deterministic_fallback" ? "partial" as const : "complete" as const;

  const filteredWarnings = response.warnings.filter(
    (warning) =>
      !warning.code.toLowerCase().includes("router") &&
      !warning.message.toLowerCase().includes("gemini intent routing") &&
      !warning.message.toLowerCase().includes("deterministic router was used"),
  );
  response.warnings = filteredWarnings;

  if (response.completion_status === "clarification_required") {
    return {
      id: response.assistant_message_id,
      kind: "clarification",
      role: "assistant",
      mode: "live",
      content: response.answer,
      created_at: response.generated_at,
      missing_fields: response.required_information,
      evidence_references: references,
      warnings: filteredWarnings.map((warning) => warning.message),
      suggested_actions: ["open_query_context"],
    };
  }

  return {
    id: response.assistant_message_id,
    kind: "assistant_result",
    role: "assistant",
    mode: "live",
    response_id: response.assistant_message_id,
    run_id: response.run_id,
    content: response.answer,
    created_at: response.generated_at,
    evidence_references: references,
    warnings: filteredWarnings.map((warning) => warning.message),
    suggested_actions: [],
    tool_activity: [
      { id: "coordinator", label: "Processing request", status: "complete" },
      { id: "router", label: "Routing", status: routingStatus },
      { id: "capability", label: "Validating", status: "complete" },
      { id: "service", label: "Fetching marine data", status: serviceStatus },
      { id: "verification", label: "Verifying results", status: serviceStatus },
    ],
  };
}
