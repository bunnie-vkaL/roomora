"""Discovery and Candidate matching web views."""

from django.core import signing
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse

from core.constants import AREAS, GROUPS, QUESTIONS
from core.models import Profile, SavedCandidate, recommendable_profiles
from core.scoring import REASON_TITLES
from core.services import DomainError, eligible_target, pair_query
from core.web.common import number, page, profile_by_id


def candidate_card(actor, profile, result=None, context=None):
    result = result or eligible_target(actor, profile)
    living = getattr(profile, "living", None)
    source = getattr(profile, "sample_source", None)
    estimated_answers = set(source.estimated_answers) if source else set()
    lifestyle_sections = []
    answers = profile.answers.values if hasattr(profile, "answers") else {}
    for group_key, (group_title, _) in GROUPS.items():
        choices = [{"title": REASON_TITLES[key], "answer": options[answers[key]],
                    "estimated": key in estimated_answers}
                   for key, group, _, options in QUESTIONS if group == group_key and key in answers]
        if choices:
            lifestyle_sections.append({"title": group_title, "choices": choices})
    context_reason = ""
    if context:
        context_reason = f"Cùng cân nhắc {context.title}; cần trao đổi thêm về căn và phần tiền mỗi người."
    return {"profile": profile, "score": result.score, "score_version": result.version,
            "similarities": result.similarities, "differences": result.differences, "warnings": result.warnings,
            "living": living, "lifestyle_sections": lifestyle_sections,
            "behavior": source.behavior_metrics if source else None,
            "context_reason": context_reason,
            "saved": SavedCandidate.objects.filter(owner=actor, candidate=profile).exists()}


def candidate_rows(actor, area="", rent=None, context=None, include_decided=False):
    if not actor.is_published or not actor.completed:
        return []
    from core.models import Connection
    candidates = recommendable_profiles().exclude(pk=actor.pk).select_related("answers", "living", "sample_source")
    if not include_decided:
        candidates = candidates.exclude(pk__in=actor.swipes.values("target_id"))
    rows = []
    for profile in candidates:
        if area and area not in profile.areas:
            continue
        if rent is not None and not profile.rent_min <= rent <= profile.rent_max:
            continue
        if not include_decided and Connection.objects.filter(pair_query(actor, profile), active=True).exists():
            continue
        try:
            result = eligible_target(actor, profile)
        except DomainError:
            continue
        rows.append(candidate_card(actor, profile, result, context))
    return sorted(rows, key=lambda row: (-row["score"], row["profile"].pk))


@page
def modern_discover(request):
    from core.services import checkpoint, room_for
    actor = request.actor
    context = room_for(actor, number(request.GET["room"])) if request.GET.get("room") else None
    area = request.GET.get("area", "")
    rent = number(request.GET.get("rent")) if request.GET.get("rent") else None

    # View mode: list or swipe (swipe is default)
    view_mode = request.GET.get("view", request.session.get("discover_view", "swipe"))
    if view_mode not in ("list", "swipe"):
        view_mode = "swipe"
    request.session["discover_view"] = view_mode

    rows = candidate_rows(actor, area, rent, context)

    # Graceful cursor: bad/stale cursor simply resets to start instead of 409
    start = 0
    if request.GET.get("cursor"):
        try:
            cursor = signing.loads(request.GET["cursor"], salt="journey-deck", max_age=3600)
            candidate_start = cursor.get("start", 0)
            if (cursor.get("actor") == actor.pk
                    and cursor.get("filters") == [area, rent, context.pk if context else None]
                    and isinstance(candidate_start, int)
                    and 0 <= candidate_start <= len(rows)):
                start = candidate_start
        except (signing.BadSignature, KeyError, TypeError):
            start = 0  # graceful fallback — no 409

    page_rows = rows[start:start + 10]
    cards = page_rows

    has_next = start + 10 < len(rows)
    next_cursor = (
        signing.dumps(
            {"actor": actor.pk, "filters": [area, rent, context.pk if context else None], "start": start + 10},
            salt="journey-deck",
        )
        if has_next else ""
    )

    checkpoint(actor, reverse("journey:discover"))
    guide_area = area or (actor.areas[0] if actor.areas else AREAS[0])
    guide_recommendations = candidate_rows(actor, guide_area, rent, context)[:3]

    # URL helpers for template
    def _url_with(extra):
        params = {k: v for k, v in request.GET.items() if k not in ("cursor", "view")}
        params.update(extra)
        from urllib.parse import urlencode
        return reverse("journey:discover") + "?" + urlencode({k: v for k, v in params.items() if v})

    list_url = _url_with({"view": "list"})
    swipe_url = _url_with({"view": "swipe"})
    all_areas_url = _url_with({"area": ""})
    next_url = _url_with({"cursor": next_cursor}) if next_cursor else ""

    return render(request, "journey/discover.html", {
        "cards": cards,
        "next_cursor": next_cursor,
        "next_url": next_url,
        "list_url": list_url,
        "swipe_url": swipe_url,
        "all_areas_url": all_areas_url,
        "view_mode": view_mode,
        "actor": actor,
        "profile": actor,
        "areas": AREAS,
        "selected_area": guide_area,
        "rent": rent or "",
        "room_context": context,
        "can_recommend": True,
        "recommendations": guide_recommendations,
    })


@page
def candidate(request, profile_id):
    from core.models import PrivateNote
    from core.services import checkpoint
    profile = profile_by_id(profile_id)
    card = candidate_card(request.actor, profile)
    note = PrivateNote.objects.filter(owner=request.actor, candidate=profile).first()
    checkpoint(request.actor, request.path)
    return render(request, "journey/candidate.html", {"card": card, "actor": request.actor, "note": note})


@page
def saved(request):
    cards = []
    for row in request.actor.saved_candidates.select_related("candidate__answers", "candidate__living"):
        try:
            cards.append(candidate_card(request.actor, row.candidate))
        except DomainError:
            continue
    return render(request, "journey/saved.html", {"cards": cards})


@page
def compare_candidates(request):
    ids = request.GET.getlist("candidate")
    if not 2 <= len(ids) <= 3 or len(set(ids)) != len(ids):
        raise DomainError("Chọn hai hoặc ba người đã lưu để so sánh.")
    cards = []
    for profile_id in ids:
        profile = profile_by_id(profile_id)
        if not SavedCandidate.objects.filter(owner=request.actor, candidate=profile).exists():
            raise DomainError("Chỉ so sánh người bạn đã lưu.", 403)
        cards.append(candidate_card(request.actor, profile))
    return render(request, "journey/compare.html", {"cards": cards, "actor": request.actor})


@page
def preferences(request):
    from core.forms import PreferencesForm
    from core.models import LivingPreferences
    from core.services import checkpoint
    living = LivingPreferences.objects.filter(profile=request.actor).first()
    checkpoint(request.actor, request.path)
    return render(request, "journey/preferences.html", {"form": PreferencesForm(instance=living), "version": living.version if living else 0})
