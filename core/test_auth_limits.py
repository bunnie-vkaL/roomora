from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import DatabaseError, connection, connections
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .auth_limits import client_address, consume
from .models import AuthRateBucket
from .tests import profile


RULES = {"login": {"seconds": 900, "ip": 4, "identity_ip": 2},
         "register": {"seconds": 900, "ip": 2},
         "password_reset": {"seconds": 900, "ip": 4, "identity_ip": 2}}


@override_settings(ROOMORA_AUTH_LIMITS=RULES, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthLimitTests(TestCase):
    def test_login_identity_normalization_ip_budget_and_forwarded_header_spoof(self):
        for username in ("Abuse@TEST.com", " abuse@test.COM "):
            self.assertEqual(self.client.post("/login/", {"username": username, "password": "bad"}).status_code, 200)
        response = self.client.post("/login/", {"username": "abuse@test.com", "password": "bad"},
                                    HTTP_X_FORWARDED_FOR="198.51.100.1", HTTP_X_ROOMORA_CLIENT_IP="198.51.100.1")
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response["Retry-After"]), 0)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotContains(response, "abuse@test.com", status_code=429)
        self.assertEqual(self.client.post("/login/", {"username": "different", "password": "bad"}).status_code, 200)
        self.assertEqual(self.client.post("/login/", {"username": "third", "password": "bad"}).status_code, 429)
        self.assertTrue(all(len(key) == 64 for key in AuthRateBucket.objects.values_list("key", flat=True)))

    def test_normal_login_works_and_other_ip_is_independent(self):
        profile("normal@test.com")
        self.assertEqual(self.client.post("/login/", {"username": "normal@test.com", "password": "strong-password-123"}).status_code, 302)
        for _ in range(4):
            Client().post("/login/", {"username": "unknown", "password": "bad"}, REMOTE_ADDR="192.0.2.1")
        self.assertEqual(Client().post("/login/", {"username": "unknown", "password": "bad"}, REMOTE_ADDR="192.0.2.2").status_code, 200)

    def test_reset_and_register_are_limited_before_side_effects(self):
        with patch("django.contrib.auth.forms.PasswordResetForm.send_mail") as send:
            profile("reset-limit@test.com")
            for _ in range(2):
                self.assertEqual(self.client.post("/password-reset/", {"email": "reset-limit@test.com"}).status_code, 302)
            self.assertEqual(self.client.post("/password-reset/", {"email": "reset-limit@test.com"}).status_code, 429)
            self.assertEqual(send.call_count, 2)
        for _ in range(2):
            self.assertEqual(self.client.post("/register/", {}).status_code, 200)
        self.assertEqual(self.client.post("/register/", {}).status_code, 429)

    def test_get_does_not_consume_and_database_failure_denies_post(self):
        self.client.get("/login/")
        self.assertFalse(AuthRateBucket.objects.exists())
        with patch("core.auth_limits.consume", side_effect=DatabaseError("SECRET-HOST")):
            response = self.client.post("/login/", {"username": "x", "password": "x"})
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, "SECRET-HOST", status_code=503)

    def test_window_expiry_and_cleanup_do_not_delete_current_bucket(self):
        now = timezone.now()
        self.assertTrue(consume("test", ["ip"], 1, 900, now)[0])
        self.assertFalse(consume("test", ["ip"], 1, 900, now)[0])
        self.assertTrue(consume("test", ["ip"], 1, 900, now + timedelta(seconds=900))[0])
        AuthRateBucket.objects.create(key="expired", expires_at=now - timedelta(seconds=1))
        call_command("prune_auth_limits", stdout=StringIO())
        self.assertFalse(AuthRateBucket.objects.filter(pk="expired").exists())
        self.assertEqual(AuthRateBucket.objects.count(), 2)

    @override_settings(ROOMORA_AUTH_TRUSTED_PROXIES=["10.0.0.0/24"])
    def test_client_header_is_only_used_from_explicit_trusted_peer(self):
        factory = RequestFactory()
        request = factory.post("/login/", REMOTE_ADDR="192.0.2.1", HTTP_X_ROOMORA_CLIENT_IP="198.51.100.5")
        self.assertEqual(client_address(request), "192.0.2.1")
        request.META["REMOTE_ADDR"] = "10.0.0.1"
        self.assertEqual(client_address(request), "198.51.100.5")
        request.META["HTTP_X_ROOMORA_CLIENT_IP"] = "invalid, spoofed"
        self.assertEqual(client_address(request), "10.0.0.1")

    def test_admin_login_uses_same_protection(self):
        for _ in range(2):
            self.assertEqual(self.client.post("/admin/login/", {"username": "bad", "password": "bad"}).status_code, 200)
        self.assertEqual(self.client.post("/admin/login/", {"username": "bad", "password": "bad"}).status_code, 429)


class AuthLimitConcurrencyTests(TransactionTestCase):
    def test_shared_counter_never_admits_more_than_limit(self):
        if connection.vendor == "sqlite" and str(connection.settings_dict["NAME"]).startswith("file:memory"):
            self.skipTest("Use config.test_settings for file-backed SQLite concurrency.")
        now = timezone.now()
        def attempt(_):
            connections.close_all()
            try:
                return consume("parallel", ["same-address"], 3, 900, now)[0]
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=6) as workers:
            accepted = list(workers.map(attempt, range(12)))
        self.assertEqual(sum(accepted), 3)
        self.assertEqual(AuthRateBucket.objects.get().attempts, 3)
