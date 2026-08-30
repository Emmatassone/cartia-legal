"use client";

import { Loader2, Mic, Square } from "lucide-react";

interface MicButtonProps {
  status: "idle" | "listening" | "transcribing";
  mode: "live" | "recording";
  supported: boolean;
  disabled?: boolean;
  onToggle: () => void;
}

export function MicButton({ status, mode, supported, disabled, onToggle }: MicButtonProps) {
  if (!supported) return null;

  const label =
    status === "listening"
      ? "Detener dictado"
      : status === "transcribing"
        ? "Transcribiendo…"
        : mode === "live"
          ? "Dictar la consulta"
          : "Grabar la consulta (se transcribe al finalizar)";

  const base =
    "flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition " +
    "focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400 disabled:opacity-40";

  if (status === "transcribing") {
    return (
      <span className={`${base} bg-ink-800 text-brass-300`} title={label} aria-label={label}>
        <Loader2 className="h-4 w-4 animate-spin" />
      </span>
    );
  }

  const listening = status === "listening";

  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      title={label}
      aria-label={label}
      aria-pressed={listening}
      className={`${base} ${
        listening
          ? "bg-red-500/90 text-white hover:bg-red-500"
          : "bg-ink-800 text-ink-300 hover:bg-ink-700 hover:text-ink-100"
      }`}
    >
      {listening ? (
        <Square className="animate-mic h-3.5 w-3.5 fill-current" />
      ) : (
        <Mic className="h-4 w-4" />
      )}
    </button>
  );
}
