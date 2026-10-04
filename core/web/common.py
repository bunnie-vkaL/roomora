"""Shared request parsing and access control for journey web views."""

import uuid
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import render

from core.models import Profile
from core.services import DomainError


def page(view):
    """Require an authenticated, enabled journey account for a web view."""
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not settings.ROOMORA_JOURNEY_ENABLED:
            raise Http404
        request.actor, _ = Profile.objects.get_or_create(
            user=request.user,
            defaults={"name": "", "age": 18, "areas": [], "rent_min": 0, "rent_max": 0,
                      "contact_type": "zalo", "contact_value": ""},
        )
        try:
            if request.actor.is_synthetic and not settings.DEBUG:
                raise DomainError("Tài khoản mẫu chỉ dùng trong môi trường thử nghiệm.", 403)
            return view(request, *args, **kwargs)
        except DomainError as exc:
            if request.headers.get("Accept") == "application/json":
                return JsonResponse({"error": exc.message}, status=exc.status)
            return render(request, "journey/error.html", {"error": exc.message}, status=exc.status)
    return wrapped


def number(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        if default is not None:
            return default
        raise DomainError("Mã hoặc số nhập vào không hợp lệ.")


def image_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise DomainError("Mã ảnh không hợp lệ.")


def text(data, key, limit, required=False):
    value = data.get(key, "").strip()
    if len(value) > limit or (required and not value):
        raise DomainError(f"Nội dung cần có độ dài từ {1 if required else 0} đến {limit} ký tự.")
    return value


def yes_no(data, key):
    value = data.get(key)
    if value not in ("1", "0"):
        raise DomainError("Hãy chọn đồng ý hoặc không đồng ý.")
    return value == "1"


def profile_by_id(value):
    profile = Profile.objects.filter(pk=number(value)).first()
    if not profile:
        raise DomainError("Hồ sơ không tồn tại.", 404)
    return profile


def clean_form(form):
    if not form.is_valid():
        raise DomainError(form.errors.as_text())
    return form.cleaned_data
