"use client";

import { LogOut, MessageSquarePlus, Trash2, X } from "lucide-react";

import type { Conversation, User } from "@/lib/types";

import { Logo } from "./Logo";

interface SidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  user: User | null | undefined;
  open: boolean;
  onClose: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onLogout: () => void;
}

export function Sidebar({
  conversations,
  activeId,
  user,
  open,
  onClose,
  onNew,
  onSelect,
  onDelete,
  onLogout,
}: SidebarProps) {
  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-20 bg-black/60 md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-72 flex-col border-r border-ink-800 bg-ink-900 transition-transform md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 py-4">
          <Logo className="text-lg" />
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar menú"
            className="text-ink-400 hover:text-ink-100 md:hidden"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-3">
          <button
            type="button"
            onClick={onNew}
            className="flex w-full items-center gap-2 rounded-lg border border-ink-700 px-3 py-2 text-sm text-ink-100 transition hover:border-ink-500 hover:bg-ink-800"
          >
            <MessageSquarePlus className="h-4 w-4 text-brass-400" />
            Nueva consulta
          </button>
        </div>

        <nav className="mt-4 flex-1 overflow-y-auto px-3 pb-3">
          {conversations.length === 0 ? (
            <p className="px-1 py-3 text-xs leading-relaxed text-ink-500">
              Todavía no hay consultas. Empezá una nueva y va a aparecer acá.
            </p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {conversations.map((conversation) => {
                const active = conversation.id === activeId;
                return (
                  <li key={conversation.id} className="group relative">
                    <button
                      type="button"
                      onClick={() => onSelect(conversation.id)}
                      className={`w-full truncate rounded-lg py-2 pl-3 pr-9 text-left text-sm transition ${
                        active
                          ? "bg-ink-800 text-ink-50"
                          : "text-ink-300 hover:bg-ink-800/60 hover:text-ink-100"
                      }`}
                    >
                      {conversation.title}
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onDelete(conversation.id);
                      }}
                      aria-label={`Eliminar ${conversation.title}`}
                      className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1.5 text-ink-500 opacity-0 transition hover:text-red-400 focus:opacity-100 group-hover:opacity-100"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </nav>

        <div className="border-t border-ink-800 px-4 py-3">
          <p className="truncate text-sm text-ink-100">{user?.full_name ?? "—"}</p>
          <p className="truncate text-xs text-ink-500">{user?.estudio ?? user?.email ?? ""}</p>
          <button
            type="button"
            onClick={onLogout}
            className="mt-2.5 flex items-center gap-1.5 text-xs text-ink-400 transition hover:text-ink-100"
          >
            <LogOut className="h-3.5 w-3.5" />
            Cerrar sesión
          </button>
        </div>
      </aside>
    </>
  );
}
