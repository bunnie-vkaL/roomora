from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import uuid
from unittest.mock import patch

from django.db import DatabaseError, connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from core.models import AuthRateBucket
from core.storage import UploadCapacityError
from core.tests import profile
from . import models as m, services as s


NOW = datetime(2026, 10, 4, 0, 0, 10, tzinfo=timezone.utc)
LIMITS = {"message": ({"limit": 1, "seconds": 60},)}


@override_settings(ROOMORA_MUTATION_LIMITS=LIMITS, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MutationRateTests(TestCase):
    def setUp(self):
        self.a, self.b = profile("limit-a@example.invalid"), profile("limit-b@example.invalid")
        s.decide(self.a, self.b, "like")
        self.conversation = s.decide(self.b, self.a, "like")

    def send(self, actor, key=None):
        client_id = uuid.uuid4()
        return s.run_mutation(actor, "message", key or uuid.uuid4(), {"client_id": str(client_id)},
            lambda: {"message": s.send_message(actor, self.conversation.pk, "Nội dung thử", client_id).pk})

    def test_retry_replays_receipt_without_spending_or_sending_twice(self):
        key, client_id = uuid.uuid4(), uuid.uuid4()
        payload = {"client_id": str(client_id)}
        operation = lambda: {"message": s.send_message(self.a, self.conversation.pk, "Tin duy nhất", client_id).pk}
        with patch("journey.rate_limits.timezone.now", return_value=NOW):
            result = s.run_mutation(self.a, "message", key, payload, operation)
            self.assertEqual(s.run_mutation(self.a, "message", key, payload, operation), result)
            with self.assertRaises(s.DomainError) as rejected:
                self.send(self.a)
            self.assertEqual(rejected.exception.status, 429)
            self.assertEqual(rejected.exception.retry_after, 50)
            with self.assertRaises(s.DomainError) as conflict:
                s.run_mutation(self.a, "message", key, {"client_id": "different"}, operation)
            self.assertEqual(conflict.exception.status, 409)
            self.send(self.b)
        self.assertEqual(m.Message.objects.count(), 2)
        self.assertEqual(m.MutationReceipt.objects.filter(actor=self.a).count(), 1)
        self.assertEqual(sorted(AuthRateBucket.objects.values_list("attempts", flat=True)), [1, 1])

    def test_failed_domain_and_storage_work_roll_back_but_attempt_stays_counted(self):
        for error in (s.DomainError("Dữ kiện cần sửa"), UploadCapacityError()):
            with self.subTest(error=type(error).__name__):
                AuthRateBucket.objects.all().delete()
                def fail():
                    m.RoomOption.objects.create(owner=self.a, title="Không được lưu")
                    s.emit([self.b.pk], "Không được gửi", "/together/")
                    raise error
                before_events = m.OutboxEvent.objects.count()
                with patch("journey.rate_limits.timezone.now", return_value=NOW):
                    with self.assertRaises(type(error)):
                        s.run_mutation(self.a, "message", uuid.uuid4(), {}, fail)
                    with self.assertRaises(s.DomainError) as rejected:
                        self.send(self.a)
                self.assertEqual(rejected.exception.status, 429)
                self.assertFalse(m.RoomOption.objects.exists())
                self.assertEqual(m.OutboxEvent.objects.count(), before_events)
                self.assertFalse(m.MutationReceipt.objects.exists())
                self.assertEqual(AuthRateBucket.objects.get().attempts, 1)

    def test_fixed_window_recovers_and_json_response_has_retry_header(self):
        self.client.force_login(self.a.user)
        path = reverse("journey:action", args=["message"])
        def post():
            return self.client.post(path, {"conversation": self.conversation.pk, "body": "Tin thử",
                "client_id": uuid.uuid4(), "mutation_key": uuid.uuid4()}, secure=True, HTTP_ACCEPT="application/json")
        with patch("journey.rate_limits.timezone.now", return_value=NOW):
            self.assertEqual(post().status_code, 200)
            limited = post()
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited["Retry-After"], "50")
        self.assertEqual(limited.json()["retry_after"], 50)
        self.assertEqual(limited["Cache-Control"], "no-store")
        next_window = NOW.replace(minute=1)
        with patch("journey.rate_limits.timezone.now", return_value=next_window):
            self.assertEqual(post().status_code, 200)
        self.assertEqual(m.Message.objects.count(), 2)

    @override_settings(ROOMORA_MUTATION_LIMITS={"all": ({"limit": 1, "seconds": 3600},), "report": ({"limit": 1, "seconds": 3600},)})
    def test_block_and_report_remain_available_after_normal_budget_is_exhausted(self):
        self.client.force_login(self.a.user)
        self.send(self.a)
        report = self.client.post(reverse("journey:action", args=["report"]), {"target": self.b.pk,
            "reason": "Báo cáo thử", "mutation_key": uuid.uuid4()}, secure=True, HTTP_ACCEPT="application/json")
        self.assertEqual(report.status_code, 200)
        blocked = self.client.post(reverse("journey:action", args=["block"]), {"target": self.b.pk,
            "mutation_key": uuid.uuid4()}, secure=True, HTTP_ACCEPT="application/json")
        self.assertEqual(blocked.status_code, 200)
        self.assertTrue(s.is_blocked(self.a, self.b))
        self.assertFalse(m.Connection.objects.get().active)
        self.assertEqual(m.Report.objects.count(), 1)

    def test_counter_database_failure_stops_operation_without_leaking_detail(self):
        self.client.force_login(self.a.user)
        with patch("journey.rate_limits.consume", side_effect=DatabaseError("PRIVATE-DATABASE-MARKER")):
            with self.assertLogs("journey.services", level="ERROR") as logs:
                response = self.client.post(reverse("journey:action", args=["message"]), {
                    "conversation": self.conversation.pk, "body": "Không được gửi", "client_id": uuid.uuid4(),
                    "mutation_key": uuid.uuid4()}, secure=True, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "60")
        self.assertNotIn("PRIVATE-DATABASE-MARKER", response.content.decode() + " ".join(logs.output))
        self.assertFalse(m.Message.objects.exists())
        self.assertFalse(m.MutationReceipt.objects.exists())

    @override_settings(ROOMORA_MUTATION_LIMITS={"all": ({"limit": 1, "seconds": 3600},)})
    def test_negative_responses_can_revoke_real_consent_after_exhaustion(self):
        invite = s.invite_workspace(self.a, self.conversation.pk, "Bảng nhà thử")
        workspace = s.respond_workspace(self.b, invite.pk, True)
        room = m.RoomOption.objects.create(owner=self.a, workspace=workspace, title="Căn thử")
        for period in ("monthly", "initial", "deposit"):
            room.costs.create(label=period, period=period, state="known", amount=100, source="Nguồn thử")
        scenario = s.save_scenario(self.a, room.pk, room.version, {str(self.a.pk): 1, str(self.b.pk): 1})
        proposal = s.propose_room(self.a, room.pk, scenario.room_version)
        for actor in (self.a, self.b):
            s.consent_choice(actor, proposal.pk, proposal.room_version)
        agreement = s.save_agreement(self.a, workspace.pk, {key: "Đã trao đổi" for key in s.CLAUSES}, 0)
        for actor in (self.a, self.b):
            for key in s.CLAUSES:
                m.ClauseResponse.objects.create(agreement=agreement, member=actor, key=key, version=agreement.version, accepted=True)
            s.consent_agreement(actor, workspace.pk, agreement.version)
        plan = m.ViewingPlan.objects.create(room=room, author=self.b, at=NOW + timedelta(days=1), meeting_point="Điểm hẹn thử")
        m.ViewingResponse.objects.create(plan=plan, member=self.a, version=plan.version, accepted=True)
        third = profile("negative-invite@example.invalid")
        s.decide(self.a, third, "like")
        other_conversation = s.decide(third, self.a, "like")
        pending = s.invite_workspace(third, other_conversation.pk, "Chưa đồng ý")
        self.send(self.a)
        self.client.force_login(self.a.user)
        for action, data in (
            ("clause-response", {"workspace": workspace.pk, "clause": "quiet", "expected_version": agreement.version}),
            ("viewing-response", {"room": room.pk, "plan": plan.pk, "expected_version": plan.version}),
            ("workspace-response", {"workspace": pending.pk}),
        ):
            positive = self.client.post(reverse("journey:action", args=[action]), {**data, "accepted": "1", "mutation_key": uuid.uuid4()},
                secure=True, HTTP_ACCEPT="application/json")
            self.assertEqual(positive.status_code, 429)
            negative = self.client.post(reverse("journey:action", args=[action]), {**data, "accepted": "0", "mutation_key": uuid.uuid4()},
                secure=True, HTTP_ACCEPT="application/json")
            self.assertEqual(negative.status_code, 200, (action, negative.content.decode()))
        self.assertFalse(agreement.consents.filter(member=self.a).exists())
        self.assertFalse(plan.responses.get(member=self.a).accepted)
        pending.refresh_from_db()
        self.assertEqual(pending.status, "declined")


