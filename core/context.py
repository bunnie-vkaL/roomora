from django.conf import settings
from django.db.models import Q


def navigation(request):
    enabled = settings.ROOMORA_JOURNEY_ENABLED
    unread = 0
    if enabled and request.user.is_authenticated and hasattr(request.user, "profile"):
        profile = request.user.profile
        unread = profile.notifications.filter(read=False).filter(
            Q(event__workspace__isnull=True) |
            Q(event__workspace__status="active", event__workspace__members__profile=profile,
              event__workspace__members__active=True)
        ).distinct().count()
    return {"journey_enabled": enabled, "journey_unread": unread}
