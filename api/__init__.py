"""Roomora FastAPI API Bridge Package"""
import os
import django

if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

try:
    django.setup()
except RuntimeError:
    pass

from .main import api_app as app

__all__ = ["app"]
