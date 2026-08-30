"use client";

import type { StreamStage } from "@/lib/types";

const LABELS: Record<StreamStage, string> = {
  guardrails: "Verificando el alcance de la consulta",
  rewrite: "Reformulando en términos jurídicos",
  retrieve: "Buscando en el corpus",
  grade: "Evaluando la pertinencia de las fuentes",
  generate: "Redactando la respuesta",
};

export function StageIndicator({ stage }: { stage: StreamStage }) {
  return (
    <div className="flex items-center gap-2.5 text-sm text-ink-400">
      <span className="flex gap-1">
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="animate-mic h-1.5 w-1.5 rounded-full bg-brass-400"
            style={{ animationDelay: `${index * 0.18}s` }}
          />
        ))}
      </span>
      {LABELS[stage]}…
    </div>
  );
}
