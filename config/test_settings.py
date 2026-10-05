"""File-backed SQLite exercises the same write-lock behavior as the application."""
from .settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / f"test_journey_{os.getpid()}.sqlite3",
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
UPSTASH_REDIS_REST_URL = ""
UPSTASH_REDIS_REST_TOKEN = ""
