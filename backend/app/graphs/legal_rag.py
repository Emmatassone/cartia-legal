"""Grafo LangGraph del workflow RAG legal.

    START
      v
  guardrails ──(no legal)──> reject ──> END
      │
      v
   rewrite  (consulta coloquial -> consultas de busqueda tecnicas)
      │
      v
  retrieve  <──────────────┐   (llama al servicio RAG, fusiona multi-query)
      │                    │
      v                    │
    grade ──(insuficiente)─┘  broaden: suelta filtros y amplia el top_k
      │
      v
  generate ──> END          (respuesta con citas numeradas)

El guardrail es deliberadamente el primer nodo: rechazar antes de reescribir, buscar y
generar evita gastar embeddings y tokens del modelo grande en consultas fuera de alcance,
y deja registrado el motivo del rechazo.
"""

from __future__ import annotations

import asyncio
import logging
import re
from functools import lru_cache
from typing import Any, Literal

from cartia_shared import Citation, NormaEstado, RetrievedChunk, SearchFilters
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from ..core.settings import get_settings
from ..services import rag_client
from ..services.gemini import answer_model, grader_model, guardrail_model, rewrite_model
from . import prompts
from .state import LegalRAGState

logger = logging.getLogger(__name__)

# Patrones de intento de override de instrucciones. Se chequean antes del LLM: es una
# defensa deterministica que no depende de que el modelo "se acuerde" de resistirlos.
_INJECTION_PATTERNS = [
    r"ignor[aá]\s+(?:todas\s+)?(?:las\s+)?instrucciones",
    r"olvid[aá]\s+(?:todo|tus\s+instrucciones|lo\s+anterior)",
    r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions",
    r"\bdisregard\s+(?:all\s+)?(?:previous\s+)?instructions",
    r"system\s*prompt",
    r"\bprompt\s+del\s+sistema\b",
    r"\bDAN\b\s+mode",
    r"actu[aá]\s+como\s+(?:si\s+fueras\s+)?(?:un[a]?\s+)?(?:\w+\s+)?sin\s+(?:restricciones|filtros|l[ií]mites)",  # noqa: E501
    r"\bjailbreak\b",
    r"revel[aá]\s+(?:tus\s+|las\s+)?instrucciones",
]

_REJECTION_INJECTION = (
    "No puedo procesar consultas que intenten modificar mis instrucciones de "
    "funcionamiento. Escribime directamente tu consulta de derecho argentino."
)


class GuardrailVerdict(BaseModel):
    allowed: bool = Field(description="True si la consulta corresponde al ámbito legal argentino")
    reason: str = Field(
        default="",
        description="Mensaje para el usuario cuando allowed es False. Vacío cuando es True.",
    )


class SearchQueries(BaseModel):
    queries: list[str] = Field(description="Entre 1 y 3 consultas de búsqueda autocontenidas")


class ContextGrade(BaseModel):
    sufficient: bool = Field(description="True si los fragmentos alcanzan para fundar la respuesta")
    missing: str = Field(default="", description="Qué información falta. Vacío si sufficient.")


def _history_block(state: LegalRAGState) -> str:
    history = state.get("history") or []
    if not history:
        return ""
    turns = history[-get_settings().history_turns :]
    rendered = "\n".join(
        f"{'Abogado' if turn['role'] == 'user' else 'CartIA'}: {turn['content']}" for turn in turns
    )
    return f"Historial de la conversación:\n{rendered}\n\n"


def _format_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for marker, chunk in enumerate(chunks, start=1):
        reference = chunk.citation or chunk.title
        if chunk.articulo:
            reference = f"{reference}, art. {chunk.articulo}"
        header = f"[{marker}] {reference}"
        if chunk.heading:
            header = f"{header} ({chunk.heading})"
        if chunk.estado == NormaEstado.PARCIALMENTE_VIGENTE:
            # El modelo tiene que saberlo para avisar que partes pueden no regir.
            header = f"{header} [VIGENCIA PARCIAL: la norma tiene derogaciones parciales]"
        blocks.append(f"{header}\n{chunk.content}")
    return "\n\n---\n\n".join(blocks)


# --------------------------------------------------------------------------- nodos


