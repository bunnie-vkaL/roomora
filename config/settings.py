import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

env_path = BASE_DIR / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

SECRET_KEY = os.getenv("SECRET_KEY", "roomora-local-development-key-please-replace-with-a-long-random-value-2026")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "core",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages", "core.context.navigation",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    parsed_database_url = urlparse(DATABASE_URL)
    if parsed_database_url.scheme not in {"postgres", "postgresql"} or not parsed_database_url.hostname:
        raise ValueError("DATABASE_URL phải là một PostgreSQL connection URI hợp lệ.")
    query = parse_qs(parsed_database_url.query)
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": (parsed_database_url.path or "/postgres").lstrip("/"),
        "USER": unquote(parsed_database_url.username or ""),
        "PASSWORD": unquote(parsed_database_url.password or ""),
        "HOST": parsed_database_url.hostname,
        "PORT": str(parsed_database_url.port or 5432),
        # Supabase's port 6543 is a transaction pooler: do not hold a Django
        # connection or server-side cursor across requests.
        "CONN_MAX_AGE": 0,
        "DISABLE_SERVER_SIDE_CURSORS": True,
        "OPTIONS": {"sslmode": query.get("sslmode", ["require"])[0]},
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3",
                             "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
                             "TEST": {"MIRROR": None}}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "vi"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "no-reply@roomora.local"
ROOMORA_JOURNEY_ENABLED = os.getenv("ROOMORA_JOURNEY_ENABLED", "True").lower() == "true"
API_BASE_URL = os.getenv("API_BASE_URL", "/api").strip().rstrip("/") or "/api"
UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
UPSTASH_REDIS_TIMEOUT = float(os.getenv("UPSTASH_REDIS_TIMEOUT", "0.35"))
UPSTASH_CACHE_TTL = int(os.getenv("UPSTASH_CACHE_TTL", "20"))
UPSTASH_LOCAL_TTL = float(os.getenv("UPSTASH_LOCAL_TTL", "5"))
ROOMORA_PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
