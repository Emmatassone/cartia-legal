"use client";

import { ChevronDown, FileText } from "lucide-react";
import { useState } from "react";

import type { Citation } from "@/lib/types";

function CitationRow({ citation }: { citation: Citation }) {
  const [open, setOpen] = useState(false);
  const heading = citation.citation ?? citation.title;

  return (
    <li className="rounded-lg border border-ink-800 bg-ink-900/60">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition hover:bg-ink-800/50"
      >
        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded bg-brass-500/15 text-[11px] font-semibold text-brass-300">
          {citation.marker}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm text-ink-100">{heading}</span>
          <span className="mt-0.5 block text-xs text-ink-400">
            {citation.articulo ? `art. ${citation.articulo} · ` : ""}
            relevancia {citation.score.toFixed(3)}
          </span>
        </span>
        {citation.estado === "derogada" && (
          <span className="mt-0.5 shrink-0 rounded bg-red-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-300">
            derogada
          </span>
        )}
        {citation.estado === "parcialmente_vigente" && (
          <span className="mt-0.5 shrink-0 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300">
            vig. parcial
          </span>
        )}
        <ChevronDown
          className={`mt-0.5 h-4 w-4 shrink-0 text-ink-500 transition ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <p className="border-t border-ink-800 px-3 py-2.5 text-xs leading-relaxed text-ink-300 whitespace-pre-wrap">
          {citation.snippet}
        </p>
      )}
    </li>
  );
}

export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;

  return (
    <div className="mt-4">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-ink-500">
        <FileText className="h-3.5 w-3.5" />
        Fuentes citadas
      </p>
      <ul className="flex flex-col gap-1.5">
        {citations.map((citation) => (
          <CitationRow key={citation.chunk_id} citation={citation} />
        ))}
      </ul>
    </div>
  );
}
