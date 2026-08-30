// Espejo de los DTOs de `shared/cartia_shared`. Si cambian allá, hay que actualizarlos acá.

export type DocumentType =
  | "ley"
  | "decreto"
  | "resolucion"
  | "codigo"
  | "constitucion"
  | "fallo"
  | "dictamen"
  | "doctrina"
  | "contrato"
  | "escrito"
  | "convenio_colectivo"
  | "otro";

export type StreamStage = "guardrails" | "rewrite" | "retrieve" | "grade" | "generate";

export type NormaEstado = "vigente" | "parcialmente_vigente" | "derogada";

export interface Citation {
  marker: number;
  document_id: string;
  chunk_id: string;
  title: string;
  citation: string | null;
  articulo: string | null;
  estado?: NormaEstado | null;
  snippet: string;
  score: number;
}

export interface StreamEvent {
  type: "stage" | "token" | "citations" | "rejected" | "done" | "error";
  stage?: StreamStage;
  text?: string;
  citations?: Citation[];
  conversation_id?: string;
  message_id?: string;
  reason?: string;
  meta?: Record<string, unknown> | null;
}

export interface SearchFilters {
  doc_types?: DocumentType[];
  jurisdictions?: string[];
  fueros?: string[];
  anio_desde?: number;
  anio_hasta?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  rejected_reason: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  estudio: string | null;
  matricula: string | null;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface CorpusStats {
  documents: number;
  chunks: number;
  chunks_sin_embedding: number;
  by_doc_type: Record<string, number>;
  by_jurisdiction: Record<string, number>;
}
