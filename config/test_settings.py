"""File-backed SQLite exercises the same write-lock behavior as the application."""
from .settings import *  # noqa: F403

DATABASES["default"].setdefault("TEST", {})["NAME"] = BASE_DIR / f"test_journey_{os.getpid()}.sqlite3"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
