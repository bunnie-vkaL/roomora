"""Legacy match, comparison, and connection views."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from core.constants import AREAS, GROUPS
from core.models import ConnectionRequest, LifestyleAnswers, PilotEvent, Profile, UserBlock, recommendable_profiles
from core.scoring import SCORING_VERSION, score_profiles
from core.services import block_profile

# ==============================================================================
# Legacy Pilot Discovery Views
# ==============================================================================

def ensure_user_profile_for_discovery(profile):
    """Ensure local/dev user profile has valid basic data and answers for matching."""
    changed = False
    if not profile.areas:
        profile.areas = ["Cầu Giấy", "Đống Đa", "Ba Đình"]
        changed = True
    if not profile.rent_min or profile.rent_min == 0:
        profile.rent_min = 3_000_000
        profile.rent_max = 5_500_000
        changed = True
    if not profile.age:
        profile.age = 23
        changed = True
    if not profile.name:
        profile.name = profile.user.first_name or profile.user.username.split("@")[0] or "Bạn"
        changed = True
    if not profile.contact_type:
        profile.contact_type = "zalo"
        profile.contact_value = "0912345678"
        changed = True
    if not profile.is_published:
        profile.is_published = True
        changed = True
    if profile.questionnaire_version != SCORING_VERSION:
        profile.questionnaire_version = SCORING_VERSION
        changed = True
    if changed:
        profile.save()

    answers, _ = LifestyleAnswers.objects.get_or_create(profile=profile)
    default_answers = {
        "A1": 1, "A2": 0, "A3": 1, "B1": 1, "B2": 1,
        "C1": 1, "C2": 0, "C3": 1, "D1": 0, "D2": 0,
        "D3": 0, "D4": 0, "D5": 1, "E1": 1, "F1": 1, "F2": 0
    }
    answers_changed = False
    for k, v in default_answers.items():
        if k not in answers.values or type(answers.values.get(k)) is not int:
            answers.values[k] = v
            answers_changed = True
    if answers_changed or not answers.is_complete:
        answers.save()


def overlap(left, right):
    return bool(set(left.areas) & set(right.areas)) and left.rent_min <= right.rent_max and right.rent_min <= left.rent_max


def blocked_pair(left, right):
    if UserBlock.objects.filter(Q(actor=left, target=right) | Q(actor=right, target=left)).exists():
        return True
    return ConnectionRequest.objects.filter(
        Q(sender=left, recipient=right) | Q(sender=right, recipient=left), status=ConnectionRequest.BLOCKED
    ).exists()


def find_matches(profile, area=None, rent=None):
    candidates = recommendable_profiles().exclude(pk=profile.pk).select_related("user", "answers")
    items = []
    for candidate in candidates:
        if not overlap(profile, candidate) or blocked_pair(profile, candidate):
            continue
        if area and area not in candidate.areas:
            continue
        if rent and not (candidate.rent_min <= rent <= candidate.rent_max):
            continue
        result = score_profiles(profile, candidate)
        if not result.excluded and result.score is not None:
            items.append((candidate, result))
    return sorted(items, key=lambda item: (-item[1].score, item[0].name.lower(), item[0].pk))[:10]


@login_required
def discover(request):
    profile = request.user.profile
    if settings.DEBUG:
        ensure_user_profile_for_discovery(profile)
    elif not profile.is_published:
        messages.info(request, "Hãy hoàn thành hồ sơ trước khi tìm match.")
        return redirect("profile_edit")

    area = request.GET.get("area")
    rent = request.GET.get("rent")
    try:
        rent = int(rent) if rent else None
    except ValueError:
        rent = None

    matches = find_matches(profile, area, rent)
    PilotEvent.objects.create(user=request.user, kind="discover_view")
    return render(request, "core/discover.html", {
        "matches": matches,
        "areas": AREAS,
        "selected_area": area,
        "rent": rent,
    })


@login_required
def comparison(request, profile_id):
    mine = request.user.profile
    if settings.DEBUG:
        ensure_user_profile_for_discovery(mine)
    other = get_object_or_404(Profile, pk=profile_id, is_published=True)
    if (not mine.is_published or (other.is_synthetic and not settings.DEBUG)
            or not overlap(mine, other) or blocked_pair(mine, other)):
        return HttpResponseForbidden("Hồ sơ này không khả dụng.")
    result = score_profiles(mine, other)
    if result.excluded or result.score is None:
        return HttpResponseForbidden(result.exclusion_reason or "Cần hoàn thành khảo sát mới để so sánh.")
    relation = ConnectionRequest.objects.filter(Q(sender=mine, recipient=other) | Q(sender=other, recipient=mine)).first()
    PilotEvent.objects.create(user=request.user, kind="comparison_view")
    group_items = [(GROUPS[key][0], value) for key, value in result.groups.items()]
    return render(request, "core/comparison.html", {
        "other": other,
        "result": result,
        "relation": relation,
        "show_contact": relation and relation.status == ConnectionRequest.ACCEPTED,
        "group_items": group_items,
    })


@login_required
def connect(request, profile_id):
    if request.method != "POST":
        return redirect("discover")
    sender, recipient = request.user.profile, get_object_or_404(Profile, pk=profile_id, is_published=True)
    if (sender == recipient or not sender.is_published or (recipient.is_synthetic and not settings.DEBUG)
            or blocked_pair(sender, recipient) or not overlap(sender, recipient)):
        return HttpResponseForbidden("Không thể gửi lời mời.")
    result = score_profiles(sender, recipient)
    if result.excluded or result.score is None:
        return HttpResponseForbidden("Hồ sơ này không khả dụng để kết nối.")
    existing = ConnectionRequest.objects.filter(
        Q(sender=sender, recipient=recipient) | Q(sender=recipient, recipient=sender)
    ).exclude(status__in=[ConnectionRequest.DECLINED, ConnectionRequest.WITHDRAWN]).first()
    if existing:
        messages.info(request, "Hai bạn đã có một lời mời hoặc kết nối đang hoạt động.")
        return redirect("comparison", profile_id=profile_id)
    obj, created = ConnectionRequest.objects.get_or_create(sender=sender, recipient=recipient, defaults={"status": ConnectionRequest.PENDING})
    if not created and obj.status in [ConnectionRequest.DECLINED, ConnectionRequest.WITHDRAWN]:
        obj.status = ConnectionRequest.PENDING
        obj.save()
        created = True
    messages.success(request, "Đã gửi lời mời kết nối." if created else "Lời mời đang tồn tại.")
    PilotEvent.objects.create(user=request.user, kind="connection_invited")
    return redirect("comparison", profile_id=profile_id)


@login_required
def connection_action(request, request_id, action):
    if request.method != "POST":
        return redirect("dashboard")
    item = get_object_or_404(ConnectionRequest, pk=request_id)
    mine = request.user.profile
    if action in ["accept", "decline"] and item.recipient != mine:
        return HttpResponseForbidden("Không có quyền thực hiện thao tác này.")
    if action == "block" and mine not in [item.sender, item.recipient]:
        return HttpResponseForbidden("Không có quyền thực hiện thao tác này.")
    if action == "withdraw" and item.sender != mine:
        return HttpResponseForbidden("Không có quyền thực hiện thao tác này.")
    mapping = {"accept": item.ACCEPTED, "decline": item.DECLINED, "block": item.BLOCKED, "withdraw": item.WITHDRAWN}
    if item.status != item.PENDING and action != "block":
        messages.info(request, "Lời mời này đã được xử lý.")
    else:
        with transaction.atomic():
            if action == "block":
                block_profile(mine, item.recipient if item.sender_id == mine.pk else item.sender)
            item.status = mapping[action]
            item.save()
        PilotEvent.objects.create(user=request.user, kind=f"connection_{action}")
        messages.success(request, "Đã cập nhật kết nối.")
    return redirect("dashboard")


