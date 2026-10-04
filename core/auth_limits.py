"""Shared fixed-window limits before expensive authentication and email work."""
import ipaddress
import json
import math
from datetime import datetime, timezone as datetime_timezone

from django.conf import settings
from django.db import DatabaseError, transaction
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.deprecation import MiddlewareMixin

from .models import AuthRateBucket


def client_address(request):
    try:
        peer = ipaddress.ip_address(request.META.get("REMOTE_ADDR", ""))
    except ValueError:
        return "unknown"
    networks = [ipaddress.ip_network(value) for value in settings.ROOMORA_AUTH_TRUSTED_PROXIES]
    if any(peer in network for network in networks):
        try:
            return str(ipaddress.ip_address(request.META.get("HTTP_X_ROOMORA_CLIENT_IP", "")))
        except ValueError:
            pass
    return str(peer)


def consume(scope, dimensions, limit, seconds, now):
    window = int(now.timestamp()) // seconds
    expires = datetime.fromtimestamp((window + 1) * seconds, tz=datetime_timezone.utc)
    key = salted_hmac("roomora.auth.rate.v1", json.dumps([scope, dimensions, window],
                      ensure_ascii=True, separators=(",", ":")), algorithm="sha256").hexdigest()
    with transaction.atomic():
        AuthRateBucket.objects.get_or_create(key=key, defaults={"expires_at": expires})
        accepted = AuthRateBucket.objects.filter(pk=key, attempts__lt=limit).update(attempts=F("attempts") + 1)
    return bool(accepted), max(1, math.ceil((expires - now).total_seconds()))


class AuthRateLimitMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method != "POST":
            return None
        name = request.resolver_match.view_name
        scope = "login" if name == "admin:login" else name
        rules = settings.ROOMORA_AUTH_LIMITS.get(scope)
        if not rules:
            return None
        address = client_address(request)
        now = timezone.now()
        try:
            allowed, retry_after = consume(scope, [address], rules["ip"], rules["seconds"], now)
            if allowed and "identity_ip" in rules:
                identity = request.POST.get("username" if scope == "login" else "email", "").strip().casefold()
                allowed, retry_after = consume(scope + ":identity", [address, identity],
                                               rules["identity_ip"], rules["seconds"], now)
        except DatabaseError:
            response = HttpResponse(render_to_string("registration/auth_unavailable.html"), status=503)
            response["Retry-After"] = "60"
        else:
            if allowed:
                return None
            response = render(request, "registration/auth_limited.html", {"retry_minutes": math.ceil(retry_after / 60)}, status=429)
            response["Retry-After"] = str(retry_after)
        response["Cache-Control"] = "no-store"
        return response
