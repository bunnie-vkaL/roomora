import csv
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from .constants import AREAS, GROUPS, QUESTIONS
from .forms import (
    EmailAuthenticationForm,
    LifestyleQuestionForm,
    PilotExerciseForm,
    ProfileForm,
    RegistrationForm,
)
from .models import ConnectionRequest, LifestyleAnswers, PilotEvent, PilotExercise, Profile
from .scoring import SCORING_VERSION, score_profiles


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "core/home.html")


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            profile, _ = Profile.objects.get_or_create(
                user=user,
                defaults={
                    "name": "",
                    "age": 18,
                    "areas": [],
                    "rent_min": 0,
                    "rent_max": 0,
                    "contact_type": "zalo",
                    "contact_value": "",
                },
            )
            LifestyleAnswers.objects.get_or_create(profile=profile)
            login(request, user)
            messages.success(request, "Đăng ký tài khoản thành công! Chào mừng bạn đến với ROOMORA.")
            next_url = request.GET.get("next") or request.POST.get("next")
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect("dashboard")
        else:
            messages.error(request, "Đăng ký không thành công. Vui lòng kiểm tra lại thông tin bên dưới.")
    return render(request, "registration/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = EmailAuthenticationForm(request, data=request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            profile_name = getattr(user, "profile", None) and user.profile.name
            display_name = profile_name or user.email or user.username
            messages.success(request, f"Đăng nhập thành công! Chào mừng {display_name} trở lại.")
            next_url = request.GET.get("next") or request.POST.get("next")
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect("dashboard")
        else:
            messages.error(request, "Đăng nhập không thành công. Vui lòng kiểm tra lại thông tin đăng nhập.")
    return render(request, "registration/login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.success(request, "Bạn đã đăng xuất thành công.")
    return redirect("home")


@login_required
def dashboard(request):
    profile = request.user.profile
    matches = find_matches(profile) if profile.is_published else []
    return render(request, "core/dashboard.html", {"profile": profile, "matches": matches[:3]})


@login_required
def profile_edit(request):
    profile = request.user.profile
    form = ProfileForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        profile = form.save(commit=False)
        profile.is_published = False
        profile.save()
        messages.success(request, "Thông tin cơ bản đã được lưu. Hoàn thành khảo sát để xuất bản hồ sơ.")
        return redirect("questionnaire")
    return render(request, "core/profile_form.html", {"form": form, "profile": profile})


@login_required
def upload_avatar(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Phương thức không được hỗ trợ."}, status=405)
    avatar_file = request.FILES.get("avatar")
    if not avatar_file:
        return JsonResponse({"success": False, "error": "Chưa chọn tệp ảnh."}, status=400)
    if avatar_file.size > 5 * 1024 * 1024:
        return JsonResponse({"success": False, "error": "Ảnh đại diện cần nhỏ hơn 5 MB."}, status=400)
    content_type = getattr(avatar_file, "content_type", "").lower()
    name = getattr(avatar_file, "name", "").lower()
    valid_types = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/pjpeg", "image/x-png"}
    valid_exts = (".jpg", ".jpeg", ".png", ".webp")
    if content_type and content_type not in valid_types and not any(name.endswith(ext) for ext in valid_exts):
        return JsonResponse({"success": False, "error": "Chỉ hỗ trợ định dạng JPG, PNG hoặc WebP."}, status=400)
    profile = request.user.profile
    profile.avatar = avatar_file
    profile.save()
    return JsonResponse({
        "success": True,
        "avatar_url": profile.avatar.url,
        "message": "Ảnh đại diện đã được lưu vào database thành công."
    })


@login_required
def delete_avatar(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Phương thức không được hỗ trợ."}, status=405)
    profile = request.user.profile
    if profile.avatar:
        profile.avatar.delete(save=False)
        profile.avatar = None
        profile.save()
    fallback_initial = (profile.name or request.user.email or "R")[:1].upper()
    return JsonResponse({
        "success": True,
        "initial": fallback_initial,
        "message": "Đã xóa ảnh đại diện trong database."
    })


@login_required
def questionnaire(request):
    profile = request.user.profile
    answers, _ = LifestyleAnswers.objects.get_or_create(profile=profile)
    try:
        step = int(request.POST.get("step", request.GET.get("step", 1)))
    except (TypeError, ValueError):
        step = 1
    step = max(1, min(step, len(QUESTIONS)))
    question = QUESTIONS[step - 1]
    form = LifestyleQuestionForm(question, request.POST or None, initial_value=answers.values.get(question[0]))
    if request.method == "POST" and form.is_valid():
        answers.values[question[0]] = form.answer()
        answers.save()
        action = request.POST.get("action", "next")
        if action == "previous" and step > 1:
            return redirect(f"{request.path}?step={step - 1}")
        if step < len(QUESTIONS):
            return redirect(f"{request.path}?step={step + 1}")
        if not answers.is_complete:
            missing_step = next(i for i, (key, _, _, options) in enumerate(QUESTIONS, 1)
                                if type(answers.values.get(key)) is not int or not 0 <= answers.values[key] < len(options))
            messages.info(request, "Hãy trả lời đủ 16 câu trước khi xuất bản hồ sơ.")
            return redirect(f"{request.path}?step={missing_step}")
        profile.is_published = True
        profile.questionnaire_version = SCORING_VERSION
        profile.full_clean()
        profile.save()
        PilotEvent.objects.create(user=request.user, kind="profile_published")
        messages.success(request, "Hồ sơ đã xuất bản. Bạn có thể bắt đầu khám phá match.")
        return redirect("discover")
    answered_count = sum(key in answers.values for key, _, _, _ in QUESTIONS)
    return render(request, "core/questionnaire.html", {"form": form, "step": step, "total_steps": len(QUESTIONS), "question": question, "answered_count": answered_count})


def ensure_user_profile_for_discovery(profile):
    """
    On development/localhost, ensure the current user's profile has valid basic data
    and complete lifestyle answers so that compatibility scoring and matching work seamlessly.
    """
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


def ensure_sample_matches(profile):
    """
    Generate or calibrate 10 synthetic sample profiles ('Mẫu thử #01' - 'Mẫu thử #10')
    that directly match the localhost account's selected areas, rent budget, and lifestyle answers,
    ranked with strictly decreasing compatibility scores (from 99% down to 84%).
    """
    Profile.objects.filter(user__username__startswith="synthetic-").update(is_published=False)

    user_areas = profile.areas or ["Cầu Giấy", "Đống Đa", "Ba Đình"]
    user_min = profile.rent_min or 3_000_000
    user_max = profile.rent_max or 5_500_000
    user_ans = profile.answers.values if hasattr(profile, "answers") else {}

    c3_alt = (user_ans.get("C3", 0) + 1) % 3
    e1_alt = (user_ans.get("E1", 0) + 1) % 4
    b2_alt = (user_ans.get("B2", 0) + 1) % 4
    d5_alt = (user_ans.get("D5", 0) + 1) % 3
    f2_alt = (user_ans.get("F2", 0) + 1) % 4
    a3_val = user_ans.get("A3", 0)
    a3_alt = 1 if a3_val in (0, 3) else 0
    c2_alt = (user_ans.get("C2", 0) + 2) % 4
    d4_val = user_ans.get("D4", 0)
    d4_alt = min(3, d4_val + 1) if d4_val < 3 else 2
    f1_val = user_ans.get("F1", 0)
    f1_alt = 1 if f1_val in (0, 3) else 0

    variations = [
        ({}, 0, 0, user_areas),
        ({"C3": c3_alt}, 0, 0, user_areas),
        ({"C3": c3_alt, "E1": e1_alt}, 200_000, 200_000, user_areas),
        ({"C3": c3_alt, "E1": e1_alt, "B2": b2_alt}, 200_000, 200_000, user_areas),
        ({"C3": c3_alt, "E1": e1_alt, "B2": b2_alt, "D5": d5_alt}, 300_000, 300_000, user_areas),
        ({"C3": c3_alt, "E1": e1_alt, "B2": b2_alt, "D5": d5_alt, "F2": f2_alt}, -200_000, -200_000, user_areas),
        ({"C3": c3_alt, "E1": e1_alt, "B2": b2_alt, "D5": d5_alt, "F2": f2_alt, "A3": a3_alt}, -300_000, -300_000, user_areas),
        ({"C3": c3_alt, "E1": e1_alt, "B2": b2_alt, "D5": d5_alt, "F2": f2_alt, "A3": a3_alt, "C2": c2_alt}, -300_000, -300_000, user_areas),
        ({"C3": c3_alt, "E1": e1_alt, "B2": b2_alt, "D5": d5_alt, "F2": f2_alt, "A3": a3_alt, "C2": c2_alt, "D4": d4_alt}, -400_000, -400_000, user_areas),
        ({"C3": c3_alt, "E1": e1_alt, "B2": b2_alt, "D5": d5_alt, "F2": f2_alt, "A3": a3_alt, "C2": c2_alt, "D4": d4_alt, "F1": f1_alt}, -400_000, -400_000, user_areas),
    ]

    for idx, (delta, rent_dmin, rent_dmax, candidate_areas) in enumerate(variations, 1):
        email = f"sample-{idx:02d}@roomora.local"
        user, _ = User.objects.get_or_create(username=email, defaults={"email": email})
        if not user.has_usable_password():
            user.set_unusable_password()
            user.save()

        sample_rent_min = max(500_000, user_min + rent_dmin)
        sample_rent_max = max(sample_rent_min + 500_000, user_max + rent_dmax)

        p_obj, _ = Profile.objects.get_or_create(user=user, defaults={
            "name": f"Mẫu thử #{idx:02d}",
            "age": 23,
            "gender": "",
            "areas": candidate_areas,
            "rent_min": sample_rent_min,
            "rent_max": sample_rent_max,
            "contact_type": "zalo",
            "contact_value": "Mẫu thử nghiệm",
            "is_published": True,
            "is_synthetic": True,
            "questionnaire_version": SCORING_VERSION,
        })
        p_obj.name = f"Mẫu thử #{idx:02d}"
        p_obj.age = 23
        p_obj.bio = ""
        p_obj.areas = candidate_areas
        p_obj.rent_min = sample_rent_min
        p_obj.rent_max = sample_rent_max
        p_obj.is_published = True
        p_obj.is_synthetic = True
        p_obj.questionnaire_version = SCORING_VERSION
        p_obj.save()

        sample_ans = dict(user_ans)
        for k, v in delta.items():
            sample_ans[k] = v
        LifestyleAnswers.objects.update_or_create(profile=p_obj, defaults={"values": sample_ans})


def overlap(left, right):
    return bool(set(left.areas) & set(right.areas)) and left.rent_min <= right.rent_max and right.rent_min <= left.rent_max


def blocked_pair(left, right):
    from journey.models import UserBlock
    if UserBlock.objects.filter(Q(actor=left, target=right) | Q(actor=right, target=left)).exists():
        return True
    return ConnectionRequest.objects.filter(
        Q(sender=left, recipient=right) | Q(sender=right, recipient=left), status=ConnectionRequest.BLOCKED
    ).exists()


def find_matches(profile, area=None, rent=None):
    candidates = Profile.objects.filter(is_published=True).exclude(pk=profile.pk).select_related("user", "answers")
    if settings.DEBUG:
        candidates = candidates.filter(is_synthetic=True, user__username__startswith="sample-")
    else:
        candidates = candidates.filter(is_synthetic=False)
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
        ensure_sample_matches(profile)
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
    if request.method != "POST": return redirect("discover")
    sender, recipient = request.user.profile, get_object_or_404(Profile, pk=profile_id, is_published=True)
    if (sender == recipient or not sender.is_published or (recipient.is_synthetic and not settings.DEBUG)
            or blocked_pair(sender, recipient) or not overlap(sender, recipient)):
        return HttpResponseForbidden("Không thể gửi lời mời.")
    result = score_profiles(sender, recipient)
    if result.excluded or result.score is None:
        return HttpResponseForbidden("Hồ sơ này không khả dụng để kết nối.")
    existing = ConnectionRequest.objects.filter(Q(sender=sender, recipient=recipient) | Q(sender=recipient, recipient=sender)).exclude(status__in=[ConnectionRequest.DECLINED, ConnectionRequest.WITHDRAWN]).first()
    if existing:
        messages.info(request, "Hai bạn đã có một lời mời hoặc kết nối đang hoạt động.")
        return redirect("comparison", profile_id=profile_id)
    obj, created = ConnectionRequest.objects.get_or_create(sender=sender, recipient=recipient, defaults={"status": ConnectionRequest.PENDING})
    if not created and obj.status in [ConnectionRequest.DECLINED, ConnectionRequest.WITHDRAWN]:
        obj.status = ConnectionRequest.PENDING; obj.save(); created = True
    messages.success(request, "Đã gửi lời mời kết nối." if created else "Lời mời đang tồn tại.")
    PilotEvent.objects.create(user=request.user, kind="connection_invited")
    return redirect("comparison", profile_id=profile_id)


@login_required
def connection_action(request, request_id, action):
    if request.method != "POST": return redirect("dashboard")
    item = get_object_or_404(ConnectionRequest, pk=request_id)
    mine = request.user.profile
    if action in ["accept", "decline"] and item.recipient != mine: return HttpResponseForbidden("Không có quyền thực hiện thao tác này.")
    if action == "block" and mine not in [item.sender, item.recipient]: return HttpResponseForbidden("Không có quyền thực hiện thao tác này.")
    if action == "withdraw" and item.sender != mine: return HttpResponseForbidden("Không có quyền thực hiện thao tác này.")
    mapping = {"accept": item.ACCEPTED, "decline": item.DECLINED, "block": item.BLOCKED, "withdraw": item.WITHDRAWN}
    if item.status != item.PENDING and action != "block":
        messages.info(request, "Lời mời này đã được xử lý.")
    else:
        with transaction.atomic():
            if action == "block":
                from journey.services import block_profile
                block_profile(mine, item.recipient if item.sender_id == mine.pk else item.sender)
            item.status = mapping[action]; item.save()
        PilotEvent.objects.create(user=request.user, kind=f"connection_{action}")
        messages.success(request, "Đã cập nhật kết nối.")
    return redirect("dashboard")


@login_required
def pilot_exercise(request):
    profile = request.user.profile
    candidates = find_matches(profile)[:3]
    if not candidates:
        messages.info(request, "Cần có ít nhất một match để làm bài thử nghiệm.")
        return redirect("discover")
    exercise, created = PilotExercise.objects.get_or_create(user=request.user, defaults={"score_first": bool(request.user.pk % 2), "candidate_ids": [p.pk for p, _ in candidates]})
    candidate_ids = exercise.candidate_ids
    candidates = [(p, r) for p, r in candidates if p.pk in candidate_ids]
    form = PilotExerciseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        lookup = {p.pk: p for p, _ in candidates}
        if form.cleaned_data["basic_choice"] not in lookup or form.cleaned_data["score_choice"] not in lookup:
            form.add_error(None, "Hãy chọn hồ sơ từ danh sách hiển thị.")
        else:
            exercise.basic_choice = lookup[form.cleaned_data["basic_choice"]]
            exercise.score_choice = lookup[form.cleaned_data["score_choice"]]
            exercise.basic_trust = form.cleaned_data["basic_trust"]
            exercise.score_trust = form.cleaned_data["score_trust"]
            exercise.feedback = form.cleaned_data["feedback"]
            exercise.completed_at = timezone.now(); exercise.save()
            PilotEvent.objects.create(user=request.user, kind="pilot_completed")
            messages.success(request, "Cảm ơn bạn đã hoàn thành bài thử nghiệm.")
            return redirect("dashboard")
    return render(request, "core/pilot.html", {"form": form, "candidates": candidates, "exercise": exercise})


@user_passes_test(lambda user: user.is_staff)
def pilot_results(request):
    exercises = PilotExercise.objects.filter(completed_at__isnull=False)
    return render(request, "core/pilot_results.html", {"exercises": exercises, "event_counts": {kind: PilotEvent.objects.filter(kind=kind).count() for kind in ["profile_published", "comparison_view", "connection_invited", "connection_accept"]}})


@user_passes_test(lambda user: user.is_staff)
def pilot_export(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="roomora-pilot-results.csv"'
    writer = csv.writer(response); writer.writerow(["completed_at", "score_first", "basic_trust", "score_trust", "feedback"])
    for item in PilotExercise.objects.filter(completed_at__isnull=False): writer.writerow([item.completed_at, item.score_first, item.basic_trust, item.score_trust, item.feedback])
    return response
