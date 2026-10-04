import os
from typing import Optional
from fastapi import Header, HTTPException, Request, status
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from core.models import Profile
from core.services import DomainError


def get_current_profile(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
) -> Profile:
    """Resolve active profile from Django session cookie or explicit test header."""
    user = None
    User = get_user_model()

    # 1. Inspect test / dev headers if provided
    if x_user_id:
        try:
            user = User.objects.filter(pk=int(x_user_id)).first()
        except (ValueError, TypeError):
            pass

    # 2. Inspect session cookie
    if not user:
        session_cookie_name = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
        session_key = request.cookies.get(session_cookie_name)
        if session_key:
            session = SessionStore(session_key=session_key)
            user_id = session.get("_auth_user_id")
            if user_id:
                user = User.objects.filter(pk=user_id).first()

    # 3. Inspect Authorization Bearer token (supports user ID or username in dev/test)
    if not user and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token.isdigit():
            user = User.objects.filter(pk=int(token)).first()
        else:
            user = User.objects.filter(username=token).first()

    if not user or not user.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yêu cầu đăng nhập để thực hiện thao tác này.",
        )

    profile, _ = Profile.objects.get_or_create(
        user=user,
        defaults={
            "name": user.username,
            "age": 18,
            "areas": [],
            "rent_min": 0,
            "rent_max": 0,
            "contact_type": "zalo",
            "contact_value": "",
        },
    )

    if profile.is_synthetic and not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản mẫu chỉ dùng trong môi trường thử nghiệm.",
        )

    return profile
