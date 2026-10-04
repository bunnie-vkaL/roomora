"""Minimal HTTPS transactional email adapter; never log message or credentials."""
import html
import json
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail.backends.base import BaseEmailBackend
from django.core.validators import validate_email
from django.utils import timezone

from .auth_limits import consume


class EmailDeliveryError(Exception):
    """Generic error safe to log without reset links or provider response bodies."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def mailbox(value):
    if "\r" in value or "\n" in value:
        raise EmailDeliveryError("Invalid email header.")
    name, address = parseaddr(value)
    try:
        validate_email(address)
    except ValidationError:
        raise EmailDeliveryError("Invalid email address.") from None
    return {"email": address, **({"name": name} if name else {})}


class BrevoEmailBackend(BaseEmailBackend):
    endpoint = "https://api.brevo.com/v3/smtp/email"

    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages or []:
            if not message.recipients():
                continue
            try:
                self.send_one(message)
            except EmailDeliveryError:
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent

    def send_one(self, message):
        if message.attachments or message.extra_headers or len(message.reply_to) > 1:
            raise EmailDeliveryError("Unsupported transactional email content.")
        if "\r" in message.subject or "\n" in message.subject:
            raise EmailDeliveryError("Invalid email header.")
        payload = {"sender": mailbox(message.from_email), "subject": message.subject,
                   "htmlContent": message.body if message.content_subtype == "html" else
                   "<div>" + html.escape(message.body).replace("\n", "<br>") + "</div>"}
        if message.content_subtype != "html":
            payload["textContent"] = message.body
        for alternative in getattr(message, "alternatives", []):
            if alternative[1] != "text/html":
                raise EmailDeliveryError("Unsupported transactional email alternative.")
            payload["htmlContent"] = alternative[0]
        for attribute in ("to", "cc", "bcc"):
            addresses = getattr(message, attribute)
            if addresses:
                payload[attribute] = [mailbox(value) for value in addresses]
        if message.reply_to:
            payload["replyTo"] = mailbox(message.reply_to[0])
        key = getattr(settings, "BREVO_API_KEY", "")
        if not key:
            raise EmailDeliveryError("Transactional email is not configured.")
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode("utf-8"),
            headers={"api-key": key, "Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        try:
            limit = getattr(settings, "ROOMORA_EMAIL_DAILY_LIMIT", 0)
            if limit and not consume("email-send", ["transactional"], limit, 86400, timezone.now())[0]:
                raise EmailDeliveryError("Transactional email daily limit reached.")
            # No redirects or automatic retries: a timeout may follow acceptance.
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=settings.EMAIL_TIMEOUT) as response:
                if response.status != 201:
                    raise EmailDeliveryError("Transactional email was not accepted.")
                result = json.loads(response.read(65536).decode("utf-8"))
                if not result.get("messageId"):
                    raise EmailDeliveryError("Transactional email acceptance is unconfirmed.")
        except EmailDeliveryError:
            raise
        except Exception:
            raise EmailDeliveryError("Transactional email is temporarily unavailable.") from None
