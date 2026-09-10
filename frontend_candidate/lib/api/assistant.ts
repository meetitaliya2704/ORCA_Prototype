import { orcaFetch } from "./client";
import {
  assistantApiRequestSchema,
  assistantApiResponseSchema,
  type AssistantApiRequest,
} from "@/lib/schemas/assistant-api";

export async function postAssistantQuery(request: AssistantApiRequest, signal?: AbortSignal) {
  const payload = assistantApiRequestSchema.parse(request);
  return orcaFetch(
    "/v1/assistant/query",
    assistantApiResponseSchema,
    { method: "POST", body: JSON.stringify(payload), signal },
  );
}
