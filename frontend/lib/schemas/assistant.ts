import { z } from "zod";
import { journeyResponseSchema } from "@/lib/schemas/journey";

export const assistantModeSchema = z.enum(["disabled", "demo"]);
export const activityStatusSchema = z.enum(["waiting", "running", "complete", "partial", "unavailable"]);
export const evidenceSourceSchema = z.enum(["pfz", "sst", "chlorophyll", "waves", "wind", "currents", "sea_level"]);

export const evidenceReferenceSchema = z.object({
  source: evidenceSourceSchema,
  label: z.string().min(1),
  state: z.enum(["available", "degraded", "pending", "unavailable", "not_requested"]),
  valid_time: z.string().datetime({ offset: true }).nullable().optional(),
  freshness: z.string().nullable().optional(),
  location: z.enum(["origin", "destination"]).optional(),
});

export const toolActivityStepSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  status: activityStatusSchema,
  detail: z.string().min(1).optional(),
});

const common = {
  id: z.string().min(1),
  content: z.string().min(1),
  created_at: z.string().datetime({ offset: true }),
  evidence_references: z.array(evidenceReferenceSchema).default([]),
  warnings: z.array(z.string()).default([]),
  suggested_actions: z.array(z.string()).default([]),
};

export const assistantMessageSchema = z.discriminatedUnion("kind", [
  z.object({ ...common, kind: z.literal("user"), role: z.literal("user"), mode: z.enum(["deterministic", "demonstration"]) }),
  z.object({ ...common, kind: z.literal("assistant_demo"), role: z.literal("assistant"), mode: z.literal("demonstration"), tool_activity: z.array(toolActivityStepSchema).default([]) }),
  z.object({ ...common, kind: z.literal("deterministic_result"), role: z.literal("assistant"), mode: z.literal("deterministic"), journey_result: journeyResponseSchema, tool_activity: z.array(toolActivityStepSchema).default([]) }),
  z.object({ ...common, kind: z.literal("clarification"), role: z.literal("assistant"), mode: z.enum(["deterministic", "demonstration"]), missing_fields: z.array(z.enum(["location", "operational_limits", "requested_time"])).default([]) }),
  z.object({ ...common, kind: z.literal("tool_activity"), role: z.literal("system"), mode: z.enum(["deterministic", "demonstration"]), tool_activity: z.array(toolActivityStepSchema).min(1) }),
  z.object({ ...common, kind: z.literal("warning"), role: z.literal("system"), mode: z.enum(["deterministic", "demonstration"]) }),
  z.object({ ...common, kind: z.literal("error"), role: z.literal("system"), mode: z.enum(["deterministic", "demonstration"]) }),
  z.object({ ...common, kind: z.literal("system_notice"), role: z.literal("system"), mode: z.enum(["deterministic", "demonstration"]) }),
]);

export const demonstrationConversationSchema = z.object({
  label: z.literal("Demonstration Conversation"),
  original_data_timestamp: z.string().datetime({ offset: true }),
  demonstration_created_at: z.string().datetime({ offset: true }),
  source_fixture: z.literal("pfz-journey.json"),
  messages: z.array(assistantMessageSchema).min(1),
});

export type AssistantMode = z.infer<typeof assistantModeSchema>;
export type AssistantMessage = z.infer<typeof assistantMessageSchema>;
export type EvidenceReference = z.infer<typeof evidenceReferenceSchema>;
export type ToolActivityStep = z.infer<typeof toolActivityStepSchema>;
export type DemonstrationConversation = z.infer<typeof demonstrationConversationSchema>;
