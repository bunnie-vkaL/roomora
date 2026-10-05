"""Roomora Frontend Web Server (Django).

Usage:
    python frontend.py          # Run without auto-reload on http://127.0.0.1:8000
    python frontend.py --reload # Run with auto-reload on file changes
    python frontend.py --production --workers 2 # Run the unified ASGI app with Gunicorn
"""
import os
import sys
import argparse

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

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

    from django.core.management import execute_from_command_line

    reload = "--reload" in sys.argv
    filtered_args = [arg for arg in sys.argv if arg != "--reload"]

    if len(filtered_args) == 1:
        port = "127.0.0.1:8000"
        print(f"ROOMORA Frontend Server running on http://{port}")
        print(f"Auto-reload: {'Enabled' if reload else 'Disabled'}")
        cmd = [filtered_args[0], "runserver", port]
        if not reload:
            cmd.append("--noreload")
        execute_from_command_line(cmd)
    else:
        execute_from_command_line(filtered_args)

if __name__ == "__main__":
    main()
