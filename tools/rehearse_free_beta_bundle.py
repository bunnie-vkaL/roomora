"""Verify an extracted release with isolated state and no external HTTP/email."""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import uuid
from unittest.mock import patch
import zipfile

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from tools.build_free_beta_bundle import verify_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    options = parser.parse_args()
    archive = Path(options.archive).resolve(strict=True)
    root = Path(options.root).absolute()
    allowed = (SOURCE.parent / "private-fixtures").resolve()
    if root.exists() or not root.resolve().is_relative_to(allowed) or root.resolve() == allowed:
        raise ValueError("Use a new isolated directory inside workspace/private-fixtures.")
    manifest = verify_bundle(archive)
    root.mkdir(parents=True)
    app = root / "roomora"
    with zipfile.ZipFile(archive) as bundle:
        # Verifier rejected traversal/duplicates and validated the full inventory before extraction.
        for name in bundle.namelist():
            destination = root / name
            if not destination.resolve().is_relative_to(root.resolve()):
                raise ValueError("Release extraction escaped rehearsal root.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(bundle.read(name))
    host = "release-rehearsal.example.invalid"
    values = {"SECRET_KEY": secrets.token_urlsafe(64), "ALLOWED_HOSTS": host,
              "CSRF_TRUSTED_ORIGINS": "https://" + host, "DEFAULT_FROM_EMAIL": "test@example.invalid",
              "BREVO_API_KEY": "FAKE-REHEARSAL-NO-DELIVERY"}
    for key in ("STATIC_ROOT", "MEDIA_ROOT", "ROOMORA_PRIVATE_MEDIA_ROOT", "ROOMORA_DATA_ROOT"):
        folder = root / key.lower()
        folder.mkdir()
        values[key] = str(folder)
    private_env = root / "private-env.json"
    private_env.write_text(json.dumps(values), encoding="utf-8")
    private_env.chmod(0o600)
    process_env = {key: value for key, value in os.environ.items() if key in
                   ("PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")}
    cli_results = []
    for command in (("check", "--deploy"), ("migrate", "--noinput"), ("collectstatic", "--noinput")):
        result = subprocess.run([sys.executable, "deploy/free_beta.py", "--env", str(private_env), *command],
                                cwd=app, env=process_env, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError("Release management command failed; inspect it with the same private configuration.")
        if command[0] == "check" and any(marker in result.stderr for marker in ("ERRORS:", "security.W004", "security.W008", "security.W009", "security.W012", "security.W016")):
            raise RuntimeError("Unexpected deployment-check result.")
        cli_results.append({"command": command[0], "exit_code": result.returncode})
    # Imports can only find application source in the extracted release, not the checkout.
    sys.path = [str(app), *[value for value in sys.path if value and Path(value).resolve() not in (SOURCE, SOURCE / "tools")]]
    from deploy.free_beta import load_environment
    load_environment(private_env)
    from django.core.wsgi import get_wsgi_application
    from django.test import Client, RequestFactory
    from django.conf import settings
    from django.core.checks import run_checks
    application = get_wsgi_application()
    assert not settings.DEBUG
    assert {item.id for item in run_checks(include_deployment_checks=True)} == {"security.W005", "security.W021"}
    assert settings.DATABASES["default"]["OPTIONS"]["transaction_mode"] == "IMMEDIATE"
    request = RequestFactory().get("/health/ready/", secure=True, HTTP_HOST=host)
    response_meta = {}
    def start_response(status, headers, exc_info=None):
        response_meta.update(status=status, headers=dict(headers))
    with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No external HTTP in release rehearsal")):
        response = application(request.environ, start_response)
        body = b"".join(response)
        response.close()
        assert response_meta["status"] == "200 OK" and json.loads(body) == {"status": "ok"}
        assert "no-store" in response_meta["headers"]["Cache-Control"]
        client = Client(enforce_csrf_checks=True)
        pages = {}
        for path in ("/", "/about/", "/login/", "/register/"):
            result = client.get(path, secure=True, HTTP_HOST=host)
            assert result.status_code == 200
            pages[path] = result.status_code
        assert client.get("/health/ready/", HTTP_HOST=host).status_code == 301
        rejected = client.post("/register/", {"email": "test@example.invalid"}, secure=True, HTTP_HOST=host,
                               HTTP_REFERER="https://" + host + "/register/")
        assert rejected.status_code == 403
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        result = client.post("/register/", {"email": "release-user@example.invalid", "password1": "Local-rehearsal-2026!",
            "password2": "Local-rehearsal-2026!", "csrfmiddlewaretoken": token}, secure=True,
            HTTP_HOST=host, HTTP_REFERER="https://" + host + "/register/")
        assert result.status_code == 302
        assert client.cookies[settings.SESSION_COOKIE_NAME]["secure"]
        for path in ("/profile/", "/questionnaire/", "/together/", "/together/rooms/"):
            result = client.get(path, secure=True, HTTP_HOST=host)
            assert result.status_code == 200
            pages[path] = result.status_code
        from django.contrib.auth.models import User
        from core.constants import QUESTIONS
        from core.models import Profile, LifestyleAnswers
        from journey import models as journey, services
        actor = Profile.objects.get()
        actor.name, actor.age, actor.areas = "Release fixture A", 25, ["Cầu Giấy"]
        actor.rent_min, actor.rent_max, actor.is_published = 3000000, 5000000, True
        actor.save()
        user = User.objects.create_user("release-other@example.invalid", "release-other@example.invalid", "Local-rehearsal-2026!")
        other = Profile.objects.create(user=user, name="Release fixture B", age=25, areas=["Cầu Giấy"],
            rent_min=3000000, rent_max=5000000, contact_type="zalo", contact_value="fixture", is_published=True)
        for person in (actor, other):
            LifestyleAnswers.objects.update_or_create(profile=person, defaults={"values": {key: 0 for key, *_ in QUESTIONS}})
        services.decide(actor, other, "like")
        conversation = services.decide(other, actor, "like")
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        def mutation(action, data):
            return client.post("/together/action/" + action + "/", {"csrfmiddlewaretoken": token, **data},
                secure=True, HTTP_HOST=host, HTTP_REFERER="https://" + host + "/together/", HTTP_ACCEPT="application/json")
        with patch("journey.rate_limits.timezone.now", return_value=datetime(2026, 10, 4, 0, 0, 10, tzinfo=timezone.utc)):
            first_payload = None
            for index in range(30):
                payload = {"conversation": conversation.pk, "body": "Local release fixture message", "client_id": str(uuid.uuid4()), "mutation_key": str(uuid.uuid4())}
                if first_payload is None:
                    first_payload = payload
                assert mutation("message", payload).status_code == 200
            limited = mutation("message", {**first_payload, "client_id": str(uuid.uuid4()), "mutation_key": str(uuid.uuid4())})
            assert limited.status_code == 429 and limited["Retry-After"] == "50"
            assert limited.json()["retry_after"] == 50 and limited["Cache-Control"] == "no-store"
            assert mutation("message", first_payload).status_code == 200
            assert journey.Message.objects.count() == 30
            # The first rejected message consumed ordinary attempt 31. Fill the remaining allowance.
            for index in range(89):
                assert mutation("not-supported", {"mutation_key": str(uuid.uuid4())}).status_code == 404
            assert mutation("not-supported", {"mutation_key": str(uuid.uuid4())}).status_code == 429
            assert mutation("block", {"target": other.pk, "mutation_key": str(uuid.uuid4())}).status_code == 200
            assert services.is_blocked(actor, other)
        assert client.get(f"/together/chat/{conversation.pk}/messages/", secure=True, HTTP_HOST=host).status_code == 403
    from core.models import ImportedSampleProfile
    assert Profile.objects.count() == 2 and ImportedSampleProfile.objects.count() == 0
    assert not Profile.objects.filter(is_synthetic=True).exists()
    assert not any(path for folder in (settings.MEDIA_ROOT, settings.ROOMORA_PRIVATE_MEDIA_ROOT) for path in Path(folder).iterdir())
    assert (settings.STATIC_ROOT / "design.css").is_file()
    assert (settings.STATIC_ROOT / "chat-polling.js").is_file()
    module_origins = []
    for name, module in sys.modules.items():
        if name.split(".")[0] in ("config", "core", "journey", "deploy") and getattr(module, "__file__", None):
            assert Path(module.__file__).resolve().is_relative_to(app.resolve())
            module_origins.append(name)
    evidence = {"date": "2026-10-04", "public_website_verified": False, "provider_account_used": False,
        "archive_name": archive.name, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "archive_files": len(manifest["files"]), "archive_inventory_and_hashes_verified": True,
        "source_bytes": manifest["raw_source_bytes"], "base_git_head": manifest["base_git_head"],
        "environment": "Windows, existing local virtualenv; extracted package only for application source",
        "commands": cli_results, "wsgi_ready": "200 OK", "public_profile": "config.free_beta_settings",
        "debug": settings.DEBUG, "allowed_deployment_warnings": ["security.W005", "security.W021"],
        "routes": pages, "http_redirect": 301, "csrf_missing_token_rejected": 403,
        "registration_with_csrf": 302, "secure_session_cookie": True, "sample_profiles": 0,
        "fictional_accounts": 2,
        "public_message_limit": {"admitted": 30, "next_status": 429, "retry_after": 50},
        "receipt_replay_after_limit": 200, "messages_after_replay": 30,
        "ordinary_attempt_limit": {"admitted": 120, "next_status": 429},
        "block_after_ordinary_limit": 200, "messages_after_block_status": 403,
        "private_and_public_upload_roots_empty": True, "static_assets_collected": True,
        "application_modules_from_extracted_bundle": len(module_origins), "external_http_and_email": "disabled, not verified",
        "limitations": ["No PythonAnywhere/Linux worker or proxy exercised", "No real email or host capacity verified",
                        "No live database, user data or uploaded media transferred", "Browser UI and full journey on provider remain required"]}
    output = Path(options.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(evidence, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"rehearsal_passed": True, "archive_files": len(manifest["files"]), "routes": len(pages),
                      "public_website_verified": False}))


if __name__ == "__main__":
    main()
