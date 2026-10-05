"""Roomora Backend API Server (FastAPI).

Usage:
    python api.py          # Run without auto-reload on http://127.0.0.1:8001
    python api.py --reload # Run with auto-reload on file changes
    python api.py --production --workers 2 # Run the unified ASGI app with Gunicorn
"""
import os
import sys
import argparse
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import uvicorn
from api.main import api_app as app

def main():
    if "--production" in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument("--production", action="store_true")
        parser.add_argument("--workers", type=int, default=2)
        parser.add_argument("--bind", default="127.0.0.1:8000")
        args = parser.parse_args()
        command = [
            sys.executable, "-m", "gunicorn", "config.asgi:application",
            "-k", "uvicorn.workers.UvicornWorker",
            "--workers", str(args.workers), "--bind", args.bind,
            "--access-logfile", "-", "--error-logfile", "-",
        ]
        os.execv(sys.executable, command)

    reload = "--reload" in sys.argv
    port = 8001
    print(f"ROOMORA FastAPI Backend running on http://127.0.0.1:{port}")
    print(f"Swagger UI Docs: http://127.0.0.1:{port}/docs")
    print(f"Auto-reload: {'Enabled' if reload else 'Disabled'}")

    if reload:
        uvicorn.run("api:app", host="127.0.0.1", port=port, reload=True)
    else:
        uvicorn.run(app, host="127.0.0.1", port=port, reload=False)

if __name__ == "__main__":
    main()
