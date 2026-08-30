"""Endpoint de chat con streaming SSE sobre el grafo LangGraph."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cartia_shared import ChatRequest, Citation, StreamEvent, StreamStage
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from ..core.db import SessionDep, get_engine
from ..core.deps import CurrentUser
from ..core.settings import get_settings
from ..graphs import get_graph
from ..models import Conversation, Message, MessageRole
from ..services import rag_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_NODE_STAGES: dict[str, StreamStage] = {
    "guardrails": StreamStage.GUARDRAILS,
    "rewrite": StreamStage.REWRITE,
    "retrieve": StreamStage.RETRIEVE,
    "broaden": StreamStage.RETRIEVE,
    "grade": StreamStage.GRADE,
    "generate": StreamStage.GENERATE,
}

_TITLE_MAX = 70


def _sse(event: StreamEvent) -> str:
    return f"data: {event.model_dump_json(exclude_none=True)}\n\n"


def _derive_title(text: str) -> str:
    single_line = " ".join(text.split())
    if len(single_line) <= _TITLE_MAX:
        return single_line
    return single_line[: _TITLE_MAX - 1].rstrip() + "…"


def _load_or_create_conversation(
    session: Session, user_id: UUID, conversation_id: UUID | None, first_message: str
) -> Conversation:
    if conversation_id is None:
        conversation = Conversation(user_id=user_id, title=_derive_title(first_message))
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        return conversation

    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="conversación inexistente"
        )
    return conversation


def _load_history(session: Session, conversation_id: UUID) -> list[dict[str, str]]:
    settings = get_settings()
    messages = session.exec(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())  # type: ignore[union-attr]
        .limit(settings.history_turns * 2)
    ).all()
    return [
        {"role": message.role.value, "content": message.content} for message in reversed(messages)
    ]


async def _stream(
    conversation_id: UUID,
    question: str,
    history: list[dict[str, str]],
    filters: Any,
) -> AsyncIterator[str]:
    """Traduce los eventos del grafo a eventos SSE que la UI consume."""
    graph = get_graph()
    initial_state: dict[str, Any] = {
        "question": question,
        "history": history,
        "filters": filters,
        "attempts": 0,
        "meta": {},
    }

    final_state: dict[str, Any] = {}
    streamed_any_token = False
    seen_stages: set[str] = set()

    try:
        async for event in graph.astream_events(initial_state, version="v2"):
            kind = event["event"]
            name = event.get("name", "")

            if kind == "on_chain_start" and name in _NODE_STAGES and name not in seen_stages:
                seen_stages.add(name)
                yield _sse(StreamEvent(type="stage", stage=_NODE_STAGES[name]))

            elif kind == "on_chat_model_stream":
                if event.get("metadata", {}).get("langgraph_node") != "generate":
                    continue
                chunk = event["data"].get("chunk")
                text = getattr(chunk, "content", None)
                if isinstance(text, str) and text:
                    streamed_any_token = True
                    yield _sse(StreamEvent(type="token", text=text))

            elif kind == "on_chain_end" and name == "LangGraph":
                output = event["data"].get("output")
                if isinstance(output, dict):
                    final_state = output

    except Exception as exc:
        logger.exception("el grafo falló durante el streaming")
        yield _sse(
            StreamEvent(
                type="error",
                reason="No pude completar la consulta. Reintentá en unos segundos.",
                meta={"detail": str(exc)} if get_settings().debug else None,
            )
        )
        return

    answer = (final_state.get("answer") or "").strip()
    allowed = final_state.get("allowed", True)
    citations: list[Citation] = final_state.get("citations") or []

    if not allowed:
        yield _sse(
            StreamEvent(
                type="rejected",
                reason=answer or "Consulta fuera del alcance de CartIA Legal.",
                conversation_id=conversation_id,
            )
        )
    elif not streamed_any_token and answer:
        # Caminos que no pasan por el modelo (sin contexto, RAG caído): el texto se emite
        # de una para que la UI lo trate igual que a una respuesta generada.
        yield _sse(StreamEvent(type="token", text=answer))

    if citations:
        yield _sse(StreamEvent(type="citations", citations=citations))

    message_id = _persist_turn(
        conversation_id=conversation_id,
        answer=answer,
        citations=citations,
        rejected_reason=None if allowed else answer,
    )

    yield _sse(
        StreamEvent(
            type="done",
            conversation_id=conversation_id,
            message_id=message_id,
            meta=_public_meta(final_state),
        )
    )


def _public_meta(final_state: dict[str, Any]) -> dict[str, Any]:
    meta = final_state.get("meta") or {}
    return {
        "guardrail": meta.get("guardrail"),
        "queries": meta.get("queries"),
        "retrieved": meta.get("retrieved"),
        "attempts": final_state.get("attempts"),
        "sufficient": final_state.get("sufficient"),
    }


def _persist_turn(
    *,
    conversation_id: UUID,
    answer: str,
    citations: list[Citation],
    rejected_reason: str | None,
) -> UUID:
    """Sesión propia: la del request ya se cerró cuando arranca el streaming."""
    with Session(get_engine()) as session:
        message = Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=answer,
            citations=[citation.model_dump(mode="json") for citation in citations],
            rejected_reason=rejected_reason,
        )
        session.add(message)
        conversation = session.get(Conversation, conversation_id)
        if conversation:
            conversation.updated_at = datetime.now(UTC)
            session.add(conversation)
        session.commit()
        session.refresh(message)
        return message.id


@router.post("/chat")
async def chat(payload: ChatRequest, user: CurrentUser, session: SessionDep) -> StreamingResponse:
    conversation = _load_or_create_conversation(
        session, user.id, payload.conversation_id, payload.message
    )
    history = _load_history(session, conversation.id)

    session.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=payload.message,
        )
    )
    session.commit()

    return StreamingResponse(
        _stream(conversation.id, payload.message, history, payload.filters),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Evita que un proxy intermedio (Cloud Run, nginx) buffere el stream.
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": str(conversation.id),
        },
    )


@router.get("/corpus/stats")
async def corpus_stats(user: CurrentUser) -> dict[str, Any]:
    """Proxy del estado del corpus, para que la UI sepa qué hay indexado."""
    try:
        return await rag_client.corpus_stats()
    except Exception as exc:
        logger.warning("no se pudo obtener el estado del corpus: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="el servicio de búsqueda no está disponible",
        ) from exc
