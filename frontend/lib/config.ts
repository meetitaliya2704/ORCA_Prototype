const integerSetting = (value: string | undefined, fallback: number) => {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
};

const developmentApiDefault =
  process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "";

const assistantMode = assistantModeSchema.catch("live").parse(process.env.NEXT_PUBLIC_ORCA_ASSISTANT_MODE ?? "live");

export const publicConfig = {
  apiBaseUrl:
    process.env.NEXT_PUBLIC_ORCA_API_BASE_URL?.replace(/\/$/, "") ??
    developmentApiDefault,
  mapStyleUrl: process.env.NEXT_PUBLIC_MAP_STYLE_URL ?? "",
  demoMode: process.env.NEXT_PUBLIC_ORCA_DEMO_MODE === "true",
  assistantMode,
  presentationMode: process.env.NEXT_PUBLIC_ORCA_PRESENTATION_MODE === "true",
  requestTimeoutMs: integerSetting(
    process.env.NEXT_PUBLIC_ORCA_REQUEST_TIMEOUT_MS,
    90_000,
  ),
  pollIntervalMs: integerSetting(
    process.env.NEXT_PUBLIC_ORCA_POLL_INTERVAL_MS,
    5_000,
  ),
  pollMaxAttempts: integerSetting(
    process.env.NEXT_PUBLIC_ORCA_POLL_MAX_ATTEMPTS,
    12,
  ),
  devDiagnostics:
    process.env.NODE_ENV === "development" &&
    process.env.NEXT_PUBLIC_ORCA_DEV_DIAGNOSTICS === "true",
} as const;
import { assistantModeSchema } from "@/lib/schemas/assistant";
