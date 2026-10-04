from django.conf import settings
from . import services


def navigation(request):
    enabled = settings.ROOMORA_JOURNEY_ENABLED
    unread = 0
    if enabled and request.user.is_authenticated and hasattr(request.user, "profile"):
        profile = request.user.profile
        if not profile.is_synthetic or settings.DEBUG:
            services.retry_notifications_for_request(request, profile)
            unread = services.visible_notifications(profile).filter(read=False).count()
    return {"journey_enabled": enabled, "journey_unread": unread}
