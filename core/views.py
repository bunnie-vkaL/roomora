import csv
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .constants import AREAS, GROUPS, QUESTIONS
from .forms import LifestyleQuestionForm, PilotExerciseForm, ProfileForm, RegistrationForm
from .models import ConnectionRequest, LifestyleAnswers, PilotEvent, PilotExercise, Profile
from .scoring import score_profiles


def home(request):
    return render(request, "core/home.html")


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        Profile.objects.create(user=user, name="", age=18, areas=[], rent_min=0, rent_max=0, contact_type="zalo", contact_value="")
        LifestyleAnswers.objects.create(profile=user.profile)
        login(request, user)
        return redirect("profile_edit")
    return render(request, "registration/register.html", {"form": form})


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
        profile.is_published = True
        profile.full_clean()
        profile.save()
        PilotEvent.objects.create(user=request.user, kind="profile_published")
        messages.success(request, "Hồ sơ đã xuất bản. Bạn có thể bắt đầu khám phá match.")
        return redirect("discover")
    return render(request, "core/questionnaire.html", {"form": form, "step": step, "total_steps": len(QUESTIONS), "question": question, "answered_count": len(answers.values)})


def overlap(left, right):
    return bool(set(left.areas) & set(right.areas)) and left.rent_min <= right.rent_max and right.rent_min <= left.rent_max


def blocked_pair(left, right):
    return ConnectionRequest.objects.filter(
        Q(sender=left, recipient=right) | Q(sender=right, recipient=left), status=ConnectionRequest.BLOCKED
    ).exists()


def find_matches(profile, area=None, rent=None):
    candidates = Profile.objects.filter(is_published=True).exclude(pk=profile.pk).select_related("user", "answers")
    if not settings.DEBUG:
        candidates = candidates.filter(is_synthetic=False)
    items = []
    for candidate in candidates:
        if not overlap(profile, candidate) or blocked_pair(profile, candidate):
            continue
        if area and area not in candidate.areas: continue
        if rent and not (candidate.rent_min <= rent <= candidate.rent_max): continue
        result = score_profiles(profile, candidate)
        if not result.excluded:
            items.append((candidate, result))
    return sorted(items, key=lambda item: (-item[1].score, item[0].name.lower(), item[0].pk))


@login_required
def discover(request):
    profile = request.user.profile
    if not profile.is_published:
        messages.info(request, "Hãy hoàn thành hồ sơ trước khi tìm match.")
        return redirect("profile_edit")
    area, rent = request.GET.get("area"), request.GET.get("rent")
    try: rent = int(rent) if rent else None
    except ValueError: rent = None
    matches = find_matches(profile, area, rent)
    PilotEvent.objects.create(user=request.user, kind="discover_view")
    return render(request, "core/discover.html", {"matches": matches, "areas": AREAS, "selected_area": area, "rent": rent})


@login_required
def comparison(request, profile_id):
    mine, other = request.user.profile, get_object_or_404(Profile, pk=profile_id, is_published=True)
    if (other.is_synthetic and not settings.DEBUG) or not overlap(mine, other) or blocked_pair(mine, other):
        return HttpResponseForbidden("Hồ sơ này không khả dụng.")
    result = score_profiles(mine, other)
    if result.excluded: return HttpResponseForbidden(result.exclusion_reason)
    relation = ConnectionRequest.objects.filter(Q(sender=mine, recipient=other) | Q(sender=other, recipient=mine)).first()
    PilotEvent.objects.create(user=request.user, kind="comparison_view")
    group_items = [(GROUPS[key][0], value) for key, value in result.groups.items()]
    return render(request, "core/comparison.html", {"other": other, "result": result, "relation": relation, "show_contact": relation and relation.status == ConnectionRequest.ACCEPTED, "group_items": group_items})


@login_required
def connect(request, profile_id):
    if request.method != "POST": return redirect("discover")
    sender, recipient = request.user.profile, get_object_or_404(Profile, pk=profile_id, is_published=True)
    if sender == recipient or (recipient.is_synthetic and not settings.DEBUG) or blocked_pair(sender, recipient): return HttpResponseForbidden("Không thể gửi lời mời.")
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
