"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface AudioRecorderState {
  isRecording: boolean;
  recordingSeconds: number;
  maxSeconds: number;
  error: string | null;
  startRecording: () => Promise<boolean>;
  stopRecording: () => Promise<Blob | null>;
  cancelRecording: () => void;
  clearError: () => void;
}

const MAX_RECORDING_SECONDS = 30;

export function useAudioRecorder(maxSeconds: number = MAX_RECORDING_SECONDS): AudioRecorderState {
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const resolveStopRef = useRef<((blob: Blob | null) => void) | null>(null);

  const cleanupStream = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) {
        track.stop();
      }
      streamRef.current = null;
    }
  }, []);

  const stopRecording = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        cleanupStream();
        setIsRecording(false);
        setRecordingSeconds(0);
        resolve(null);
        return;
      }

      resolveStopRef.current = resolve;
      try {
        recorder.stop();
      } catch {
        cleanupStream();
        setIsRecording(false);
        setRecordingSeconds(0);
        resolve(null);
      }
    });
  }, [cleanupStream]);

  const cancelRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      try {
        recorder.stop();
      } catch {
        // ignore
      }
    }
    cleanupStream();
    chunksRef.current = [];
    setIsRecording(false);
    setRecordingSeconds(0);
    if (resolveStopRef.current) {
      resolveStopRef.current(null);
      resolveStopRef.current = null;
    }
  }, [cleanupStream]);

  const startRecording = useCallback(async (): Promise<boolean> => {
    setError(null);
    cancelRecording();

    if (typeof window === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setError("Microphone is not supported in this browser. Please type your query.");
      return false;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Select supported MIME type
      let mimeType = "";
      if (typeof MediaRecorder.isTypeSupported === "function") {
        if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
          mimeType = "audio/webm;codecs=opus";
        } else if (MediaRecorder.isTypeSupported("audio/webm")) {
          mimeType = "audio/webm";
        } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
          mimeType = "audio/mp4";
        } else if (MediaRecorder.isTypeSupported("audio/ogg")) {
          mimeType = "audio/ogg";
        }
      }

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      mediaRecorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        cleanupStream();
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        chunksRef.current = [];
        setIsRecording(false);
        setRecordingSeconds(0);

        if (resolveStopRef.current) {
          resolveStopRef.current(blob);
          resolveStopRef.current = null;
        }
      };

      recorder.onerror = () => {
        cleanupStream();
        setIsRecording(false);
        setRecordingSeconds(0);
        setError("Audio recording error occurred. Please try again or type your query.");
        if (resolveStopRef.current) {
          resolveStopRef.current(null);
          resolveStopRef.current = null;
        }
      };

      recorder.start(250); // collect data in 250ms chunks
      setIsRecording(true);
      setRecordingSeconds(0);

      // 30 seconds countdown timer
      let elapsed = 0;
      timerRef.current = setInterval(() => {
        elapsed += 1;
        setRecordingSeconds(elapsed);
        if (elapsed >= maxSeconds) {
          stopRecording();
        }
      }, 1000);

      return true;
    } catch (err: unknown) {
      cleanupStream();
      setIsRecording(false);
      setRecordingSeconds(0);

      const errName = (err as { name?: string })?.name;
      if (errName === "NotAllowedError" || errName === "PermissionDeniedError") {
        setError("Microphone permission denied. Please allow microphone access or type your query.");
      } else if (errName === "NotFoundError" || errName === "DevicesNotFoundError") {
        setError("No microphone found on this device. Please type your query in the text box.");
      } else {
        setError("Could not access microphone. Please type your query in the text box.");
      }
      return false;
    }
  }, [cancelRecording, cleanupStream, maxSeconds, stopRecording]);

  useEffect(() => {
    return () => {
      cancelRecording();
    };
  }, [cancelRecording]);

  const clearError = useCallback(() => setError(null), []);

  return {
    isRecording,
    recordingSeconds,
    maxSeconds,
    error,
    startRecording,
    stopRecording,
    cancelRecording,
    clearError,
  };
}

