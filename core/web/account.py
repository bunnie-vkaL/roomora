"""Account creation, profile editing, and lifestyle survey views."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from core.constants import GROUPS, QUESTIONS
from core.forms import EmailAuthenticationForm, LifestyleQuestionForm, PreferencesForm, ProfileForm, RegistrationForm
from core.models import LifestyleAnswers, LivingPreferences, PilotEvent, Profile
from core.scoring import SCORING_VERSION


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            profile, _ = Profile.objects.get_or_create(
                user=user,
                defaults={"name": "", "age": 18, "areas": [], "rent_min": 0, "rent_max": 0,
                          "contact_type": "zalo", "contact_value": ""},
            )
            LifestyleAnswers.objects.get_or_create(profile=profile)
            login(request, user)
            request.session["profile_onboarding"] = True
            messages.success(request, "Đăng ký tài khoản thành công! Chào mừng bạn đến với ROOMORA.")
            next_url = request.GET.get("next") or request.POST.get("next")
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect("dashboard")
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
            display_name = (getattr(user, "profile", None) and user.profile.name) or user.email or user.username
            messages.success(request, f"Đăng nhập thành công! Chào mừng {display_name} trở lại.")
            next_url = request.GET.get("next") or request.POST.get("next")
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect("dashboard")
        messages.error(request, "Đăng nhập không thành công. Vui lòng kiểm tra lại thông tin đăng nhập.")
    return render(request, "registration/login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.success(request, "Bạn đã đăng xuất thành công.")
    return redirect("home")


@login_required
def dashboard(request):
    profile = request.user.profile
    if profile.is_published and profile.completed:
        return redirect("journey:discover" if settings.ROOMORA_JOURNEY_ENABLED else "discover")
    profile_ready = bool(profile.name and profile.areas and profile.rent_min and profile.rent_max and profile.contact_value)
    from core.constants import AREAS
    from core.views import candidate_rows
    selected_area = request.GET.get("area", "")
    if selected_area not in AREAS:
        selected_area = profile.areas[0] if profile.areas else AREAS[0]
    can_recommend = bool(settings.ROOMORA_JOURNEY_ENABLED and profile.is_published and profile.completed and selected_area in profile.areas)
    return render(request, "core/dashboard.html", {
        "profile": profile, "profile_ready": profile_ready, "areas": AREAS,
        "selected_area": selected_area, "can_recommend": can_recommend,
        "recommendations": candidate_rows(profile, area=selected_area)[:3] if can_recommend else [],
    })


@login_required
def profile_edit(request):
    profile = request.user.profile
    is_onboarding = bool(request.session.get("profile_onboarding"))
    form = ProfileForm(request.POST or None, request.FILES or None, instance=profile)
    living = LivingPreferences.objects.filter(profile=profile).first()
    living_form = PreferencesForm(request.POST or None, instance=living, prefix="living")
    if request.method == "POST" and form.is_valid() and living_form.is_valid():
        with transaction.atomic():
            profile = form.save(commit=False)
            profile.save()
            living = living_form.save(commit=False)
            living.profile = profile
            if living.pk:
                living.version += 1
            living.save()
        if is_onboarding:
            request.session.pop("profile_onboarding", None)
            messages.success(request, "Thông tin cơ bản đã được lưu. Tiếp tục trả lời lifestyle để hoàn tất hồ sơ.")
            return redirect("questionnaire")
        messages.success(request, "Đã lưu thay đổi hồ sơ.")
        return redirect("profile_edit")
    return render(request, "core/profile_form.html", {
        "form": form,
        "living_form": living_form,
        "profile": profile,
        "is_onboarding": is_onboarding,
    })


@login_required
def upload_avatar(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Phương thức không được hỗ trợ."}, status=405)
    avatar_file = request.FILES.get("avatar")
    if not avatar_file:
        return JsonResponse({"success": False, "error": "Chưa chọn tệp ảnh."}, status=400)
    if avatar_file.size > 8 * 1024 * 1024:
        return JsonResponse({"success": False, "error": "Ảnh đại diện cần nhỏ hơn 8 MB."}, status=400)
    content_type, name = getattr(avatar_file, "content_type", "").lower(), getattr(avatar_file, "name", "").lower()
    valid_types = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/pjpeg", "image/x-png"}
    if content_type and content_type not in valid_types and not name.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return JsonResponse({"success": False, "error": "Chỉ hỗ trợ định dạng JPG, PNG hoặc WebP."}, status=400)
    profile = request.user.profile
    profile.avatar = avatar_file
    profile.save()
    return JsonResponse({"success": True, "avatar_url": profile.avatar.url, "message": "Ảnh đại diện đã được lưu vào database thành công."})


@login_required
def delete_avatar(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Phương thức không được hỗ trợ."}, status=405)
    profile = request.user.profile
    if profile.avatar:
        profile.avatar.delete(save=False)
        profile.avatar = None
        profile.save()
    return JsonResponse({"success": True, "initial": (profile.name or request.user.email or "R")[:1].upper(),
                         "message": "Đã xóa ảnh đại diện trong database."})


@login_required
def questionnaire(request):
    profile = request.user.profile
    answers, _ = LifestyleAnswers.objects.get_or_create(profile=profile)
    valid_keys = {key for key, _, _, options in QUESTIONS
                  if type(answers.values.get(key)) is int and 0 <= answers.values[key] < len(options)}
    resume_step = next((i for i, (key, *_) in enumerate(QUESTIONS, 1) if key not in valid_keys), 1)
    try:
        step = int(request.POST.get("step", request.GET.get("step", resume_step)))
    except (TypeError, ValueError):
        step = 1
    step = max(1, min(step, len(QUESTIONS)))
    question = QUESTIONS[step - 1]
    form = LifestyleQuestionForm(question, request.POST or None, initial_value=answers.values.get(question[0]))
    if request.method == "POST" and form.is_valid():
        answers.values[question[0]] = form.answer()
        answers.save()
        action = request.POST.get("action", "next")
        if action == "save":
            messages.success(request, "Đã cập nhật câu trả lời lifestyle.")
            return redirect(f"{request.path}?step={step}")
        if action == "previous" and step > 1:
            return redirect(f"{request.path}?step={step - 1}")
        if step < len(QUESTIONS):
            return redirect(f"{request.path}?step={step + 1}")
        if not answers.is_complete:
            missing_step = next(i for i, (key, _, _, options) in enumerate(QUESTIONS, 1)
                                if type(answers.values.get(key)) is not int or not 0 <= answers.values[key] < len(options))
            messages.info(request, "Hãy trả lời đủ 16 câu trước khi xuất bản hồ sơ.")
            return redirect(f"{request.path}?step={missing_step}")
        profile.is_published, profile.questionnaire_version = True, SCORING_VERSION
        profile.full_clean()
        profile.save()
        PilotEvent.objects.create(user=request.user, kind="profile_published")
        messages.success(request, "Hồ sơ đã sẵn sàng. Đây là những người phù hợp với bạn.")
        return redirect("dashboard")
    survey_groups = []
    for group_key, (title, _) in GROUPS.items():
        group_questions = [(i, key) for i, (key, group, *_) in enumerate(QUESTIONS, 1) if group == group_key]
        survey_groups.append({"title": title, "step": group_questions[0][0],
                              "total": len(group_questions),
                              "answered": sum(key in valid_keys for _, key in group_questions),
                              "current": group_key == question[1]})
    return render(request, "core/questionnaire.html", {"form": form, "step": step,
                  "total_steps": len(QUESTIONS), "question": question,
                  "answered_count": len(valid_keys), "survey_groups": survey_groups,
                  "group_title": GROUPS[question[1]][0], "previous_step": step - 1})
