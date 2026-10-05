"""ASGI config for Roomora.

Routes requests to:
- /api/* to FastAPI (including /api/docs and /api/health)
- All other routes to Django ASGI (for pages, templates, auth, admin, and static fallback)
"""
import os
import django
from django.core.asgi import get_asgi_application
from starlette.applications import Starlette
from starlette.routing import Mount

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
django_asgi_app = get_asgi_application()

from api.main import api_app

application = Starlette(
    routes=[
        Mount("/api", app=api_app),
        Mount("/", app=django_asgi_app),
    ]
)
