import os
import subprocess
import sys
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase, SimpleTestCase
from django.urls import reverse


class HealthTests(TestCase):
    def test_probes_are_get_only_and_uncached(self):
        for name in ("health-live", "health-ready"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok"})
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(self.client.post(reverse(name)).status_code, 405)

    def test_db_outage_does_not_leak_exception_or_break_liveness(self):
        with patch("config.health.connection.cursor", side_effect=DatabaseError("SECRET-DATABASE-HOST")):
            response = self.client.get(reverse("health-ready"))
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"status": "unavailable"})
            self.assertEqual(self.client.get(reverse("health-live")).status_code, 200)


class ProductionSettingsTests(SimpleTestCase):
    def load_settings(self, overrides=None):
        from pathlib import Path
        env = {key: value for key, value in os.environ.items() if key in
               ("PATH", "SystemRoot", "SYSTEMROOT", "TEMP", "TMP", "WINDIR")}
        env.update({"DJANGO_SETTINGS_MODULE": "config.production_settings",
            "SECRET_KEY": "config-test-only-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyz",
            "ALLOWED_HOSTS": "roomora.example", "CSRF_TRUSTED_ORIGINS": "https://roomora.example",
            "POSTGRES_DB": "test", "POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test",
            "POSTGRES_HOST": "database.example", "EMAIL_HOST": "smtp.example",
            "EMAIL_HOST_USER": "test", "EMAIL_HOST_PASSWORD": "test",
            "DEFAULT_FROM_EMAIL": "hello@roomora.example",
            "STATIC_ROOT": str(Path.cwd() / "staticfiles"), "MEDIA_ROOT": str(Path.cwd() / "media"),
            "ROOMORA_PRIVATE_MEDIA_ROOT": str(Path.cwd() / "private_media")})
        env.update(overrides or {})
        return subprocess.run([sys.executable, "-c", "from config import production_settings as s; "
            "assert not s.DEBUG; assert s.DATABASES['default']['ENGINE'].endswith('postgresql'); "
            "assert s.EMAIL_USE_TLS; assert s.SECURE_PROXY_SSL_HEADER is None; print('valid')"],
            env=env, capture_output=True, text=True)

    def test_valid_environment_has_no_local_dotenv_overrides(self):
        result = self.load_settings()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "valid")

    def test_unsafe_or_incomplete_configuration_fails_startup(self):
        from pathlib import Path
        for overrides in ({"SECRET_KEY": "replace-me"}, {"POSTGRES_PASSWORD": ""},
                          {"ALLOWED_HOSTS": "*"}, {"CSRF_TRUSTED_ORIGINS": "http://roomora.example"},
                          {"ROOMORA_PRIVATE_MEDIA_ROOT": str(Path.cwd() / "media" / "evidence")},
                          {"EMAIL_HOST_PASSWORD": ""}):
            with self.subTest(overrides=list(overrides)):
                self.assertNotEqual(self.load_settings(overrides).returncode, 0)

    def test_auth_proxy_requires_explicit_valid_network(self):
        for value in ("0.0.0.0/0", "::/0", "not-a-network"):
            self.assertNotEqual(self.load_settings({"ROOMORA_AUTH_TRUSTED_PROXIES": value}).returncode, 0)
        self.assertEqual(self.load_settings({"ROOMORA_AUTH_TRUSTED_PROXIES": "10.0.0.0/24"}).returncode, 0)


class FreeBetaSettingsTests(SimpleTestCase):
    def run_profile(self, overrides=None, rehearsal=False):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory(prefix="roomora-free-test-") as folder:
            root = Path(folder)
            (root / "data").mkdir()
            env = {key: value for key, value in os.environ.items() if key in
                   ("PATH", "SystemRoot", "SYSTEMROOT", "TEMP", "TMP", "WINDIR")}
            env.update({"DJANGO_SETTINGS_MODULE": "config.free_beta_settings", "DEBUG": "True",
                "SECRET_KEY": "config-test-only-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyz",
                "ALLOWED_HOSTS": "roomora.pythonanywhere.com", "CSRF_TRUSTED_ORIGINS": "https://roomora.pythonanywhere.com",
                "DEFAULT_FROM_EMAIL": "sender@example.com", "BREVO_API_KEY": "FAKE-TEST-KEY",
                "STATIC_ROOT": str(root / "static"), "MEDIA_ROOT": str(root / "media"),
                "ROOMORA_PRIVATE_MEDIA_ROOT": str(root / "private"), "ROOMORA_DATA_ROOT": str(root / "data")})
            for key, value in (overrides or {}).items():
                env[key] = value.replace("{root}", str(root))
            code = "from config import free_beta_settings as s; "
            code += "assert not s.DEBUG; assert s.DATABASES['default']['ENGINE'].endswith('sqlite3'); "
            code += "assert s.EMAIL_BACKEND=='core.email_backend.BrevoEmailBackend'; assert s.ROOMORA_EMAIL_DAILY_LIMIT==250; "
            code += "assert s.SECURE_SSL_REDIRECT and s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE; "
            if rehearsal:
                code += "import django; django.setup(); from django.core.management import call_command; "
                code += "from django.core.checks import run_checks; assert {c.id for c in run_checks(include_deployment_checks=True)} == {'security.W005','security.W021'}; "
                code += "call_command('check', deploy=True, fail_level='ERROR'); call_command('migrate', verbosity=0); "
                code += "from django.test import Client; c=Client(); assert c.get('/health/ready/', secure=True, HTTP_HOST='roomora.pythonanywhere.com').status_code==200; "
                code += "assert c.get('/login/', secure=True, HTTP_HOST='roomora.pythonanywhere.com').status_code==200; "
                code += "assert c.get('/login/', HTTP_HOST='roomora.pythonanywhere.com').status_code==301; "
            code += "print('valid')"
            return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)

    def test_secure_free_profile_boots_and_migrates_without_paid_dependencies(self):
        result = self.run_profile(rehearsal=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.rstrip().endswith("valid"), result.stdout)

    def test_free_profile_rejects_missing_key_and_exposed_or_overlapping_data(self):
        for overrides in ({"BREVO_API_KEY": ""}, {"SECRET_KEY": "short"},
                          {"ROOMORA_DATA_ROOT": "{root}/media/data"},
                          {"ROOMORA_PRIVATE_MEDIA_ROOT": "{root}/media/../media/private"},
                          {"MEDIA_ROOT": "{root}/static/media"}, {"ROOMORA_DATA_ROOT": "relative/data"}):
            self.assertNotEqual(self.run_profile(overrides).returncode, 0)
