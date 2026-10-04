"""Landing / About public view."""

from django.conf import settings
from django.shortcuts import render

from core.constants import AREAS


def about(request):
    profile = getattr(request.user, "profile", None) if request.user.is_authenticated else None
    selected_area = request.GET.get("area", "")
    if selected_area not in AREAS:
        selected_area = profile.areas[0] if profile and profile.areas else AREAS[0]
    can_recommend = bool(
        settings.ROOMORA_JOURNEY_ENABLED and profile and profile.is_published
        and profile.completed and selected_area in profile.areas
    )
    recommendations = []
    if can_recommend:
        from core.web.discovery import candidate_rows
        recommendations = candidate_rows(profile, area=selected_area)[:3]
    return render(request, "core/about.html", {
        "areas": AREAS,
        "selected_area": selected_area,
        "profile": profile,
        "can_recommend": can_recommend,
        "recommendations": recommendations,
        "show_area_guide": True,
    })
