"""Roomora Unified Runner.

Runs both the FastAPI backend (api.py) and the Django frontend (frontend.py)
concurrently as managed subprocesses.

Usage:
    python run.py          # Run both without auto-reload
    python run.py --reload # Run both with auto-reload enabled
    python run.py --production --workers 2 # Run Django + FastAPI via Gunicorn
"""
import os
import signal
import subprocess
import sys
import time
import argparse


def run_production():
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


def main():
    if "--production" in sys.argv:
        run_production()

    reload = "--reload" in sys.argv
    python_bin = sys.executable

    print("=" * 60)
    print("🚀 ROOMORA UNIFIED RUNNER")
    print("=" * 60)
    print("Frontend Web:    http://127.0.0.1:8000")
    print("FastAPI Backend: http://127.0.0.1:8001")
    print("Swagger UI Docs: http://127.0.0.1:8001/docs")
    print(f"Auto-reload:     {'Enabled' if reload else 'Disabled'}")
    print("Press Ctrl+C to terminate both servers.")
    print("=" * 60)

    api_cmd = [python_bin, "api.py"]
    frontend_cmd = [python_bin, "frontend.py"]
    if reload:
        api_cmd.append("--reload")
        frontend_cmd.append("--reload")

    api_proc = subprocess.Popen(api_cmd)
    time.sleep(0.5)
    frontend_proc = subprocess.Popen(frontend_cmd)

    def shutdown(signum=None, frame=None):
        print("\n🛑 Stopping ROOMORA servers...")
        for proc, name in [(api_proc, "API"), (frontend_proc, "Frontend")]:
            if proc.poll() is None:
                proc.terminate()
        for proc, name in [(api_proc, "API"), (frontend_proc, "Frontend")]:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("Both servers stopped cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        api_exit = api_proc.poll()
        frontend_exit = frontend_proc.poll()

        if api_exit is not None:
            print(f"API server exited with code {api_exit}")
            shutdown()
        if frontend_exit is not None:
            print(f"Frontend server exited with code {frontend_exit}")
            shutdown()

        time.sleep(0.5)


if __name__ == "__main__":
    main()