async def guardrails_node(state: LegalRAGState) -> dict[str, Any]:
    question = state["question"]

    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, question, flags=re.IGNORECASE):
            logger.warning("guardrail: intento de override de instrucciones bloqueado")
            return {
                "allowed": False,
                "rejection_reason": _REJECTION_INJECTION,
                "meta": {**state.get("meta", {}), "guardrail": "injection"},
            }

    context_note = (
        "Esta consulta continúa una conversación jurídica ya iniciada, así que un mensaje "
        "breve o con referencias implícitas puede ser un seguimiento legítimo."
        if state.get("history")
        else ""
    )
    messages = [
        SystemMessage(content=prompts.GUARDRAIL_SYSTEM),
        HumanMessage(
            content=prompts.GUARDRAIL_USER.format(question=question, context_note=context_note)
        ),
    ]

    try:
        verdict: GuardrailVerdict = (
            await guardrail_model().with_structured_output(GuardrailVerdict).ainvoke(messages)
        )
    except Exception:
        # Fail-open acotado: si el clasificador se cae, dejamos pasar la consulta. El peor
        # caso es una respuesta fuera de alcance; el caso contrario seria dejar el producto
        # inutilizable ante una falla transitoria de la API.
        logger.exception("guardrail: el clasificador falló, se admite la consulta por defecto")
        return {"allowed": True, "meta": {**state.get("meta", {}), "guardrail": "error"}}

    if not verdict.allowed:
        logger.info("guardrail: consulta rechazada. %s", verdict.reason)
        reason = verdict.reason.strip() or (
            "Esta consulta no corresponde al ámbito del derecho argentino, que es el único "
            "alcance de CartIA Legal."
        )
        return {
            "allowed": False,
            "rejection_reason": reason,
            "meta": {**state.get("meta", {}), "guardrail": "rejected"},
        }
    return {"allowed": True, "meta": {**state.get("meta", {}), "guardrail": "allowed"}}


async def reject_node(state: LegalRAGState) -> dict[str, Any]:
    return {"answer": state.get("rejection_reason", ""), "citations": [], "chunks": []}


async def rewrite_node(state: LegalRAGState) -> dict[str, Any]:
    question = state["question"]
    messages = [
        SystemMessage(content=prompts.REWRITE_SYSTEM),
        HumanMessage(
            content=prompts.REWRITE_USER.format(
                history_block=_history_block(state), question=question
            )
        ),
    ]
    try:
        result: SearchQueries = (
            await rewrite_model().with_structured_output(SearchQueries).ainvoke(messages)
        )
        queries = [query.strip() for query in result.queries if query.strip()][:3]
    except Exception:
        logger.exception("rewrite: falló la reescritura, se usa la consulta original")
        queries = []

    if not queries:
        queries = [question]
    logger.info("rewrite: %s consultas -> %s", len(queries), queries)
    return {"search_queries": queries, "attempts": state.get("attempts", 0)}


def _with_estado_default(filters: SearchFilters | None) -> SearchFilters | None:
    """Filtro de sistema: no recuperar normas derogadas salvo que el usuario lo pida.

    Aplica tambien en el reintento (broaden): soltar los filtros del usuario no es
    razon para empezar a citar normas que ya no rigen.
    """
    settings = get_settings()
    if not settings.retrieval_excluir_derogadas:
        return filters
    if filters is not None and filters.estados:
        return filters
    base = filters.model_dump() if filters else {}
    base["estados"] = [NormaEstado.VIGENTE, NormaEstado.PARCIALMENTE_VIGENTE]
    return SearchFilters(**base)


async def retrieve_node(state: LegalRAGState) -> dict[str, Any]:
    settings = get_settings()
    queries = state.get("search_queries") or [state["question"]]
    attempts = state.get("attempts", 0)
    # En el segundo intento se amplia el pool: ya sabemos que el primero no alcanzo.
    top_k = settings.retrieval_top_k * (2 if attempts else 1)
    filters = _with_estado_default(None if attempts else state.get("filters"))

    try:
        responses = await asyncio.gather(
            *(rag_client.search(query, top_k=top_k, filters=filters) for query in queries)
        )
    except rag_client.RagUnavailableError as exc:
        logger.error("retrieve: %s", exc)
        return {
            "chunks": [],
            "attempts": attempts + 1,
            "meta": {**state.get("meta", {}), "rag_error": str(exc)},
        }

    # Fusion multi-query: un chunk que aparece para varias consultas es mas relevante, pero
    # basta con quedarse con su mejor score para no sesgar hacia consultas redundantes.
    best: dict[Any, RetrievedChunk] = {}
    for response in responses:
        for chunk in response.chunks:
            current = best.get(chunk.chunk_id)
            if current is None or chunk.score > current.score:
                best[chunk.chunk_id] = chunk

    chunks = sorted(best.values(), key=lambda chunk: chunk.score, reverse=True)[
        : settings.retrieval_top_k
    ]
    logger.info("retrieve: %s chunks unicos, se conservan %s", len(best), len(chunks))
    return {
        "chunks": chunks,
        "attempts": attempts + 1,
        "meta": {
            **state.get("meta", {}),
            "retrieved": len(best),
            "queries": queries,
        },
    }


