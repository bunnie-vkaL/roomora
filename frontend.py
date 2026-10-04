"""Roomora Frontend Web Server (Django).

Usage:
    python frontend.py          # Run without auto-reload on http://127.0.0.1:8000
    python frontend.py --reload # Run with auto-reload on file changes
"""
import os
import sys

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
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
