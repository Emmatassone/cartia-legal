from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import select

from ..core.db import SessionDep
from ..core.deps import CurrentUser
from ..models import Conversation, Message
from ..schemas.chat import ConversationDetail, ConversationOut, MessageOut

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Conversation]:
    return list(
        session.exec(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())  # type: ignore[union-attr]
            .limit(limit)
            .offset(offset)
        ).all()
    )


def _owned_conversation(session: SessionDep, user_id: UUID, conversation_id: UUID) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="conversación inexistente"
        )
    return conversation


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: UUID, user: CurrentUser, session: SessionDep) -> dict:
    conversation = _owned_conversation(session, user.id, conversation_id)
    messages = session.exec(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)  # type: ignore[arg-type]
    ).all()
    return {
        **conversation.model_dump(),
        "messages": [MessageOut.model_validate(message.model_dump()) for message in messages],
    }


@router.patch("/{conversation_id}", response_model=ConversationOut)
def rename_conversation(
    conversation_id: UUID, title: str, user: CurrentUser, session: SessionDep
) -> Conversation:
    conversation = _owned_conversation(session, user.id, conversation_id)
    conversation.title = title[:300]
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: UUID, user: CurrentUser, session: SessionDep) -> None:
    conversation = _owned_conversation(session, user.id, conversation_id)
    for message in session.exec(
        select(Message).where(Message.conversation_id == conversation_id)
    ).all():
        session.delete(message)
    session.delete(conversation)
    session.commit()
