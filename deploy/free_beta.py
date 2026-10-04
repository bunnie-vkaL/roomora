"""Use the same private environment file for the provider WSGI app and CLI."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys


APP_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_KEYS = {"SECRET_KEY", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS", "STATIC_ROOT", "MEDIA_ROOT",
                "ROOMORA_PRIVATE_MEDIA_ROOT", "ROOMORA_DATA_ROOT", "DEFAULT_FROM_EMAIL", "BREVO_API_KEY",
                "ROOMORA_TRUST_PROXY_PROTO", "ROOMORA_AUTH_TRUSTED_PROXIES", "ROOMORA_JOURNEY_ENABLED"}
REQUIRED_KEYS = ALLOWED_KEYS - {"ROOMORA_TRUST_PROXY_PROTO", "ROOMORA_AUTH_TRUSTED_PROXIES", "ROOMORA_JOURNEY_ENABLED"}


def load_environment(path):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("Private configuration must be an absolute, unlinked file.")
    path = path.resolve(strict=True)
    if path.is_relative_to(APP_ROOT):
        raise ValueError("Private configuration must stay outside application source.")
    if path.stat().st_size > 16384:
        raise ValueError("Private configuration is too large.")
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("Private configuration must have owner-only permissions.")
    values = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(values, dict) or set(values) - ALLOWED_KEYS or not REQUIRED_KEYS <= set(values):
        raise ValueError("Private configuration has missing or unsupported keys.")
    if any(not isinstance(value, str) for value in values.values()):
        raise ValueError("Private configuration values must be strings.")
    for key in ("STATIC_ROOT", "MEDIA_ROOT", "ROOMORA_PRIVATE_MEDIA_ROOT", "ROOMORA_DATA_ROOT"):
        root = Path(values[key])
        if not root.is_absolute() or path.is_relative_to(root.resolve()) or root.resolve().is_relative_to(APP_ROOT) or APP_ROOT.is_relative_to(root.resolve()):
            raise ValueError("Storage and private configuration must be separate from application source.")
    values.setdefault("ROOMORA_TRUST_PROXY_PROTO", "0")
    values.setdefault("ROOMORA_AUTH_TRUSTED_PROXIES", "")
    values.setdefault("ROOMORA_JOURNEY_ENABLED", "True")
    os.environ.update(values)
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.free_beta_settings"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    options = parser.parse_args()
    if not options.command:
        parser.error("A Django management command is required.")
    try:
        load_environment(options.env)
    except (OSError, ValueError):
        raise SystemExit("Private configuration could not be loaded; check its keys, location and permissions.") from None
    sys.path.insert(0, str(APP_ROOT))
    from django.core.management import execute_from_command_line
    execute_from_command_line(["manage.py", *options.command])


if __name__ == "__main__":
    main()
