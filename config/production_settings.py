"""PostgreSQL and SMTP deployment profile."""
from .public_settings import *  # noqa: F403

DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql",
    "NAME": required("POSTGRES_DB"), "USER": required("POSTGRES_USER"),
    "PASSWORD": required("POSTGRES_PASSWORD"), "HOST": required("POSTGRES_HOST"),
    "PORT": os.getenv("POSTGRES_PORT", "5432"), "CONN_MAX_AGE": 60,
    "CONN_HEALTH_CHECKS": True, "OPTIONS": {"sslmode": "require", "connect_timeout": 5}}}

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = required("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = required("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = required("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = required("DEFAULT_FROM_EMAIL")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
