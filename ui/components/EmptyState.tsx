"use client";

import { Logo } from "./Logo";

const EJEMPLOS = [
  "¿Qué indemnizaciones corresponden en un despido sin justa causa según el art. 245 LCT?",
  "Plazo y requisitos para interponer un recurso extraordinario federal ante la CSJN.",
  "Diferencias entre la responsabilidad objetiva del art. 1757 CCyC y la subjetiva del 1749.",
  "Requisitos de la Ley 27.401 para un programa de integridad en una PyME.",
];

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 py-16 text-center">
      <Logo className="text-3xl" />
      <p className="mt-4 max-w-md text-sm leading-relaxed text-ink-400">
        Consultá sobre derecho argentino. Cada respuesta se funda en el corpus indexado y cita
        las fuentes que la respaldan.
      </p>

      <div className="mt-8 grid w-full gap-2 sm:grid-cols-2">
        {EJEMPLOS.map((ejemplo) => (
          <button
            key={ejemplo}
            type="button"
            onClick={() => onPick(ejemplo)}
            className="rounded-xl border border-ink-800 bg-ink-900/50 px-4 py-3 text-left text-[0.84rem] leading-relaxed text-ink-300 transition hover:border-ink-600 hover:bg-ink-800/60 hover:text-ink-100"
          >
            {ejemplo}
          </button>
        ))}
      </div>
    </div>
  );
}
