from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from .user import utcnow


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    title: str = Field(default="Nueva consulta", max_length=300)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    conversation_id: UUID = Field(foreign_key="conversations.id", index=True)
    role: MessageRole
    content: str
    # Citas devueltas por el grafo, serializadas como recibidas del RAG.
    citations: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    # Motivo cuando el guardrail rechaza la consulta; queda registrado para auditoria.
    rejected_reason: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
