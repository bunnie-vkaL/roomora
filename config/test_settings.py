"""File-backed SQLite exercises the same write-lock behavior as the application."""
from copy import deepcopy
from .settings import *  # noqa: F403

DATABASES = deepcopy(DATABASES)
DATABASES["default"]["TEST"] = {"NAME": BASE_DIR / f"test_journey_{os.getpid()}.sqlite3"}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
