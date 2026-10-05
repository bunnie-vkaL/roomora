from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
import uuid

from django.db.models import Prefetch

from core.models import Connection, Conversation, PinnedFact, SearchWorkspace


def navigation(request):
    enabled = settings.ROOMORA_JOURNEY_ENABLED
    unread = 0
    recent_notifications = []
    chat_contacts = []
    if enabled and request.user.is_authenticated and hasattr(request.user, "profile"):
        profile = request.user.profile
        visible = profile.notifications.filter(
            created_at__gte=timezone.now() - timedelta(days=30)
        ).filter(
            Q(event__workspace__isnull=True) |
            Q(event__workspace__status="active", event__workspace__members__profile=profile,
              event__workspace__members__active=True)
        ).distinct()
        unread = visible.filter(read=False).count()
        recent_notifications = list(visible.select_related("event").order_by("-created_at")[:5])
        conversation_qs = Conversation.objects.order_by("-generation").prefetch_related(
            Prefetch("facts", queryset=PinnedFact.objects.select_related("author", "source").prefetch_related("consents"), to_attr="chat_facts"),
            Prefetch("workspaces", queryset=SearchWorkspace.objects.filter(status__in=["pending", "active"]), to_attr="chat_workspaces"),
        )
        connections = Connection.objects.filter(Q(low=profile) | Q(high=profile), active=True).select_related("low", "high").prefetch_related(
            Prefetch("conversations", queryset=conversation_qs, to_attr="chat_conversations")
        )
        for connection in connections:
            conversation = next((item for item in connection.chat_conversations if item.generation == connection.generation), None)
            if conversation:
                other = connection.other(profile)
                workspace = conversation.chat_workspaces[0] if conversation.chat_workspaces else None
                chat_contacts.append({
                    "profile": other,
                    "conversation": conversation,
                    "workspace": workspace,
                    "facts": [
                        {"fact": fact, "confirmed": {consent.member_id for consent in fact.consents.all()} == {connection.low_id, connection.high_id},
                         "mine": profile.pk in {consent.member_id for consent in fact.consents.all()}}
                        for fact in conversation.chat_facts
                    ],
                })
    return {
        "journey_enabled": enabled,
        "api_base_url": settings.API_BASE_URL,
        "journey_unread": unread,
        "journey_recent_notifications": recent_notifications,
        "journey_chat_contacts": chat_contacts,
        "journey_chat_client_id": uuid.uuid4(),
        "journey_chat_actor_id": getattr(request.user, "profile", None).pk if request.user.is_authenticated and hasattr(request.user, "profile") else "",
    }
