from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta


def navigation(request):
    enabled = settings.ROOMORA_JOURNEY_ENABLED
    unread = 0
    recent_notifications = []
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
    return {
        "journey_enabled": enabled,
        "api_base_url": settings.API_BASE_URL,
        "journey_unread": unread,
        "journey_recent_notifications": recent_notifications,
    }
