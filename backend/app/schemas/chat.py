from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    citations: list[dict[str, Any]]
    rejected_reason: str | None
    created_at: datetime


class ConversationOut(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]
