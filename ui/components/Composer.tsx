"use client";

import { ArrowUp, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useVoiceInput } from "@/lib/useVoiceInput";

import { MicButton } from "./MicButton";

interface ComposerProps {
  onSend: (message: string) => void;
  onStop: () => void;
  streaming: boolean;
}

const MAX_ROWS_PX = 200;

export function Composer({ onSend, onStop, streaming }: ComposerProps) {
  const [value, setValue] = useState("");
  const [interim, setInterim] = useState("");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const appendTranscript = useCallback((text: string) => {
    setInterim("");
    setValue((current) => (current ? `${current.trimEnd()} ${text}` : text));
    textareaRef.current?.focus();
  }, []);

  const voice = useVoiceInput({
    onTranscript: appendTranscript,
    onInterim: setInterim,
    onError: setVoiceError,
  });

  // Autosize: el textarea crece con el contenido hasta un techo y después scrollea.
  useEffect(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_ROWS_PX)}px`;
  }, [value, interim]);

  const toggleVoice = () => {
    setVoiceError(null);
    voice.toggle();
  };

  const submit = () => {
    const message = value.trim();
    if (!message || streaming) return;
    if (voice.status === "listening") voice.stop();
    onSend(message);
    setValue("");
    setInterim("");
  };

  const displayed = interim ? (value ? `${value.trimEnd()} ${interim}` : interim) : value;
  const canSend = displayed.trim().length > 0 && !streaming;

  return (
    <div className="border-t border-ink-800 bg-ink-950/80 px-4 pb-4 pt-3 backdrop-blur">
      <div className="mx-auto max-w-3xl">
        {voiceError && (
          <p className="mb-2 text-xs text-amber-400" role="alert">
            {voiceError}
          </p>
        )}
        {voice.status === "listening" && voice.mode === "recording" && (
          <p className="mb-2 text-xs text-ink-400">
            Grabando. Este navegador no soporta dictado en vivo: el texto aparece al detener.
          </p>
        )}

        <div className="flex items-end gap-2 rounded-2xl border border-ink-700 bg-ink-900 px-3 py-2 focus-within:border-ink-500">
          <MicButton
            status={voice.status}
            mode={voice.mode}
            supported={voice.supported}
            disabled={streaming}
            onToggle={toggleVoice}
          />

          <textarea
            ref={textareaRef}
            value={displayed}
            onChange={(event) => {
              setInterim("");
              setValue(event.target.value);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            rows={1}
            placeholder="Consultá sobre normativa, jurisprudencia o procedimiento argentino…"
            aria-label="Consulta"
            className="max-h-[200px] flex-1 resize-none bg-transparent py-1.5 text-[0.94rem] leading-relaxed text-ink-100 placeholder:text-ink-500 focus:outline-none"
          />

          {streaming ? (
            <button
              type="button"
              onClick={onStop}
              title="Detener la generación"
              aria-label="Detener la generación"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink-700 text-ink-100 transition hover:bg-ink-600"
            >
              <Square className="h-3.5 w-3.5 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={submit}
              disabled={!canSend}
              title="Enviar"
              aria-label="Enviar consulta"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brass-500 text-ink-950 transition hover:bg-brass-400 disabled:bg-ink-800 disabled:text-ink-600"
            >
              <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
            </button>
          )}
        </div>

        <p className="mt-2 text-center text-[11px] leading-relaxed text-ink-600">
          CartIA responde sobre derecho argentino y cita las fuentes del corpus indexado.
          Verificá la vigencia de las normas antes de usarlas en un escrito.
        </p>
      </div>
    </div>
  );
}
