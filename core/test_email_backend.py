import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

from django.core import mail
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import SimpleTestCase, TestCase, override_settings

from .email_backend import BrevoEmailBackend, EmailDeliveryError, NoRedirect
from .tests import profile


SETTINGS = {"EMAIL_BACKEND": "core.email_backend.BrevoEmailBackend", "EMAIL_TIMEOUT": 10,
            "BREVO_API_KEY": "FAKE-TEST-KEY", "ROOMORA_EMAIL_DAILY_LIMIT": 0,
            "DEFAULT_FROM_EMAIL": "Roomora <sender@example.com>"}


def accepted_opener():
    opener = MagicMock()
    response = opener.open.return_value.__enter__.return_value
    response.status = 201
    response.read.return_value = b'{"messageId":"fake-message-id"}'
    return opener


@override_settings(**SETTINGS)
class EmailTransportTests(SimpleTestCase):
    def test_https_payload_preserves_vietnamese_plain_html_and_bcc(self):
        message = EmailMultiAlternatives("Đặt lại mật khẩu", "Một liên kết <riêng>\nDòng mới",
            to=["Recipient <recipient@example.com>"], cc=["cc@example.com"],
            bcc=["private@example.com"], reply_to=["reply@example.com"])
        message.attach_alternative("<p>Nội dung tiếng Việt</p>", "text/html")
        opener = accepted_opener()
        with patch("core.email_backend.urllib.request.build_opener", return_value=opener):
            self.assertEqual(message.send(), 1)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 10)
        self.assertEqual(request.get_header("Api-key"), "FAKE-TEST-KEY")
        payload = json.loads(request.data)
        self.assertEqual(payload["sender"], {"name": "Roomora", "email": "sender@example.com"})
        self.assertEqual(payload["subject"], message.subject)
        self.assertEqual(payload["textContent"], message.body)
        self.assertEqual(payload["htmlContent"], "<p>Nội dung tiếng Việt</p>")
        self.assertEqual(payload["bcc"], [{"email": "private@example.com"}])
        self.assertNotIn("private@example.com", json.dumps(payload["to"]))

    def test_plain_text_is_html_escaped_and_empty_recipients_do_not_send(self):
        opener = accepted_opener()
        with patch("core.email_backend.urllib.request.build_opener", return_value=opener):
            self.assertEqual(EmailMessage("Title", "<script>\n&", to=["a@example.com"]).send(), 1)
            self.assertEqual(EmailMessage("Title", "Body").send(), 0)
        self.assertEqual(json.loads(opener.open.call_args.args[0].data)["htmlContent"], "<div>&lt;script&gt;<br>&amp;</div>")
        self.assertEqual(opener.open.call_count, 1)

    def test_http_quota_and_timeout_errors_are_generic_and_not_retried(self):
        errors = [TimeoutError("SECRET reset-token"),
            urllib.error.HTTPError("https://api.brevo.com", 429, "SECRET body", {}, io.BytesIO(b"SECRET provider body"))]
        for error in errors:
            opener = accepted_opener()
            opener.open.side_effect = error
            with patch("core.email_backend.urllib.request.build_opener", return_value=opener):
                with self.assertRaises(EmailDeliveryError) as caught:
                    EmailMessage("Reset", "SECRET reset-token", to=["a@example.com"]).send()
            self.assertNotIn("SECRET", str(caught.exception))
            self.assertEqual(opener.open.call_count, 1)
        opener = accepted_opener()
        opener.open.side_effect = TimeoutError()
        with patch("core.email_backend.urllib.request.build_opener", return_value=opener):
            self.assertEqual(EmailMessage("Reset", "Body", to=["a@example.com"]).send(fail_silently=True), 0)

    def test_invalid_ack_or_unsupported_content_is_not_reported_as_sent(self):
        for data in (b"{}", b"not-json", b"[]"):
            opener = accepted_opener()
            opener.open.return_value.__enter__.return_value.read.return_value = data
            with patch("core.email_backend.urllib.request.build_opener", return_value=opener):
                with self.assertRaises(EmailDeliveryError):
                    EmailMessage("Reset", "Body", to=["a@example.com"]).send()
        message = EmailMessage("Reset", "Body", to=["a@example.com"])
        message.attach("file.txt", "must not disappear", "text/plain")
        with patch("core.email_backend.urllib.request.build_opener") as transport:
            with self.assertRaises(EmailDeliveryError):
                message.send()
            transport.assert_not_called()
        with self.assertRaises(EmailDeliveryError):
            EmailMessage("Header\ninjection", "Body", to=["a@example.com"]).send()
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other.example"))


@override_settings(**{**SETTINGS, "ROOMORA_EMAIL_DAILY_LIMIT": 1,
                      "PASSWORD_HASHERS": ["django.contrib.auth.hashers.MD5PasswordHasher"]})
class EmailIntegrationTests(TestCase):
    def test_daily_budget_is_shared_between_backend_instances(self):
        opener = accepted_opener()
        with patch("core.email_backend.urllib.request.build_opener", return_value=opener):
            message = EmailMessage("Title", "Body", to=["a@example.com"])
            self.assertEqual(BrevoEmailBackend().send_messages([message]), 1)
            with self.assertRaises(EmailDeliveryError):
                BrevoEmailBackend().send_messages([message])
        self.assertEqual(opener.open.call_count, 1)

    def test_reset_known_unknown_and_delivery_failure_have_same_response(self):
        profile("reset-backend@example.com")
        opener = accepted_opener()
        with patch("core.email_backend.urllib.request.build_opener", return_value=opener):
            known = self.client.post("/password-reset/", {"email": "reset-backend@example.com"}, follow=True)
            payload = json.loads(opener.open.call_args.args[0].data)
            self.assertIn("/reset/", payload["textContent"])
            self.assertEqual(payload["to"], [{"email": "reset-backend@example.com"}])
            unknown = self.client.post("/password-reset/", {"email": "unknown@example.com"}, follow=True)
            with self.assertLogs("django.contrib.auth", level="ERROR") as logs:
                failed = self.client.post("/password-reset/", {"email": "reset-backend@example.com"}, follow=True)
        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.content, unknown.content)
        self.assertEqual(known.content, failed.content)
        self.assertNotContains(failed, "/reset/")
        self.assertNotIn("FAKE-TEST-KEY", "\n".join(logs.output))
        self.assertNotIn("/reset/", "\n".join(logs.output))
        self.assertEqual(opener.open.call_count, 1)
