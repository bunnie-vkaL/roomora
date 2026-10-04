"""Single-worker free hosting profile, with persistent SQLite and HTTPS email."""
from .public_settings import *  # noqa: F403

ROOMORA_DATA_ROOT = absolute_path("ROOMORA_DATA_ROOT")
assert_disjoint(STATIC_ROOT, MEDIA_ROOT, ROOMORA_PRIVATE_MEDIA_ROOT, ROOMORA_DATA_ROOT)
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3",
    "NAME": ROOMORA_DATA_ROOT / "roomora.sqlite3",
    "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"}}}
EMAIL_BACKEND = "core.email_backend.BrevoEmailBackend"
BREVO_API_KEY = required("BREVO_API_KEY")
EMAIL_TIMEOUT = 10
ROOMORA_EMAIL_DAILY_LIMIT = 250
ROOMORA_UPLOAD_BUDGET_BYTES = 64 * 1024 * 1024
ROOMORA_UPLOAD_FREE_RESERVE_BYTES = 32 * 1024 * 1024
ROOMORA_PERSON_IMAGE_COUNT = 20
ROOMORA_PERSON_IMAGE_BYTES = 8 * 1024 * 1024
STORAGES = {"default": {"BACKEND": "core.storage.BudgetFileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
