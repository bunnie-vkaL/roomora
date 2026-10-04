"""ASGI config for Roomora.

Routes requests to:
- /api/* and /docs to FastAPI (for typed API bridge & interactive Swagger documentation)
- All other routes to Django ASGI (for pages, templates, auth, and admin)
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
