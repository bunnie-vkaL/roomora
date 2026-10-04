from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

from django.apps import apps
from django.db import connection, connections
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.tests import profile
from . import models as m, services as s


@override_settings(ROOMORA_JOURNEY_ENABLED=True, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NotificationDeliveryTests(TestCase):
    def setUp(self):
        self.a = profile("notify-a@test.com")
        self.b = profile("notify-b@test.com")

    def test_committed_event_is_delivered_without_worker(self):
        with self.captureOnCommitCallbacks(execute=True):
            event = s.emit([self.a.pk], "Immediate notification", reverse("journey:hub"))
        event.refresh_from_db()
        self.assertTrue(event.delivered)
        self.assertEqual(m.Notification.objects.filter(event=event, profile=self.a).count(), 1)

    def test_next_page_retries_only_this_reader_due_events_and_deduplicates(self):
        own = s.emit([self.a.pk], "Own retry", reverse("journey:hub"))
        unrelated = s.emit([self.b.pk], "Unrelated retry", reverse("journey:hub"))
        self.client.force_login(self.a.user)
        response = self.client.get(reverse("journey:notifications"))
        self.assertContains(response, "Own retry")
        self.assertNotContains(response, "Unrelated retry")
        self.client.get(reverse("journey:notifications"))
        self.assertEqual(m.Notification.objects.filter(event=own, profile=self.a).count(), 1)
        unrelated.refresh_from_db()
        self.assertFalse(unrelated.delivered)
        self.assertFalse(m.Notification.objects.filter(event=unrelated).exists())

    def test_batch_is_bounded_and_failure_backoff_does_not_starve_following_events(self):
        events = [s.emit([self.a.pk], f"Event {index}", reverse("journey:hub")) for index in range(12)]
        original = s.deliver_event
        def fail_first(event_id):
            if event_id == events[0].pk:
                raise RuntimeError("PRIVATE-CONTENT-NOT-FOR-LOGS")
            return original(event_id)
        with patch("journey.services.deliver_event", side_effect=fail_first) as delivery:
            with self.assertLogs("journey.services", level="ERROR") as logs:
                self.assertEqual(s.retry_outbox_for(self.a), 9)
            self.assertEqual(delivery.call_count, 10)
        self.assertNotIn("PRIVATE-CONTENT", "\n".join(logs.output))
        events[0].refresh_from_db()
        self.assertEqual(events[0].delivery_attempts, 1)
        self.assertGreater(events[0].retry_at, timezone.now())
        self.assertEqual(s.retry_outbox_for(self.a), 2)
        self.assertEqual(m.Notification.objects.count(), 11)
        m.OutboxEvent.objects.filter(pk=events[0].pk).update(retry_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(s.retry_outbox_for(self.a), 1)
        self.assertEqual(m.Notification.objects.count(), 12)

    def test_multiple_template_calls_retry_at_most_once_per_request(self):
        from .context import navigation
        request = RequestFactory().get("/profile/")
        request.user = self.a.user
        with patch("journey.services.retry_outbox_for") as retry:
            navigation(request)
            navigation(request)
        retry.assert_called_once()

    def test_index_backfill_preserves_old_event_payload_and_skips_deleted_profiles(self):
        old = m.OutboxEvent.objects.create(recipients=[self.a.pk, self.a.pk, 999999], title="Old event", path="/together/")
        migration = import_module("journey.migrations.0002_scoped_notification_retries")
        migration.populate_recipient_index(apps, SimpleNamespace(connection=connection))
        migration.populate_recipient_index(apps, SimpleNamespace(connection=connection))
        self.assertEqual(m.OutboxRecipient.objects.filter(event=old).count(), 1)
        old.refresh_from_db()
        self.assertEqual(old.recipients, [self.a.pk, self.a.pk, 999999])
        self.assertEqual(s.retry_outbox_for(self.a), 1)

    def test_workspace_notifications_and_count_are_hidden_after_block(self):
        s.decide(self.a, self.b, "like")
        conversation = s.decide(self.b, self.a, "like")
        workspace = s.invite_workspace(self.a, conversation.pk, "Cùng tìm")
        s.respond_workspace(self.b, workspace.pk, True)
        event = s.emit([self.a.pk], "PRIVATE-WORKSPACE-UPDATE", "/together/", workspace)
        s.deliver_event(event.pk)
        self.assertTrue(s.visible_notifications(self.a).filter(event=event).exists())
        # A legacy block can be added independently of workspace status.
        from core.models import ConnectionRequest
        ConnectionRequest.objects.create(sender=self.b, recipient=self.a, status="blocked")
        self.assertFalse(s.visible_notifications(self.a).filter(event=event).exists())
        self.client.force_login(self.a.user)
        self.assertNotContains(self.client.get(reverse("journey:notifications")), "PRIVATE-WORKSPACE-UPDATE")

    def test_operator_retry_continues_after_failure_and_returns_error_status(self):
        first = s.emit([self.a.pk], "First", "/together/")
        second = s.emit([self.a.pk], "Second", "/together/")
        original = s.deliver_event
        def fail_first(event_id):
            if event_id == first.pk:
                raise RuntimeError("temporary")
            return original(event_id)
        with patch("journey.services.deliver_event", side_effect=fail_first):
            with self.assertLogs("journey.services", level="ERROR"):
                with self.assertRaises(CommandError):
                    call_command("deliver_notifications", limit=2, stdout=StringIO())
        second.refresh_from_db()
        self.assertTrue(second.delivered)
        with self.assertRaises(CommandError):
            call_command("deliver_notifications", limit=501, stdout=StringIO())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NotificationConcurrencyTests(TransactionTestCase):
    def test_parallel_delivery_creates_one_notification(self):
        if connection.vendor == "sqlite" and str(connection.settings_dict["NAME"]).startswith("file:memory"):
            self.skipTest("Use config.test_settings for file-backed concurrency.")
        actor = profile("parallel-notify@test.com")
        event = m.OutboxEvent.objects.create(recipients=[actor.pk], title="Parallel", path="/together/")
        def deliver(_):
            connections.close_all()
            try:
                s.deliver_event(event.pk)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=6) as workers:
            list(workers.map(deliver, range(12)))
        self.assertEqual(m.Notification.objects.filter(event=event, profile=actor).count(), 1)
        event.refresh_from_db()
        self.assertTrue(event.delivered)
