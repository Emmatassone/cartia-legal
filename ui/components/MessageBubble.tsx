"use client";

import { ShieldAlert } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ChatMessage } from "@/lib/types";

import { CitationList } from "./CitationList";

interface MessageBubbleProps {
  message: ChatMessage;
  streaming?: boolean;
}

export function MessageBubble({ message, streaming }: MessageBubbleProps) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-ink-800 px-4 py-2.5 text-[0.94rem] leading-relaxed text-ink-50 whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.rejected_reason) {
    return (
      <div className="flex gap-3 rounded-xl border border-amber-500/25 bg-amber-500/5 px-4 py-3">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-amber-400">
            Consulta fuera de alcance
          </p>
          <p className="mt-1 text-[0.94rem] leading-relaxed text-ink-200">
            {message.rejected_reason}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className={`prose-legal text-[0.94rem] text-ink-200 ${streaming ? "streaming-caret" : ""}`}>
        <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
      </div>
      <CitationList citations={message.citations} />
    </div>
  );
}
