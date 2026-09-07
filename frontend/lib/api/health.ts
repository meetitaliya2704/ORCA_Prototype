import { z } from "zod";
import { orcaFetch } from "./client";

const healthSchema = z.object({ status: z.literal("healthy"), service: z.string() });

export async function getHealth(signal?: AbortSignal) {
  return (await orcaFetch("/v1/health", healthSchema, { signal }, 5_000)).data;
}
