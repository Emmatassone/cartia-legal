"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { api } from "./api";

/**
 * Dictado por voz con dos estrategias.
 *
 * 1. Web Speech API cuando el browser la expone (Chrome, Edge, Safari): transcribe en
 *    vivo, sin costo y sin latencia de red al final.
 * 2. MediaRecorder + `POST /transcribe` como fallback (Firefox, y cualquier browser donde
 *    `SpeechRecognition` falle): graba el audio y lo transcribe con Gemini al soltar.
 *
 * La decisión se toma en runtime y no en build, porque el mismo bundle corre en browsers
 * distintos. `mode` se expone para que la UI pueda avisar cuál está activa: en el modo
 * grabación no hay texto parcial y el usuario tiene que esperar al final.
 */

type VoiceMode = "live" | "recording";
type VoiceStatus = "idle" | "listening" | "transcribing";

interface SpeechRecognitionAlternative {
  transcript: string;
}
interface SpeechRecognitionResult {
  isFinal: boolean;
  0: SpeechRecognitionAlternative;
  length: number;
}
interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: { length: number; [index: number]: SpeechRecognitionResult };
}
interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: Event & { error?: string }) => void) | null;
  onend: (() => void) | null;
}
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

function getSpeechRecognition(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

interface VoiceCapabilities {
  mode: VoiceMode;
  supported: boolean;
}

// El server no puede detectar nada, así que arranca en el modo por defecto sin soporte y
// el cliente lo corrige en el primer render. El resultado se memoiza porque `getSnapshot`
// tiene que devolver siempre la misma referencia.
const SERVER_CAPABILITIES: VoiceCapabilities = { mode: "live", supported: false };
let clientCapabilities: VoiceCapabilities | null = null;

function detectCapabilities(): VoiceCapabilities {
  if (clientCapabilities) return clientCapabilities;
  const hasSpeech = getSpeechRecognition() !== null;
  const hasRecorder =
    typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
  clientCapabilities = {
    mode: hasSpeech ? "live" : "recording",
    supported: hasSpeech || hasRecorder,
  };
  return clientCapabilities;
}

// Las capacidades del browser no cambian durante la sesión: nunca hay que notificar.
const neverChanges = () => () => {};

function pickAudioMimeType(): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

interface UseVoiceInputOptions {
  /** Se llama con el texto listo para insertar en el composer. */
  onTranscript: (text: string) => void;
  /** Texto parcial mientras se dicta. Solo se emite en modo `live`. */
  onInterim?: (text: string) => void;
  onError?: (message: string) => void;
}

export function useVoiceInput({ onTranscript, onInterim, onError }: UseVoiceInputOptions) {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const { mode, supported } = useSyncExternalStore(
    neverChanges,
    detectCapabilities,
    () => SERVER_CAPABILITIES,
  );

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const finalRef = useRef("");

  const stopTracks = useCallback((stream: MediaStream) => {
    stream.getTracks().forEach((track) => track.stop());
  }, []);

  const startRecording = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = pickAudioMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    chunksRef.current = [];

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = async () => {
      stopTracks(stream);
      const blob = new Blob(chunksRef.current, { type: mimeType || "audio/webm" });
      chunksRef.current = [];
      if (blob.size < 1024) {
        setStatus("idle");
        return;
      }
      setStatus("transcribing");
      try {
        const text = await api.transcribe(blob);
        if (text.trim()) onTranscript(text.trim());
        else onError?.("No se entendió el audio. Probá de nuevo.");
      } catch (error) {
        onError?.(error instanceof Error ? error.message : "No se pudo transcribir el audio");
      } finally {
        setStatus("idle");
      }
    };

    recorderRef.current = recorder;
    recorder.start();
    setStatus("listening");
  }, [onError, onTranscript, stopTracks]);

  const startLive = useCallback(() => {
    const Recognition = getSpeechRecognition();
    if (!Recognition) return startRecording();

    const recognition = new Recognition();
    recognition.lang = "es-AR";
    recognition.continuous = true;
    recognition.interimResults = true;
    finalRef.current = "";

    recognition.onresult = (event) => {
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (result.isFinal) finalRef.current += result[0].transcript;
        else interim += result[0].transcript;
      }
      onInterim?.((finalRef.current + interim).trim());
    };
    recognition.onerror = (event) => {
      const code = (event as Event & { error?: string }).error;
      // `no-speech` y `aborted` son cancelaciones normales, no errores para el usuario.
      if (code && code !== "no-speech" && code !== "aborted") {
        onError?.(
          code === "not-allowed"
            ? "Falta permiso para usar el micrófono."
            : `El dictado falló (${code}).`,
        );
      }
      setStatus("idle");
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      const text = finalRef.current.trim();
      if (text) onTranscript(text);
      onInterim?.("");
      setStatus("idle");
    };

    recognitionRef.current = recognition;
    recognition.start();
    setStatus("listening");
    return undefined;
  }, [onError, onInterim, onTranscript, startRecording]);

  const start = useCallback(async () => {
    if (status !== "idle") return;
    try {
      if (mode === "live") await startLive();
      else await startRecording();
    } catch (error) {
      setStatus("idle");
      const denied = error instanceof DOMException && error.name === "NotAllowedError";
      onError?.(
        denied
          ? "Falta permiso para usar el micrófono."
          : "No se pudo iniciar el dictado en este navegador.",
      );
    }
  }, [mode, onError, startLive, startRecording, status]);

  const stop = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      return;
    }
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
      recorderRef.current = null;
    }
  }, []);

  const toggle = useCallback(() => {
    if (status === "idle") void start();
    else if (status === "listening") stop();
  }, [start, status, stop]);

  useEffect(
    () => () => {
      recognitionRef.current?.abort();
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    },
    [],
  );

  return { status, mode, supported, toggle, start, stop };
}
