"""Shared security for public deployments; credentials come from the environment."""
import os
import ipaddress
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured
from .settings import *  # noqa: F403


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"Missing production setting: {name}")
    return value


def absolute_path(name):
    value = Path(required(name))
    if not value.is_absolute():
        raise ImproperlyConfigured("Public storage paths must be absolute.")
    return value.resolve()


def assert_disjoint(*paths):
    for i, left in enumerate(paths):
        for right in paths[i + 1:]:
            if left.is_relative_to(right) or right.is_relative_to(left):
                raise ImproperlyConfigured("Public, private and data roots must not overlap.")


DEBUG = False
SECRET_KEY = required("SECRET_KEY")
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 20 or any(
        marker in SECRET_KEY.lower() for marker in ("replace-me", "local-development", "django-insecure")):
    raise ImproperlyConfigured("Production SECRET_KEY must be a fresh random secret.")
ALLOWED_HOSTS = [host.strip() for host in required("ALLOWED_HOSTS").split(",")]
if any(not host or "*" in host or "/" in host or ":" in host or host.startswith(".") for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("Production ALLOWED_HOSTS requires explicit domain names.")
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in required("CSRF_TRUSTED_ORIGINS").split(",")]
for origin in CSRF_TRUSTED_ORIGINS:
    parsed = urlparse(origin)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise ImproperlyConfigured("CSRF origins must be HTTPS origins for allowed hosts.")

STATIC_URL = "/static/"
STATIC_ROOT = absolute_path("STATIC_ROOT")
MEDIA_ROOT = absolute_path("MEDIA_ROOT")
ROOMORA_PRIVATE_MEDIA_ROOT = absolute_path("ROOMORA_PRIVATE_MEDIA_ROOT")
assert_disjoint(STATIC_ROOT, MEDIA_ROOT, ROOMORA_PRIVATE_MEDIA_ROOT)

DEFAULT_FROM_EMAIL = required("DEFAULT_FROM_EMAIL")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# Enable only when the trusted edge replaces incoming forwarded-proto headers.
if os.getenv("ROOMORA_TRUST_PROXY_PROTO") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    SECURE_PROXY_SSL_HEADER = None

DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
ROOMORA_AUTH_TRUSTED_PROXIES = [value.strip() for value in os.getenv("ROOMORA_AUTH_TRUSTED_PROXIES", "").split(",") if value.strip()]
for value in ROOMORA_AUTH_TRUSTED_PROXIES:
    try:
        network = ipaddress.ip_network(value)
    except ValueError as exc:
        raise ImproperlyConfigured("Invalid trusted auth proxy network.") from exc
    if network.prefixlen == 0:
        raise ImproperlyConfigured("Do not trust all addresses for client-IP headers.")
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
ROOMORA_MUTATION_LIMITS = {
    "all": ({"limit": 120, "seconds": 60}, {"limit": 1000, "seconds": 3600}),
    "message": ({"limit": 30, "seconds": 60}, {"limit": 300, "seconds": 3600}),
    "discovery": ({"limit": 60, "seconds": 60}, {"limit": 600, "seconds": 3600}),
    "workspace-invite": ({"limit": 10, "seconds": 3600},),
    "room-save": ({"limit": 60, "seconds": 3600},),
    "image-upload": ({"limit": 20, "seconds": 3600},),
    "report": ({"limit": 10, "seconds": 3600},),
}
LOGGING = {"version": 1, "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}}}