@override_settings(ROOMORA_MUTATION_LIMITS={"message": ({"limit": 2, "seconds": 60},)},
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrentMutationRateTests(TransactionTestCase):
    def setUp(self):
        if "memory" in str(connection.settings_dict["NAME"]):
            self.skipTest("Use config.test_settings to verify file-backed SQLite concurrency.")

    def test_simultaneous_unique_sends_never_exceed_actor_limit(self):
        actor, other = profile("concurrent-limit-a@example.invalid"), profile("concurrent-limit-b@example.invalid")
        s.decide(actor, other, "like")
        conversation = s.decide(other, actor, "like")
        def send(index):
            try:
                client_id = uuid.uuid4()
                s.run_mutation(actor, "message", uuid.uuid4(), {"index": index},
                    lambda: {"id": s.send_message(actor, conversation.pk, "Thử đồng thời", client_id).pk})
                return True
            except s.DomainError as error:
                self.assertEqual(error.status, 429)
                return False
            finally:
                connections.close_all()
        with patch("journey.rate_limits.timezone.now", return_value=NOW), ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(send, range(8)))
        self.assertEqual(sum(results), 2)
        self.assertEqual(m.Message.objects.count(), 2)
        self.assertEqual(m.MutationReceipt.objects.count(), 2)
        self.assertEqual(AuthRateBucket.objects.get().attempts, 2)
