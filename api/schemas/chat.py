from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class MessageSendRequest(BaseModel):
    conversation_id: Optional[int] = None
    target_profile_id: Optional[int] = None
    body: str = Field(min_length=1, max_length=4000)
    client_id: UUID


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    sender_name: str
    is_me: bool
    body: str
    client_id: str
    created_at: str


class MessagesListResponse(BaseModel):
    conversation_id: int
    generation: int
    messages: List[MessageOut]
    has_more: bool = False


class PinnedFactRequest(BaseModel):
    source_message_id: int
    body: str = Field(min_length=1, max_length=1000)
    version: int = 1


class FactConsentRequest(BaseModel):
    version: int


class PinnedFactOut(BaseModel):
    id: int
    source_message_id: int
    author_id: int
    author_name: str
    body: str
    version: int
    my_consent: bool
    consents_count: int
    all_consented: bool
