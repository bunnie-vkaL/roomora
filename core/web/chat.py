"""Conversation inbox and chat views."""

import uuid

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from core.models import Connection, SearchWorkspace, SwipeDecision, recommendable_profiles
from core.scoring import score_profiles
from core.services import DomainError, blocked_profile_ids, checkpoint, conversation_for, pair_chat_for, workspace_for
from core.web.common import number, page, profile_by_id

# ==============================================================================
# S-CHAT Communication Views
# ==============================================================================

@page
def hub(request):
    actor = request.actor
    conversations = []
    connected_ids = set()
    blocked_ids = blocked_profile_ids(actor)
    for connection in Connection.objects.filter(Q(low=actor) | Q(high=actor), active=True).select_related("low", "high"):
        other = connection.other(actor)
        if other.pk in blocked_ids:
            continue
        conversation = connection.conversations.filter(generation=connection.generation).first()
        if conversation:
            connected_ids.add(other.pk)
            conversations.append({"conversation": conversation, "other": other,
                                  "last_message": conversation.messages.select_related("sender").order_by("-pk").first()})
    available_ids = set(recommendable_profiles().values_list("pk", flat=True))
    outgoing = []
    for swipe in SwipeDecision.objects.filter(actor=actor, choice=SwipeDecision.LIKE).select_related("target").order_by("-updated_at"):
        if (swipe.target_id in connected_ids or swipe.target_id not in available_ids
                or swipe.target_id in blocked_ids):
            continue
        outgoing.append({"profile": swipe.target, "sent_at": swipe.updated_at})
    incoming = []
    for swipe in SwipeDecision.objects.filter(target=actor, choice=SwipeDecision.LIKE).select_related("actor").order_by("-updated_at"):
        if (swipe.actor_id in connected_ids or not swipe.actor.is_published
                or swipe.actor_id in blocked_ids):
            continue
        incoming.append({"profile": swipe.actor, "sent_at": swipe.updated_at})
    invites = []
    for workspace in SearchWorkspace.objects.filter(invitee=actor, status="pending").select_related("inviter"):
        try:
            conversation_for(actor, workspace.conversation_id)
            invites.append(workspace)
        except DomainError:
            continue
    workspaces = []
    for membership in actor.workspaces.filter(active=True).select_related("workspace"):
        try:
            workspaces.append(workspace_for(actor, membership.workspace_id))
        except DomainError:
            continue
    return render(request, "journey/hub.html", {"conversations": conversations, "outgoing": outgoing,
                                                "incoming": incoming, "invites": invites, "workspaces": workspaces,
                                                "widget_client_id": uuid.uuid4()})


@page
def chat(request, conversation_id):
    conversation = conversation_for(request.actor, conversation_id, allow_pending=True)
    connection = conversation.connection
    other = connection.other(request.actor)
    if not connection.active:
        # Friendly pending-consent screen instead of a silent redirect/403
        return render(request, "journey/chat_pending.html", {
            "conversation": conversation,
            "other": other,
            "actor": request.actor,
            "hub_url": reverse("journey:hub"),
        })
    checkpoint(request.actor, request.path)
    result = score_profiles(request.actor, other)
    opener = f"Chào {other.name}, một điểm hợp của chúng ta là: {result.similarities[0]} Mình muốn trao đổi thêm về kế hoạch tìm nhà. Bạn thấy thế nào?" if result.similarities else f"Chào {other.name}, mình muốn tìm hiểu nhu cầu ở ghép của bạn. Mình cùng trao đổi nhé?"
    facts = []
    for fact in conversation.facts.select_related("source", "author").order_by("-pk"):
        consent_ids = set(fact.consents.filter(version=fact.version).values_list("member_id", flat=True))
        facts.append({"fact": fact, "confirmed": consent_ids == {connection.low_id, connection.high_id}, "mine": request.actor.pk in consent_ids})
    query = conversation.messages.select_related("sender")
    if request.GET.get("message"):
        source_id = number(request.GET["message"])
        if not query.filter(pk=source_id).exists():
            raise DomainError("Tin nguồn không thuộc cuộc trò chuyện này.", 404)
        messages_list = list(query.filter(pk__lte=source_id).order_by("-pk")[:25])[::-1] + list(query.filter(pk__gt=source_id).order_by("pk")[:25])
    else:
        messages_list = list(query.order_by("-pk")[:50])[::-1]
    older_cursor = messages_list[0].pk if messages_list and query.filter(pk__lt=messages_list[0].pk).exists() else None
    return render(request, "journey/chat.html", {"conversation": conversation, "other": other, "actor": request.actor,
                  "messages_list": messages_list,
                  "facts": facts, "opener": opener, "client_id": uuid.uuid4(),
                  "shared_workspace": conversation.workspaces.filter(status__in=["pending", "active"]).first(),
                  "older_cursor": older_cursor})


@page
def messages(request, conversation_id):
    conversation = conversation_for(request.actor, conversation_id, allow_pending=True)
    query = conversation.messages.select_related("sender")
    before = number(request.GET["before"]) if request.GET.get("before") else None
    after = number(request.GET.get("after"), 0)
    if before:
        rows = list(query.filter(pk__lt=before).order_by("-pk")[:50])[::-1]
    else:
        rows = list(query.filter(pk__gt=after).order_by("pk")[:50])
    return JsonResponse({"messages": [{"id": row.pk, "sender": row.sender.name, "mine": row.sender_id == request.actor.pk, "body": row.body, "created_at": row.created_at.isoformat()} for row in rows], "next_before": rows[0].pk if len(rows) == 50 else None})


@page
def pair_messages(request, profile_id):
    target = profile_by_id(profile_id)
    connection, conversation = pair_chat_for(request.actor, target)
    after = number(request.GET.get("after"), 0)
    if after < 0:
        raise DomainError("Mã tin nhắn không hợp lệ.")
    rows = list(conversation.messages.select_related("sender").filter(pk__gt=after).order_by("pk")[:50]) if conversation else []
    messages = [{"id": row.pk, "sender": row.sender.name,
                 "mine": row.sender_id == request.actor.pk, "body": row.body,
                 "created_at": row.created_at.isoformat()} for row in rows]
    if conversation:
        workspace = conversation.workspaces.filter(status__in=["pending", "active"]).order_by("pk").first()
        if workspace:
            body = (f"Lời mời cùng tìm nhà: {workspace.title}" if workspace.status == "pending"
                    else f"Lời mời cùng tìm nhà đã được đồng ý: {workspace.title}")
            messages.append({"id": f"workspace-{workspace.pk}", "sender": "ROOMORA", "mine": False,
                             "system": True, "workspace_id": workspace.pk, "status": workspace.status,
                             "inviter_id": workspace.inviter_id, "invitee_id": workspace.invitee_id,
                             "body": body, "created_at": workspace.created_at.isoformat()})
            messages.sort(key=lambda message: message["created_at"])
    return JsonResponse({"messages": messages, "connected": connection.active})

