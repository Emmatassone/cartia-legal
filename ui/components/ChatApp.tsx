"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Menu } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, emptyMessage, streamChat } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ChatMessage, StreamStage } from "@/lib/types";
import { useAuthHydrated } from "@/lib/useHydrated";

import { AuthScreen } from "./AuthScreen";
import { Composer } from "./Composer";
import { EmptyState } from "./EmptyState";
import { Logo } from "./Logo";
import { MessageBubble } from "./MessageBubble";
import { Sidebar } from "./Sidebar";
import { StageIndicator } from "./StageIndicator";

export function ChatApp() {
  const hydrated = useAuthHydrated();
  const { accessToken, refreshToken, clear } = useAuth();
  const queryClient = useQueryClient();

  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [stage, setStage] = useState<StreamStage | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const authenticated = hydrated && !!accessToken;

  const { data: user = null } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    enabled: authenticated,
  });

  const { data: conversations = [] } = useQuery({
    queryKey: ["conversations"],
    queryFn: api.conversations,
    enabled: authenticated,
  });

  // Solo mueve el scroll; no toca estado de React, así que puede vivir en un efecto.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, stage]);

  const startNew = useCallback(() => {
    abortRef.current?.abort();
    setActiveId(null);
    setMessages([]);
    setStage(null);
    setStreaming(false);
    setError(null);
    setSidebarOpen(false);
  }, []);

  const openConversation = useCallback(
    async (id: string) => {
      setSidebarOpen(false);
      setError(null);
      setActiveId(id);
      try {
        const detail = await queryClient.fetchQuery({
          queryKey: ["conversation", id],
          queryFn: () => api.conversation(id),
        });
        setMessages(detail.messages);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "No se pudo abrir la conversación");
      }
    },
    [queryClient],
  );

  const deleteMutation = useMutation({
    mutationFn: api.deleteConversation,
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: ["conversations"] });
      if (id === activeId) startNew();
    },
    onError: (caught) =>
      setError(caught instanceof Error ? caught.message : "No se pudo eliminar la conversación"),
  });

  const logout = useCallback(async () => {
    if (refreshToken) await api.logout(refreshToken).catch(() => undefined);
    clear();
    queryClient.clear();
    setMessages([]);
    setActiveId(null);
  }, [clear, queryClient, refreshToken]);

  const send = useCallback(
    async (text: string) => {
      const userMessage = emptyMessage("user", text);
      const assistantMessage = emptyMessage("assistant");

      setError(null);
      setMessages((current) => [...current, userMessage, assistantMessage]);
      setStreaming(true);
      setStage(null);

      const controller = new AbortController();
      abortRef.current = controller;

      const patchAssistant = (patch: Partial<ChatMessage>) =>
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantMessage.id ? { ...message, ...patch } : message,
          ),
        );

      let buffer = "";
      let conversationId = activeId;

      try {
        await streamChat(
          { message: text, conversation_id: activeId },
          {
            signal: controller.signal,
            onEvent: (event) => {
              switch (event.type) {
                case "stage":
                  if (event.stage) setStage(event.stage);
                  break;
                case "token":
                  buffer += event.text ?? "";
                  patchAssistant({ content: buffer });
                  break;
                case "citations":
                  patchAssistant({ citations: event.citations ?? [] });
                  break;
                case "rejected":
                  patchAssistant({ rejected_reason: event.reason ?? "", content: "" });
                  break;
                case "error":
                  setError(event.reason ?? "Ocurrió un error al procesar la consulta");
                  break;
                case "done":
                  if (event.conversation_id) conversationId = event.conversation_id;
                  if (event.message_id) patchAssistant({ id: event.message_id });
                  break;
              }
            },
          },
        );

        if (conversationId && conversationId !== activeId) setActiveId(conversationId);
        if (conversationId) {
          void queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] });
        }
        void queryClient.invalidateQueries({ queryKey: ["conversations"] });
      } catch (caught) {
        if (controller.signal.aborted) {
          patchAssistant({ content: buffer || "_Generación detenida._" });
        } else {
          setError(caught instanceof Error ? caught.message : "No se pudo enviar la consulta");
          setMessages((current) =>
            current.filter((message) => message.id !== assistantMessage.id),
          );
        }
      } finally {
        abortRef.current = null;
        setStreaming(false);
        setStage(null);
      }
    },
    [activeId, queryClient],
  );

  if (!hydrated) return <div className="min-h-screen bg-ink-950" />;
  if (!accessToken) return <AuthScreen />;

  const lastMessage = messages[messages.length - 1];
  const lastIsStreamingAssistant = streaming && lastMessage?.role === "assistant";

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        user={user}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNew={startNew}
        onSelect={(id) => void openConversation(id)}
        onDelete={(id) => deleteMutation.mutate(id)}
        onLogout={() => void logout()}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-ink-800 px-4 py-3 md:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-label="Abrir menú"
            className="text-ink-300 hover:text-ink-100"
          >
            <Menu className="h-5 w-5" />
          </button>
          <Logo className="text-base" />
        </header>

        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <EmptyState onPick={(text) => void send(text)} />
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6">
              {messages.map((message, index) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  streaming={lastIsStreamingAssistant && index === messages.length - 1}
                />
              ))}
              {stage && <StageIndicator stage={stage} />}
              {error && (
                <p className="rounded-lg border border-red-500/25 bg-red-500/5 px-3 py-2 text-sm text-red-300">
                  {error}
                </p>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <Composer
          onSend={(text) => void send(text)}
          onStop={() => abortRef.current?.abort()}
          streaming={streaming}
        />
      </div>
    </div>
  );
}