async def grade_node(state: LegalRAGState) -> dict[str, Any]:
    chunks = state.get("chunks") or []
    if not chunks:
        return {"sufficient": False, "missing": "no se recuperó ningún fragmento"}

    messages = [
        SystemMessage(content=prompts.GRADE_SYSTEM),
        HumanMessage(
            content=prompts.GRADE_USER.format(
                question=state["question"],
                # Se grada sobre un recorte: alcanza para juzgar pertinencia y abarata la llamada.
                context=_format_context(chunks)[:12000],
            )
        ),
    ]
    try:
        grade: ContextGrade = (
            await grader_model().with_structured_output(ContextGrade).ainvoke(messages)
        )
    except Exception:
        logger.exception("grade: el evaluador falló, se asume contexto suficiente")
        return {"sufficient": True, "missing": ""}

    logger.info("grade: sufficient=%s missing=%r", grade.sufficient, grade.missing)
    return {"sufficient": grade.sufficient, "missing": grade.missing}


async def broaden_node(state: LegalRAGState) -> dict[str, Any]:
    """Segundo intento: consulta original + lo que el grader marco como faltante, sin filtros."""
    missing = (state.get("missing") or "").strip()
    queries = [state["question"]]
    if missing:
        queries.append(f"{state['question']} {missing}")
    logger.info("broaden: reintento de retrieval sin filtros")
    return {"search_queries": queries, "filters": None}


def _build_citations(chunks: list[RetrievedChunk], answer: str) -> list[Citation]:
    """Devuelve solo las fuentes efectivamente citadas, conservando su numeración."""
    used = {int(marker) for marker in re.findall(r"\[(\d{1,2})\]", answer)}
    citations: list[Citation] = []
    for marker, chunk in enumerate(chunks, start=1):
        if used and marker not in used:
            continue
        citations.append(
            Citation(
                marker=marker,
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                title=chunk.title,
                citation=chunk.citation,
                articulo=chunk.articulo,
                estado=chunk.estado,
                snippet=chunk.content[:600],
                score=chunk.score,
            )
        )
    return citations


async def generate_node(state: LegalRAGState) -> dict[str, Any]:
    chunks = state.get("chunks") or []
    meta = state.get("meta", {})

    if meta.get("rag_error"):
        return {
            "answer": (
                "No pude consultar el corpus jurídico en este momento porque el servicio de "
                "búsqueda no está respondiendo. Reintentá en unos segundos."
            ),
            "citations": [],
        }
    if not chunks:
        return {"answer": prompts.NO_CONTEXT_ANSWER, "citations": []}

    system = prompts.ANSWER_SYSTEM
    if not state.get("sufficient", True):
        system = f"{system}\n\n{prompts.INSUFFICIENT_CONTEXT_NOTE}"

    messages = [
        SystemMessage(content=system),
        HumanMessage(
            content=prompts.ANSWER_USER.format(
                history_block=_history_block(state),
                question=state["question"],
                context=_format_context(chunks),
            )
        ),
    ]

    # `astream` en lugar de `ainvoke` para que `astream_events` emita los tokens y la UI
    # los pueda mostrar a medida que se generan.
    parts: list[str] = []
    async for piece in answer_model().astream(messages):
        text = piece.content
        if isinstance(text, str) and text:
            parts.append(text)
    answer = "".join(parts).strip()

    return {"answer": answer, "citations": _build_citations(chunks, answer)}


# --------------------------------------------------------------------------- ruteo


def route_after_guardrails(state: LegalRAGState) -> Literal["reject", "rewrite"]:
    return "rewrite" if state.get("allowed") else "reject"


def route_after_grade(state: LegalRAGState) -> Literal["broaden", "generate"]:
    if state.get("sufficient"):
        return "generate"
    if state.get("attempts", 0) >= get_settings().retrieval_max_attempts:
        # Se responde igual, pero el prompt le avisa al modelo que el contexto es debil.
        return "generate"
    if state.get("meta", {}).get("rag_error"):
        return "generate"
    return "broaden"


def build_graph():
    graph = StateGraph(LegalRAGState)
    graph.add_node("guardrails", guardrails_node)
    graph.add_node("reject", reject_node)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("grade", grade_node)
    graph.add_node("broaden", broaden_node)
    graph.add_node("generate", generate_node)

    graph.add_edge(START, "guardrails")
    graph.add_conditional_edges(
        "guardrails", route_after_guardrails, {"reject": "reject", "rewrite": "rewrite"}
    )
    graph.add_edge("reject", END)
    graph.add_edge("rewrite", "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges(
        "grade", route_after_grade, {"broaden": "broaden", "generate": "generate"}
    )
    graph.add_edge("broaden", "retrieve")
    graph.add_edge("generate", END)
    return graph.compile()


@lru_cache
def get_graph():
    return build_graph()
