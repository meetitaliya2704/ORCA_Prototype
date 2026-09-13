import { publicConfig } from "@/lib/config";
import { OrcaApiError } from "@/lib/api/client";
import {
  voiceTranscriptionResponseSchema,
  type VoiceTranscriptionResponse,
} from "@/lib/schemas/assistant-api";

export async function transcribeAudioQuery(
  audioBlob: Blob,
  language?: string,
): Promise<VoiceTranscriptionResponse> {
  const baseUrl = (publicConfig.apiBaseUrl || "").replace(/\/+$/, "");
  const formData = new FormData();
  const ext = audioBlob.type.includes("mp4")
    ? "mp4"
    : audioBlob.type.includes("wav")
      ? "wav"
      : "webm";
  formData.append("file", audioBlob, `voice_query.${ext}`);

  const url = new URL(`${baseUrl}/v1/assistant/transcribe`);
  if (language) {
    url.searchParams.set("language", language);
  }

  const response = await fetch(url.toString(), {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let errorDetail = "Voice transcription could not be completed.";
    let code = `HTTP_${response.status}`;
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        if (typeof errorJson.detail === "string") {
          errorDetail = errorJson.detail;
        } else if (errorJson.detail.message) {
          errorDetail = errorJson.detail.message;
          code = errorJson.detail.code ?? code;
        }
      }
    } catch {
      // ignore
    }
    throw new OrcaApiError(code, errorDetail, response.status);
  }

  const json = await response.json();
  return voiceTranscriptionResponseSchema.parse(json);
}

