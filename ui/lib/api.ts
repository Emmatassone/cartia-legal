import { useAuth } from "./auth";
import type {
  ChatMessage,
  Conversation,
  ConversationDetail,
  CorpusStats,
  SearchFilters,
  StreamEvent,
  TokenPair,
  User,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) return body.detail.map((d: { msg?: string }) => d.msg).join(", ");
  } catch {
    // El cuerpo no era JSON; se cae al mensaje genérico.
  }
  return `error ${response.status}`;
}

/** Renueva el access token. Devuelve el nuevo, o null si hay que volver a loguearse. */
async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken, setTokens, clear } = useAuth.getState();
  if (!refreshToken) return null;

  const response = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    clear();
    return null;
  }
  const tokens: TokenPair = await response.json();
  setTokens(tokens);
  return tokens.access_token;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Interno: evita bucles de reintento cuando el refresh también da 401. */
  retried?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, retried, headers, ...rest } = options;
  const accessToken = useAuth.getState().accessToken;

  const response = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (response.status === 401 && !retried) {
    const renewed = await refreshAccessToken();
    if (renewed) return request<T>(path, { ...options, retried: true });
  }
  if (!response.ok) throw new ApiError(await readError(response), response.status);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  signup: (payload: {
    email: string;
    password: string;
    full_name: string;
    estudio?: string;
    matricula?: string;
  }) => request<TokenPair>("/auth/signup", { method: "POST", body: payload }),

  login: (payload: { email: string; password: string }) =>
    request<TokenPair>("/auth/login", { method: "POST", body: payload }),

  me: () => request<User>("/auth/me"),

  logout: (refresh_token: string) =>
    request<void>("/auth/logout", { method: "POST", body: { refresh_token } }),

  conversations: () => request<Conversation[]>("/conversations"),

  conversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),

  deleteConversation: (id: string) =>
    request<void>(`/conversations/${id}`, { method: "DELETE" }),

  renameConversation: (id: string, title: string) =>
    request<Conversation>(`/conversations/${id}?title=${encodeURIComponent(title)}`, {
      method: "PATCH",
    }),

  corpusStats: () => request<CorpusStats>("/corpus/stats"),

  async transcribe(audio: Blob): Promise<string> {
    const form = new FormData();
    // El nombre importa: FastAPI valida el content-type del part.
    form.append("audio", audio, `dictado.${audio.type.includes("ogg") ? "ogg" : "webm"}`);

    const send = async (token: string | null) =>
      fetch(`${API_URL}/transcribe`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });

    let response = await send(useAuth.getState().accessToken);
    if (response.status === 401) {
      const renewed = await refreshAccessToken();
      if (renewed) response = await send(renewed);
    }
    if (!response.ok) throw new ApiError(await readError(response), response.status);
    const body: { text: string } = await response.json();
    return body.text;
  },
};

export interface ChatStreamHandlers {
  onEvent: (event: StreamEvent) => void;
  signal?: AbortSignal;
}

/**
 * Consume el stream SSE de `POST /chat`.
 *
 * No se usa `EventSource` porque solo soporta GET y no permite enviar el header de
 * autorización; se lee el body del `fetch` a mano y se parsea el protocolo SSE.
 */
export async function streamChat(
  payload: { message: string; conversation_id?: string | null; filters?: SearchFilters | null },
  { onEvent, signal }: ChatStreamHandlers,
): Promise<void> {
  const send = async (token: string | null) =>
    fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        message: payload.message,
        conversation_id: payload.conversation_id ?? null,
        filters: payload.filters ?? null,
      }),
      signal,
    });

  let response = await send(useAuth.getState().accessToken);
  if (response.status === 401) {
    const renewed = await refreshAccessToken();
    if (renewed) response = await send(renewed);
  }
  if (!response.ok || !response.body) {
    throw new ApiError(await readError(response), response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Los eventos SSE se separan con una línea en blanco.
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const dataLine = frame
        .split("\n")
        .find((line) => line.startsWith("data:"));
      if (dataLine) {
        try {
          onEvent(JSON.parse(dataLine.slice(5).trim()) as StreamEvent);
        } catch {
          // Un frame corrupto no debe cortar el stream completo.
        }
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}

export function emptyMessage(role: ChatMessage["role"], content = ""): ChatMessage {
  return {
    id: `local-${crypto.randomUUID()}`,
    role,
    content,
    citations: [],
    rejected_reason: null,
    created_at: new Date().toISOString(),
  };
}
