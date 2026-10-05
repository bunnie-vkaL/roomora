from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from django.shortcuts import get_object_or_404
from core.models import Profile
from core import models as m
from core.services import (
    DomainError,
    conversation_for,
    pair_chat_for,
    send_message,
    send_pair_message,
)
from api.dependencies import get_current_profile
from api.schemas.chat import (
    FactConsentRequest,
    MessageOut,
    MessageSendRequest,
    MessagesListResponse,
    PinnedFactOut,
    PinnedFactRequest,
)

router = APIRouter(prefix="/chat", tags=["Chat & Messaging"])


@router.get("/{conversation_id}/messages", response_model=MessagesListResponse)
def get_messages(
    conversation_id: int,
    since_id: Optional[int] = Query(None, description="Fetch messages with ID strictly greater than since_id"),
    limit: int = Query(50, ge=1, le=100),
    actor: Profile = Depends(get_current_profile),
):
    """Poll messages for a conversation, optionally filtered by since_id."""
    try:
        conversation = conversation_for(actor, conversation_id)
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)

    qs = conversation.messages.select_related("sender").order_by("pk")
    if since_id:
        qs = qs.filter(pk__gt=since_id)

    messages_slice = list(qs[:limit])
    output = []
    for msg in messages_slice:
        output.append(
            MessageOut(
                id=msg.pk,
                conversation_id=conversation.pk,
                sender_id=msg.sender_id,
                sender_name=msg.sender.name,
                is_me=(msg.sender_id == actor.pk),
                body=msg.body,
                client_id=str(msg.client_id),
                created_at=msg.created_at.strftime("%H:%M, %d/%m"),
            )
        )

    return MessagesListResponse(
        conversation_id=conversation.pk,
        generation=conversation.generation,
        messages=output,
        has_more=len(messages_slice) == limit,
    )


@router.post("/{conversation_id}/messages", response_model=MessageOut)
def post_message(
    conversation_id: int,
    payload: MessageSendRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Send a message to an active conversation with client UUID deduplication."""
    try:
        msg = send_message(
            actor=actor,
            conversation_id=conversation_id,
            body=payload.body,
            client_id=payload.client_id,
        )
        return MessageOut(
            id=msg.pk,
            conversation_id=conversation_id,
            sender_id=msg.sender_id,
            sender_name=msg.sender.name,
            is_me=True,
            body=msg.body,
            client_id=str(msg.client_id),
            created_at=msg.created_at.strftime("%H:%M, %d/%m"),
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)


@router.post("/pair/{target_id}/messages", response_model=MessageOut)
def post_pair_message(
    target_id: int,
    payload: MessageSendRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Send a message to a pair before a mutual connection is formally confirmed."""
    target = get_object_or_404(Profile, pk=target_id)
    try:
        msg = send_pair_message(
            actor=actor,
            target=target,
            body=payload.body,
            client_id=payload.client_id,
        )
        return MessageOut(
            id=msg.pk,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            sender_name=msg.sender.name,
            is_me=True,
            body=msg.body,
            client_id=str(msg.client_id),
            created_at=msg.created_at.strftime("%H:%M, %d/%m"),
        )
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
