"""Behavior and access-control tests for the complete roommate journey."""
import io
import random
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from core.models import ConnectionRequest, ImportedSampleProfile
from core.tests import profile
from . import forms as f, models as m, services as s
from .costs import calculate_shared_costs, split_amount


@override_settings(DEBUG=False, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DiscoveryQueryTests(TestCase):
    def setUp(self):
        self.actor = profile("query-actor@test.com")

    def test_switching_view_preserves_filters_cursor_and_ranked_profiles(self):
        from urllib.parse import parse_qs, urlsplit
        for index in range(25):
            profile(f"switch-{index}@test.com")
        self.client.force_login(self.actor.user)
        response = self.client.get(reverse("journey:discover"), {"view": "list", "area": "Cầu Giấy", "rent": "4000000"}, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "person-list-card")
        self.assertNotContains(response, "data-swipe-deck")
        second = self.client.get(reverse("journey:discover") + response.context["next_url"], secure=True)
        expected = [row["profile"].pk for row in second.context["cards"]]
        switch_query = parse_qs(urlsplit(second.context["swipe_url"]).query)
        self.assertEqual(switch_query["view"], ["swipe"])
        self.assertEqual(switch_query["area"], ["Cầu Giấy"])
        self.assertEqual(switch_query["rent"], ["4000000"])
        self.assertTrue(switch_query["cursor"])
        swipe = self.client.get(reverse("journey:discover") + second.context["swipe_url"], secure=True)
        self.assertEqual(swipe.status_code, 200)
        self.assertContains(swipe, "data-swipe-deck")
        self.assertEqual([row["profile"].pk for row in swipe.context["cards"]], expected)
        self.assertEqual([row["score"] for row in swipe.context["cards"]], [row["score"] for row in second.context["cards"]])
        reset = parse_qs(urlsplit(swipe.context["all_areas_url"]).query)
        self.assertNotIn("cursor", reset)
        self.assertNotIn("area", reset)
        self.assertEqual(reset["view"], ["swipe"])
        self.assertEqual(reset["rent"], ["4000000"])

    def test_view_preference_is_remembered_and_invalid_mode_rejected(self):
        self.client.force_login(self.actor.user)
        self.assertEqual(self.client.get(reverse("journey:discover"), secure=True).context["view_mode"], "list")
        self.client.get(reverse("journey:discover"), {"view": "swipe"}, secure=True)
        self.assertEqual(self.client.get(reverse("journey:discover"), secure=True).context["view_mode"], "swipe")
        self.assertEqual(self.client.get(reverse("journey:discover"), {"view": "unsupported"}, secure=True).status_code, 400)

    def test_discovery_expands_only_visible_cards_and_preserves_cursor_order(self):
        from . import views
        for index in range(25):
            profile(f"page-{index}@test.com")
        self.client.force_login(self.actor.user)
        expected = [row["profile"].pk for row in views.candidate_rows(self.actor)]
        with patch.object(views, "candidate_card", wraps=views.candidate_card) as expand:
            first = self.client.get(reverse("journey:discover"), secure=True)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(expand.call_count, 10)
        self.assertEqual([row["profile"].pk for row in first.context["cards"]], expected[:10])
        with patch.object(views, "candidate_card", wraps=views.candidate_card) as expand:
            second = self.client.get(reverse("journey:discover"), {"cursor": first.context["next_cursor"]}, secure=True)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(expand.call_count, 10)
        self.assertEqual([row["profile"].pk for row in second.context["cards"]], expected[10:20])

    def test_query_count_does_not_grow_per_candidate(self):
        from .views import candidate_rows
        from core.models import Profile

        counts = []
        for start, stop in ((0, 5), (5, 25)):
            for index in range(start, stop):
                profile(f"query-{index}@test.com")
            actor = Profile.objects.select_related("answers").get(pk=self.actor.pk)
            with CaptureQueriesContext(connection) as queries:
                rows = candidate_rows(actor)
            self.assertEqual(len(rows), stop)
            counts.append(len(queries))
            self.assertEqual([row["profile"].pk for row in rows], sorted(row["profile"].pk for row in rows))
        self.assertEqual(counts, [4, 4])

    def test_bulk_discovery_matches_direct_eligibility_and_rechecks_blocks(self):
        from .views import candidate_rows
        from core.models import recommendable_profiles

        saved = profile("saved@test.com")
        active = profile("active@test.com")
        blocked = profile("blocked@test.com")
        legacy = profile("legacy@test.com")
        profile("hidden@test.com", is_published=False)
        profile("other-area@test.com", areas=["Thanh Xuân"])
        profile("expensive@test.com", rent_min=6000000, rent_max=7000000)
        profile("incomplete@test.com", values={})
        profile("old-survey@test.com", questionnaire_version="old")
        profile("synthetic@test.com", is_synthetic=True)
        m.SavedCandidate.objects.create(owner=self.actor, candidate=saved)
        m.UserBlock.objects.create(actor=blocked, target=self.actor)
        ConnectionRequest.objects.create(sender=self.actor, recipient=legacy, status="blocked")
        m.Connection.objects.create(low=self.actor, high=active, active=True)

        expected = {}
        for target in recommendable_profiles().exclude(pk=self.actor.pk):
            try:
                expected[target.pk] = s.eligible_target(self.actor, target).score
            except s.DomainError:
                pass
        rows = candidate_rows(self.actor, include_decided=True)
        self.assertEqual({row["profile"].pk: row["score"] for row in rows}, expected)
        self.assertEqual(set(expected), {saved.pk, active.pk})
        self.assertTrue(next(row for row in rows if row["profile"].pk == saved.pk)["saved"])
        self.assertEqual([row["profile"].pk for row in candidate_rows(self.actor)], [saved.pk])
        self.assertEqual(candidate_rows(self.actor, rent=6000000), [])
        self.assertEqual(candidate_rows(self.actor, area="Thanh Xuân"), [])
        m.UserBlock.objects.create(actor=self.actor, target=saved)
        self.assertEqual(candidate_rows(self.actor), [])
        with self.assertRaises(s.DomainError):
            s.eligible_target(self.actor, saved)


class CostTests(SimpleTestCase):
    def test_allocation_conserves_vnd_and_is_stable(self):
        rng = random.Random(42)
        for _ in range(200):
            amount = rng.randrange(10**12)
            weights = {str(i): rng.randrange(1, 10001) for i in range(1, rng.randrange(2, 6))}
            shares = split_amount(amount, weights)
            self.assertEqual(sum(shares.values()), amount)
            self.assertEqual(shares, split_amount(amount, dict(reversed(list(weights.items())))))
            self.assertLessEqual(max(shares.values()), amount)
        self.assertEqual(split_amount(1, {"2": 1, "1": 1}), {"2": 0, "1": 1})

    def test_invalid_amounts_weights_and_members_are_rejected(self):
        for amount in (-1, 1.5, True, None, 10**12 + 1):
            with self.assertRaises(ValueError):
                split_amount(amount, {"1": 1})
        for weights in ({}, {"1": 0}, {"1": True}, {"1": 10001}):
            with self.assertRaises(ValueError):
                split_amount(100, weights)
        with self.assertRaises(ValueError):
            calculate_shared_costs([], [{"id": 1}], {"1": 1, "2": 1})

    def test_unknown_estimated_and_deposit_remain_distinct(self):
        costs = [
            {"label": "Thuê", "period": "monthly", "state": "known", "amount": 6000001},
            {"label": "Điện", "period": "monthly", "state": "estimated", "amount": 300000},
            {"label": "Nước", "period": "monthly", "state": "unknown", "amount": None},
            {"label": "Cọc", "period": "deposit", "state": "known", "amount": 6000000},
            {"label": "Đồ", "period": "initial", "state": "known", "amount": 1000000},
        ]
        result = calculate_shared_costs(costs, [{"id": 1, "monthly_budget": 3000000, "upfront_budget": 6000000}, {"id": 2}])
        self.assertFalse(result["complete"])
        self.assertFalse(result["monthly_complete"])
        self.assertEqual(result["estimated"], ["Điện"])
        self.assertEqual(result["totals"]["upfront"], 13300001)
        self.assertEqual(sum(row["upfront"] for row in result["members"]), 13300001)
        self.assertTrue(result["members"][0]["monthly_over_budget"])
        self.assertTrue(result["members"][0]["upfront_over_budget"])
        self.assertIsNone(result["members"][1]["monthly_budget"])

    def test_empty_costs_cannot_be_treated_as_a_verified_free_home(self):
        self.assertFalse(calculate_shared_costs([], [{"id": 1}])["complete"])

    def test_omitted_deposit_and_initial_charges_are_unknown(self):
        result = calculate_shared_costs([{"label": "Thuê", "period": "monthly", "state": "known", "amount": 6000000}], [{"id": 1}])
        self.assertEqual({row["period"] for row in result["unknown"]}, {"deposit", "initial"})
        self.assertFalse(result["complete"])

    def test_unknown_nonempty_amount_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_shared_costs([{"label": "Cọc", "period": "deposit", "state": "unknown", "amount": 0}], [{"id": 1}])


@override_settings(ROOMORA_JOURNEY_ENABLED=True)
class JourneyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = profile("an@test.com", name="An", contact_value="PRIVATE-CONTACT-AN")
        cls.b = profile("binh@test.com", name="Bình", contact_value="PRIVATE-CONTACT-BINH")
        cls.c = profile("chi@test.com", name="Chi")

    @override_settings(DEBUG=True)
    def test_recommendations_exclude_generic_test_accounts(self):
        from .views import candidate_rows

        imported = profile("sample-rm001@roomora.local", name="Nguyễn Hoài Vy", is_synthetic=True)
        placeholder = profile("sample-01@roomora.local", name="Mẫu thử #01", is_synthetic=True)
        fresh = profile("freshuser@roomora.local", name="freshuser")
        shown = {row["profile"].pk for row in candidate_rows(self.a)}
        self.assertIn(imported.pk, shown)
        self.assertNotIn(placeholder.pk, shown)
        self.assertNotIn(fresh.pk, shown)

    def test_candidate_detail_shows_survey_and_behavior_without_actor_routine(self):
        ImportedSampleProfile.objects.create(
            profile=self.b, source_id="RMTEST", estimated_answers=["A1"],
            behavior_metrics={
                "payment_on_time_pct": 88, "payment_periods": 0,
                "reply_within_24h_pct": 90, "show_up_score": 4.2,
                "review_average": 4.1, "review_count": 0,
                "verified_reports_90d": 0, "estimated_fields": ["payment_on_time_pct"],
            },
        )
        self.client.force_login(self.a.user)
        response = self.client.get(reverse("journey:candidate", args=[self.b.pk]))
        self.assertContains(response, "16 lựa chọn lifestyle")
        self.assertContains(response, "Hành vi mô phỏng")
        self.assertContains(response, "Ước tính")
        self.assertNotContains(response, "An · một ngày thường")
        self.assertNotContains(response, "chỉ số hành vi chưa có dữ liệu")

    def post(self, actor, action, **data):
        self.client.force_login(actor.user)
        data.setdefault("mutation_key", str(uuid.uuid4()))
        return self.client.post(reverse("journey:action", args=[action]), data, HTTP_ACCEPT="application/json")

    def matched(self):
        self.assertIsNone(s.decide(self.a, self.b, "like"))
        return s.decide(self.b, self.a, "like")

    def together(self):
        conversation = self.matched()
        invite = s.invite_workspace(self.a, conversation.pk, "Nhà của chúng mình")
        return s.respond_workspace(self.b, invite.pk, True)

    def known_room(self, workspace=None):
        room = m.RoomOption.objects.create(owner=self.a, workspace=workspace, title="Căn có ban công", area="Cầu Giấy")
        for label, period, amount in [("Thuê", "monthly", 6000001), ("Cọc", "deposit", 6000000), ("Phí đầu kỳ", "initial", 0)]:
            room.costs.create(label=label, period=period, state="known", amount=amount, source="Chủ nhà xác nhận bằng văn bản")
        return room

    def chosen(self):
        workspace = self.together()
        room = self.known_room(workspace)
        scenario = s.save_scenario(self.a, room.pk, 1, {str(self.a.pk): 1, str(self.b.pk): 1})
        proposal = s.propose_room(self.a, room.pk, scenario.room_version)
        for actor in (self.a, self.b):
            s.consent_choice(actor, proposal.pk, proposal.room_version)
        return workspace, room, proposal

    def agreed(self):
        workspace, room, proposal = self.chosen()
        agreement = s.save_agreement(self.a, workspace.pk, {key: f"Điều khoản {key}" for key in s.CLAUSES}, 0)
        for actor in (self.a, self.b):
            for key in s.CLAUSES:
                m.ClauseResponse.objects.create(agreement=agreement, member=actor, version=agreement.version, key=key, accepted=True)
            s.consent_agreement(actor, workspace.pk, agreement.version)
        return workspace, room, agreement

    def test_saved_is_independent_of_decision_and_mutual_match(self):
        self.assertEqual(self.post(self.a, "save-candidate", target=self.b.pk, saved="1").status_code, 200)
        self.assertFalse(m.SwipeDecision.objects.exists())
        self.assertEqual(self.post(self.a, "like", target=self.b.pk).status_code, 200)
        self.assertFalse(m.Conversation.objects.exists())
        self.client.force_login(self.b.user)
        self.assertContains(self.client.get(reverse("journey:hub")), "An")
        response = self.post(self.b, "like", target=self.a.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn("/chat/", response.json()["redirect"])
        self.assertEqual(m.Connection.objects.filter(active=True).count(), 1)
        self.assertEqual(m.Conversation.objects.count(), 1)
        self.assertTrue(m.SavedCandidate.objects.filter(owner=self.a, candidate=self.b).exists())
        self.assertEqual(self.post(self.b, "like", target=self.a.pk).status_code, 409)
        self.assertEqual(m.Conversation.objects.count(), 1)

    def test_connection_hub_tracks_sent_invites_and_opens_chat_after_acceptance(self):
        response = self.post(self.a, "like", target=self.b.pk)
        self.assertEqual(response.json()["redirect"], f"{reverse('journey:hub')}?chat={self.b.pk}")
        self.assertEqual(m.Conversation.objects.count(), 0)
        self.assertEqual(m.OutboxEvent.objects.filter(recipients=[self.b.pk]).count(), 1)

        self.client.force_login(self.a.user)
        sender_hub = self.client.get(reverse("journey:hub"))
        self.assertEqual([row["profile"].pk for row in sender_hub.context["outgoing"]], [self.b.pk])
        self.assertEqual(sender_hub.context["incoming"], [])
        self.assertEqual(sender_hub.context["conversations"], [])
        self.assertContains(sender_hub, "Đã gửi lời mời")

        self.client.force_login(self.b.user)
        recipient_hub = self.client.get(reverse("journey:hub"))
        self.assertEqual([row["profile"].pk for row in recipient_hub.context["incoming"]], [self.a.pk])
        self.assertContains(recipient_hub, "Kết nối và mở chat")
        response = self.post(self.b, "like", target=self.a.pk)
        conversation = m.Conversation.objects.get()
        self.assertEqual(response.json()["redirect"], reverse("journey:chat", args=[conversation.pk]))

        for actor, other in ((self.a, self.b), (self.b, self.a)):
            self.client.force_login(actor.user)
            hub = self.client.get(reverse("journey:hub"))
            self.assertEqual(hub.context["outgoing"], [])
            self.assertEqual(hub.context["incoming"], [])
            self.assertEqual([row["other"].pk for row in hub.context["conversations"]], [other.pk])
            self.assertContains(hub, reverse("journey:chat", args=[conversation.pk]))
            self.assertContains(hub, f'data-chat-person="{other.pk}"')

        response = self.post(self.a, "message", conversation=conversation.pk, body="Mình muốn hỏi về giờ giấc sinh hoạt.", client_id=uuid.uuid4())
        self.assertEqual(response.status_code, 200)
        self.client.force_login(self.b.user)
        self.assertContains(self.client.get(reverse("journey:hub")), "Mình muốn hỏi về giờ giấc sinh hoạt.")
        self.assertContains(self.client.get(reverse("journey:chat", args=[conversation.pk])), "Mình muốn hỏi về giờ giấc sinh hoạt.")

    def test_repeating_sent_invite_does_not_repeat_notification(self):
        self.post(self.a, "like", target=self.b.pk)
        self.post(self.a, "like", target=self.b.pk)
        self.assertEqual(m.OutboxEvent.objects.count(), 1)
        self.assertEqual(m.SwipeDecision.objects.count(), 1)

    def test_pending_like_cannot_create_chat_from_pair_send_or_polling(self):
        s.decide(self.a, self.b, "like")
        for actor, target in ((self.a, self.b), (self.b, self.a)):
            self.client.force_login(actor.user)
            self.assertEqual(self.client.get(reverse("journey:pair-messages", args=[target.pk])).status_code, 403)
            self.assertEqual(self.post(actor, "message", target=target.pk,
                                       body="Pending message", client_id=uuid.uuid4()).status_code, 403)
            with self.assertRaises(s.DomainError):
                s.send_pair_message(actor, target, "Direct service call", uuid.uuid4())
            hub = self.client.get(reverse("journey:hub"))
            self.assertNotContains(hub, f'data-chat-person="{target.pk}"')
        self.assertFalse(m.Conversation.objects.exists())
        self.assertFalse(m.Message.objects.exists())

    def test_legacy_pending_history_is_inaccessible_until_mutual_consent(self):
        s.decide(self.a, self.b, "like")
        connection = m.Connection.objects.get()
        conversation = s.ensure_current_conversation(connection)
        message = m.Message.objects.create(conversation=conversation, sender=self.a,
                                           client_id=uuid.uuid4(), body="LEGACY-PENDING-HISTORY")
        for actor, target in ((self.a, self.b), (self.b, self.a)):
            self.client.force_login(actor.user)
            for route, identifier in (("chat", conversation.pk), ("messages", conversation.pk),
                                      ("pair-messages", target.pk)):
                response = self.client.get(reverse(f"journey:{route}", args=[identifier]))
                self.assertEqual(response.status_code, 403)
                self.assertNotIn(b"LEGACY-PENDING-HISTORY", response.content)
            self.assertEqual(self.post(actor, "message", conversation=conversation.pk,
                                       body="Denied", client_id=uuid.uuid4()).status_code, 403)
            with self.assertRaises(s.DomainError):
                s.send_message(actor, conversation.pk, "Denied directly", uuid.uuid4())
        self.assertTrue(m.Message.objects.filter(pk=message.pk).exists())
        matched = s.decide(self.b, self.a, "like")
        self.assertEqual(matched.pk, conversation.pk)
        for actor, target in ((self.a, self.b), (self.b, self.a)):
            self.client.force_login(actor.user)
            response = self.client.get(reverse("journey:pair-messages", args=[target.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["messages"][0]["body"], "LEGACY-PENDING-HISTORY")
        self.assertEqual(m.Conversation.objects.count(), 1)

    def test_pair_chat_allows_mutual_messages_but_revokes_on_disconnect(self):
        conversation = self.matched()
        client_id = uuid.uuid4()
        for _ in range(2):
            self.assertEqual(self.post(self.a, "message", target=self.b.pk,
                                       body="Mutual message", client_id=client_id).status_code, 200)
        self.assertEqual(conversation.messages.count(), 1)
        s.disconnect(self.b, conversation.connection_id)
        for actor, target in ((self.a, self.b), (self.b, self.a)):
            self.client.force_login(actor.user)
            self.assertEqual(self.client.get(reverse("journey:pair-messages", args=[target.pk])).status_code, 403)
            self.assertEqual(self.post(actor, "message", target=target.pk,
                                       body="After disconnect", client_id=uuid.uuid4()).status_code, 403)
        self.assertEqual(conversation.messages.count(), 1)

    def test_undo_restores_previous_decision_but_cannot_undo_a_match(self):
        s.decide(self.a, self.b, "pass")
        s.decide(self.a, self.b, "like")
        s.undo_last(self.a)
        self.assertEqual(m.SwipeDecision.objects.get(actor=self.a, target=self.b).choice, "pass")
        s.undo_last(self.a)
        self.assertFalse(m.SwipeDecision.objects.filter(actor=self.a).exists())
        self.matched()
        with self.assertRaises(s.DomainError) as error:
            s.undo_last(self.b)
        self.assertEqual(error.exception.status, 409)

    def test_mutation_retry_replays_without_repeating_side_effects(self):
        key = str(uuid.uuid4())
        first = self.post(self.a, "like", target=self.b.pk, mutation_key=key)
        second = self.post(self.a, "like", target=self.b.pk, mutation_key=key)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(m.DecisionEvent.objects.count(), 1)
        self.assertEqual(self.post(self.a, "like", target=self.c.pk, mutation_key=key).status_code, 409)
        self.assertFalse(m.SwipeDecision.objects.filter(target=self.c).exists())

    def test_failed_commands_roll_back_receipt_and_state(self):
        response = self.post(self.a, "preferences", expected_version=0, sleep_at="23:00", wake_at="")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(m.MutationReceipt.objects.exists())
        self.assertFalse(m.LivingPreferences.objects.exists())

    def test_block_closes_chat_workspace_and_both_discovery_directions(self):
        workspace = self.together()
        conversation = workspace.conversation
        room = self.known_room(workspace)
        self.assertEqual(self.post(self.a, "block", target=self.b.pk).status_code, 200)
        workspace.refresh_from_db()
        self.assertEqual(workspace.status, "closed")
        self.assertFalse(workspace.members.filter(active=True).exists())
        self.assertFalse(m.Connection.objects.get(pk=conversation.connection_id).active)
        for actor in (self.a, self.b):
            self.client.force_login(actor.user)
            for url in (reverse("journey:chat", args=[conversation.pk]), reverse("journey:workspace", args=[workspace.pk]), reverse("journey:room", args=[room.pk])):
                self.assertEqual(self.client.get(url, HTTP_ACCEPT="application/json").status_code, 403)
        with self.assertRaises(s.DomainError):
            s.decide(self.b, self.a, "like")

    def test_legacy_block_revokes_the_new_journey_too(self):
        workspace = self.together()
        legacy = ConnectionRequest.objects.create(sender=self.a, recipient=self.b, status="accepted")
        self.client.force_login(self.b.user)
        self.client.post(f"/connections/{legacy.pk}/block/")
        workspace.refresh_from_db()
        self.assertEqual(workspace.status, "closed")
        self.assertTrue(s.is_blocked(self.a, self.b))

    def test_disconnect_then_rematch_cannot_reopen_old_chat(self):
        old = self.matched()
        s.disconnect(self.a, old.connection_id)
        s.decide(self.a, self.b, "like")
        new = s.decide(self.b, self.a, "like")
        self.assertNotEqual(old.pk, new.pk)
        with self.assertRaises(s.DomainError):
            s.conversation_for(self.a, old.pk)
        self.assertEqual(s.conversation_for(self.a, new.pk).pk, new.pk)

    def test_outsider_cannot_read_chat_workspace_or_private_room(self):
        workspace = self.together()
        room = self.known_room()
        self.client.force_login(self.c.user)
        for name, pk in (("chat", workspace.conversation_id), ("workspace", workspace.pk), ("room", room.pk)):
            self.assertEqual(self.client.get(reverse("journey:" + name, args=[pk]), HTTP_ACCEPT="application/json").status_code, 403)
        self.assertEqual(self.post(self.c, "message", conversation=workspace.conversation_id, body="X", client_id=uuid.uuid4()).status_code, 403)

    def test_invitation_requires_invitee_acceptance_and_decline_allows_new_invite(self):
        conversation = self.matched()
        invite = s.invite_workspace(self.a, conversation.pk, "Nhà")
        self.assertFalse(m.WorkspaceMember.objects.exists())
        self.assertEqual(self.post(self.a, "workspace-response", workspace=invite.pk, accepted="1").status_code, 409)
        self.assertEqual(self.post(self.c, "workspace-response", workspace=invite.pk, accepted="1").status_code, 409)
        s.respond_workspace(self.b, invite.pk, False)
        new = s.invite_workspace(self.a, conversation.pk, "Lần mới")
        self.assertNotEqual(new.pk, invite.pk)
        s.respond_workspace(self.b, new.pk, True)
        self.assertEqual(set(s.member_ids(new)), {self.a.pk, self.b.pk})

    def test_message_idempotency_and_history_pagination(self):
        conversation = self.matched()
        key = uuid.uuid4()
        s.send_message(self.a, conversation.pk, "Chào", key)
        s.send_message(self.a, conversation.pk, "Chào", key)
        with self.assertRaises(s.DomainError):
            s.send_message(self.a, conversation.pk, "Nội dung khác", key)
        m.Message.objects.bulk_create([m.Message(conversation=conversation, sender=self.b, body=f"Tin {i}") for i in range(60)])
        self.assertEqual(conversation.messages.count(), 61)
        self.client.force_login(self.a.user)
        url = reverse("journey:messages", args=[conversation.pk])
        first = self.client.get(url).json()["messages"]
        last = self.client.get(url, {"after": first[-1]["id"]}).json()["messages"]
        self.assertEqual(len(first), 50)
        self.assertEqual(len(last), 11)
        older = self.client.get(url, {"before": last[0]["id"]}).json()["messages"]
        self.assertEqual([row["id"] for row in first], [row["id"] for row in older])

    def test_message_retry_after_reload_with_new_mutation_key_still_dedupes(self):
        conversation = self.matched()
        client_id = uuid.uuid4()
        for _ in range(2):
            response = self.post(self.a, "message", conversation=conversation.pk, body="Lưu draft qua reload", client_id=client_id)
            self.assertEqual(response.status_code, 200)
        self.assertEqual(conversation.messages.count(), 1)
        self.assertEqual(m.MutationReceipt.objects.filter(action="message").count(), 2)

    def test_pinned_fact_edit_requires_fresh_individual_consents(self):
        conversation = self.matched()
        message = s.send_message(self.a, conversation.pk, "Tiền", uuid.uuid4())
        self.assertEqual(self.post(self.a, "fact-pin", conversation=conversation.pk, source=message.pk, body="Chia đều").status_code, 200)
        fact = m.PinnedFact.objects.get()
        for actor in (self.a, self.b):
            self.post(actor, "fact-consent", conversation=conversation.pk, fact=fact.pk, expected_version=1)
        self.assertEqual(self.post(self.b, "fact-edit", conversation=conversation.pk, fact=fact.pk, expected_version=1, body="Khác").status_code, 403)
        self.assertEqual(self.post(self.a, "fact-edit", conversation=conversation.pk, fact=fact.pk, expected_version=1, body="Chia theo phòng").status_code, 200)
        fact.refresh_from_db()
        self.assertEqual(fact.version, 2)
        self.assertFalse(fact.consents.filter(version=2).exists())
        self.assertEqual(self.post(self.b, "fact-consent", conversation=conversation.pk, fact=fact.pk, expected_version=1).status_code, 409)

    def test_pinned_old_message_can_be_loaded_even_outside_initial_history(self):
        conversation = self.matched()
        source = s.send_message(self.a, conversation.pk, "OLD-SOURCE-TEXT", uuid.uuid4())
        m.Message.objects.bulk_create([m.Message(conversation=conversation, sender=self.b, body=f"Tin {i}") for i in range(60)])
        self.client.force_login(self.a.user)
        url = reverse("journey:chat", args=[conversation.pk])
        self.assertNotContains(self.client.get(url), "OLD-SOURCE-TEXT")
        self.assertContains(self.client.get(url, {"message": source.pk}), "OLD-SOURCE-TEXT")
        self.assertEqual(self.client.get(url, {"message": 999999}).status_code, 404)

    def test_private_notes_are_owner_scoped_and_escape_html(self):
        self.post(self.a, "note", target=self.b.pk, expected_version=0, body="PRIVATE-NOTE <script>alert(1)</script>")
        self.client.force_login(self.a.user)
        self.assertContains(self.client.get(reverse("journey:candidate", args=[self.b.pk])), "&lt;script&gt;")
        self.client.force_login(self.c.user)
        self.assertNotContains(self.client.get(reverse("journey:candidate", args=[self.b.pk])), "PRIVATE-NOTE")
        self.assertEqual(self.post(self.a, "note", target=self.b.pk, expected_version=0, body="Overwrite").status_code, 409)

    def test_people_compare_requires_two_or_three_saved_candidates(self):
        self.client.force_login(self.a.user)
        url = reverse("journey:compare")
        self.assertEqual(self.client.get(url, {"candidate": [self.b.pk, self.c.pk]}).status_code, 403)
        for candidate in (self.b, self.c):
            m.SavedCandidate.objects.create(owner=self.a, candidate=candidate)
        self.assertContains(self.client.get(url, {"candidate": [self.b.pk, self.c.pk]}), "Bình")
        self.assertEqual(self.client.get(url, {"candidate": [self.b.pk]}).status_code, 400)

    def test_discovery_does_not_expose_contacts_and_rejects_bad_cursor(self):
        self.client.force_login(self.a.user)
        response = self.client.get(reverse("journey:discover"))
        self.assertContains(response, "Bình")
        self.assertNotContains(response, "PRIVATE-CONTACT")
        self.assertEqual(self.client.get(reverse("journey:discover"), {"cursor": "forged"}).status_code, 409)
        self.b.is_published = False
        self.b.save()
        self.assertEqual(self.post(self.a, "like", target=self.b.pk).status_code, 403)

    def test_signed_cursor_has_no_duplicates_and_rejects_changed_deck(self):
        for i in range(10):
            profile(f"page-{i}@test.com")
        self.client.force_login(self.a.user)
        url = reverse("journey:discover")
        first = self.client.get(url)
        cursor = first.context["next_cursor"]
        self.assertTrue(cursor)
        second = self.client.get(url, {"cursor": cursor})
        first_ids = {card["profile"].pk for card in first.context["cards"]}
        second_ids = {card["profile"].pk for card in second.context["cards"]}
        self.assertEqual(len(first_ids), 10)
        self.assertEqual(len(second_ids), 2)
        self.assertFalse(first_ids & second_ids)
        s.decide(self.a, self.b, "pass")
        self.assertEqual(self.client.get(url, {"cursor": cursor}).status_code, 409)

    def test_preferences_autosave_version_and_validation(self):
        result = self.post(self.a, "preferences", expected_version=0, needs="Bàn làm việc", sleep_at="23:00", wake_at="07:00", notifications_enabled="on")
        self.assertEqual(result.json()["version"], 1)
        self.assertEqual(self.post(self.a, "preferences", expected_version=0, needs="Stale").status_code, 409)
        self.assertEqual(self.post(self.a, "preferences", expected_version=1, move_in_from="2026-11-10", move_in_until="2026-11-01").status_code, 400)

    def test_preferences_form_has_exactly_one_version_field_for_autosave(self):
        self.client.force_login(self.a.user)
        response = self.client.get(reverse("journey:preferences"))
        self.assertEqual(response.content.count(b'name="expected_version"'), 1)
        m.LivingPreferences.objects.create(profile=self.a, version=2)
        response = self.client.get(reverse("journey:preferences"))
        self.assertEqual(response.content.count(b'name="expected_version"'), 1)
        self.assertContains(response, 'name="expected_version" value="2"')

    def test_private_room_share_is_explicit_snapshot_and_idempotent(self):
        workspace = self.together()
        private = self.known_room()
        shared = s.share_room(self.a, private.pk, workspace.pk)
        self.assertEqual(s.share_room(self.a, private.pk, workspace.pk).pk, shared.pk)
        private.title = "Bản riêng mới"
        private.save()
        private.costs.filter(period="monthly").update(amount=9000000)
        shared.refresh_from_db()
        self.assertEqual(shared.title, "Căn có ban công")
        self.assertEqual(shared.costs.get(period="monthly").amount, 6000001)
        self.assertTrue(shared.checklist.exists())
        with self.assertRaises(s.DomainError):
            s.share_room(self.b, private.pk, workspace.pk)

    def test_room_formset_save_update_and_foreign_cost_id_are_isolated(self):
        data = {"title": "Căn qua form", "room": 0, "expected_version": 0,
                "costs-TOTAL_FORMS": 1, "costs-INITIAL_FORMS": 0, "costs-MIN_NUM_FORMS": 0, "costs-MAX_NUM_FORMS": 20,
                "costs-0-label": "Thuê", "costs-0-period": "monthly", "costs-0-state": "known", "costs-0-amount": 5000000, "costs-0-source": "Tin chủ nhà"}
        response = self.post(self.a, "room-save", **data)
        self.assertEqual(response.status_code, 200, response.content)
        room = m.RoomOption.objects.get(title=data["title"])
        self.assertEqual(room.costs.get().amount, 5000000)
        foreign = self.known_room()
        foreign_cost = foreign.costs.get(period="monthly")
        data.update(room=room.pk, expected_version=room.version, title="Căn sửa", **{"costs-INITIAL_FORMS": 1, "costs-0-id": foreign_cost.pk, "costs-0-amount": 1})
        response = self.post(self.a, "room-save", **data)
        self.assertIn(response.status_code, (200, 400))
        foreign_cost.refresh_from_db()
        self.assertEqual(foreign_cost.amount, 6000001)
        room.refresh_from_db()
        if response.status_code == 200:
            self.assertEqual(self.post(self.a, "room-save", **data).status_code, 409)

    def test_individual_opinions_do_not_set_other_members_or_choice_consents(self):
        workspace = self.together()
        room = self.known_room(workspace)
        self.post(self.a, "opinion", room=room.pk, choice="interested", expected_version=0)
        self.post(self.b, "opinion", room=room.pk, choice="no", expected_version=0, note="Xa chỗ làm")
        self.assertEqual(room.opinions.count(), 2)
        self.assertFalse(m.ChoiceConsent.objects.exists())
        self.assertEqual(self.post(self.a, "opinion", room=room.pk, choice="unsure", expected_version=0).status_code, 409)

    def test_board_shows_both_members_and_pending_opinion_without_inventing_consent(self):
        workspace = self.together()
        room = self.known_room(workspace)
        m.RoomOpinion.objects.create(room=room, member=self.a, choice="interested")
        self.client.force_login(self.a.user)
        response = self.client.get(reverse("journey:workspace", args=[workspace.pk]))
        self.assertContains(response, "An")
        self.assertContains(response, "Bình")
        self.assertContains(response, "Chưa phản hồi")
        self.assertFalse(m.RoomOpinion.objects.filter(room=room, member=self.b).exists())

    def test_unverified_costs_or_missing_sources_cannot_be_proposed(self):
        workspace = self.together()
        room = self.known_room(workspace)
        room.costs.filter(period="deposit").update(state="unknown", amount=None)
        scenario = s.save_scenario(self.a, room.pk, 1, {str(self.a.pk): 1, str(self.b.pk): 1})
        self.assertEqual(self.post(self.a, "room-propose", room=room.pk, expected_version=scenario.room_version).status_code, 400)
        room.costs.filter(period="deposit").update(state="estimated", amount=6000000)
        scenario = s.save_scenario(self.a, room.pk, scenario.room_version, {str(self.a.pk): 1, str(self.b.pk): 1})
        self.assertEqual(self.post(self.a, "room-propose", room=room.pk, expected_version=scenario.room_version).status_code, 400)
        room.costs.filter(period="deposit").update(state="known", source="")
        scenario = s.save_scenario(self.a, room.pk, scenario.room_version, {str(self.a.pk): 1, str(self.b.pk): 1})
        self.assertEqual(self.post(self.a, "room-propose", room=room.pk, expected_version=scenario.room_version).status_code, 400)

    def test_choice_requires_both_consents_and_room_changes_invalidate_them(self):
        workspace = self.together()
        room = self.known_room(workspace)
        scenario = s.save_scenario(self.a, room.pk, 1, {str(self.a.pk): 2, str(self.b.pk): 1})
        proposal = s.propose_room(self.a, room.pk, scenario.room_version)
        self.assertFalse(proposal.consents.exists())
        s.consent_choice(self.a, proposal.pk, proposal.room_version)
        self.assertFalse(s.proposal_confirmed(proposal))
        s.consent_choice(self.b, proposal.pk, proposal.room_version)
        self.assertTrue(s.proposal_confirmed(proposal))
        s.save_scenario(self.a, room.pk, scenario.room_version, {str(self.a.pk): 1, str(self.b.pk): 1})
        proposal = m.RoomChoiceProposal.objects.select_related("room", "scenario", "workspace").get(pk=proposal.pk)
        self.assertFalse(s.proposal_confirmed(proposal))
        self.assertEqual(self.post(self.b, "choice-consent", proposal=proposal.pk, expected_version=proposal.room_version).status_code, 409)

    def test_agreement_requires_each_clause_and_each_person_then_can_start_move(self):
        workspace, _, _ = self.chosen()
        agreement = s.save_agreement(self.a, workspace.pk, {key: "Đồng ý nội dung" for key in s.CLAUSES}, 0)
        self.assertEqual(self.post(self.a, "agreement-consent", workspace=workspace.pk, expected_version=1).status_code, 400)
        self.assertEqual(self.post(self.a, "move-in-start", workspace=workspace.pk).status_code, 409)
        for actor in (self.a, self.b):
            for key in s.CLAUSES:
                self.assertEqual(self.post(actor, "clause-response", workspace=workspace.pk, expected_version=1, clause=key, accepted="1").status_code, 200)
            self.assertEqual(self.post(actor, "agreement-consent", workspace=workspace.pk, expected_version=1).status_code, 200)
        agreement.refresh_from_db()
        self.assertTrue(s.agreement_confirmed(agreement))
        self.assertEqual(self.post(self.a, "move-in-start", workspace=workspace.pk).status_code, 200)
        workspace.refresh_from_db()
        self.assertTrue(workspace.moving_in)

    def test_agreement_edit_and_clause_disagreement_revoke_move_in(self):
        workspace, _, agreement = self.agreed()
        self.post(self.a, "move-in-start", workspace=workspace.pk)
        self.post(self.b, "clause-response", workspace=workspace.pk, expected_version=1, clause="quiet", accepted="0", note="Cần giờ khác")
        agreement.refresh_from_db()
        self.assertFalse(s.agreement_confirmed(agreement))
        workspace.refresh_from_db()
        self.assertFalse(workspace.moving_in)
        response = self.post(self.a, "agreement-save", workspace=workspace.pk, expected_version=1, **{key: "Bản mới" for key in s.CLAUSES})
        self.assertEqual(response.json()["version"], 2)
        self.assertEqual(self.post(self.b, "agreement-consent", workspace=workspace.pk, expected_version=1).status_code, 409)
        self.assertFalse(m.AgreementConsent.objects.filter(agreement=agreement, version=2).exists())

    def test_incomplete_agreement_cannot_be_confirmed(self):
        workspace, _, _ = self.chosen()
        agreement = s.save_agreement(self.a, workspace.pk, {key: "" for key in s.CLAUSES}, 0)
        self.assertEqual(self.post(self.a, "agreement-consent", workspace=workspace.pk, expected_version=agreement.version).status_code, 400)

    def test_viewing_requires_each_member_response_again_after_time_change(self):
        room = self.known_room(self.together())
        at = timezone.now() + timedelta(days=2)
        response = self.post(self.a, "viewing-save", room=room.pk, at=at.isoformat(), meeting_point="Cổng")
        self.assertEqual(response.status_code, 200)
        plan = m.ViewingPlan.objects.get()
        self.post(self.b, "viewing-response", room=room.pk, plan=plan.pk, expected_version=1, accepted="1")
        self.assertEqual(plan.responses.filter(version=1, accepted=True).count(), 2)
        self.post(self.a, "viewing-save", room=room.pk, plan=plan.pk, expected_version=1, at=(at + timedelta(hours=1)).isoformat(), meeting_point="Cổng")
        plan.refresh_from_db()
        self.assertEqual(plan.version, 2)
        self.assertEqual(plan.responses.filter(version=2, accepted=True).count(), 1)
        self.assertEqual(self.post(self.b, "viewing-response", room=room.pk, plan=plan.pk, expected_version=1, accepted="1").status_code, 409)
        self.assertEqual(self.post(self.b, "viewing-cancel", room=room.pk, plan=plan.pk, expected_version=2).status_code, 200)
        self.assertEqual(self.post(self.a, "viewing-response", room=room.pk, plan=plan.pk, expected_version=3, accepted="1").status_code, 404)

    def test_checklist_evidence_and_invalid_image_ids(self):
        room = self.known_room(self.together())
        self.post(self.a, "checklist-add", room=room.pk, title="Kiểm tra vòi nước")
        item = room.checklist.get()
        self.assertEqual(self.post(self.b, "checklist-update", room=room.pk, item=item.pk, expected_version=1, done="1", note="Chảy ổn").status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.checked_by, self.b)
        self.assertEqual(self.post(self.a, "checklist-update", room=room.pk, item=item.pk, expected_version=1, done="0").status_code, 409)
        self.assertEqual(self.post(self.b, "evidence", room=room.pk, note="Đã xem cửa sổ").status_code, 200)
        for action in ("image-pin", "evidence"):
            self.assertEqual(self.post(self.a, action, room=room.pk, image="not-a-uuid", question="?", x=.5, y=.5, note="X").status_code, 400)

    def test_task_templates_assignment_edit_and_stale_update(self):
        workspace = self.together()
        self.post(self.a, "task-template", workspace=workspace.pk)
        self.post(self.b, "task-template", workspace=workspace.pk)
        self.assertEqual(workspace.tasks.count(), 4)
        task = workspace.tasks.first()
        response = self.post(self.a, "task-save", workspace=workspace.pk, task=task.pk, expected_version=1, title="Nhận chìa khóa", assignee=self.b.pk, due_at="2026-12-01")
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.assignee, self.b)
        self.assertEqual(self.post(self.b, "task-update", workspace=workspace.pk, task=task.pk, expected_version=1, done="1").status_code, 409)
        self.assertEqual(self.post(self.b, "task-update", workspace=workspace.pk, task=task.pk, expected_version=2, done="1").status_code, 200)
        self.assertEqual(self.post(self.a, "task-save", workspace=workspace.pk, title="Ngoài", assignee=self.c.pk).status_code, 400)

    def test_room_comparison_has_per_member_names_and_needs(self):
        workspace = self.together()
        m.LivingPreferences.objects.create(profile=self.a, needs="Cần bàn học", total_monthly_budget=1000000)
        first, second = self.known_room(workspace), self.known_room(workspace)
        self.client.force_login(self.a.user)
        response = self.client.get(reverse("journey:room-compare"), {"room": [first.pk, second.pk]})
        self.assertContains(response, "Cần bàn học")
        self.assertContains(response, "Bình")
        self.assertContains(response, "vượt trần tổng chi phí tháng")

    def test_notifications_are_durable_idempotent_and_respect_preferences_and_membership(self):
        workspace = self.together()
        m.LivingPreferences.objects.create(profile=self.b, notifications_enabled=False)
        event = s.emit([self.a.pk, self.b.pk], "Thông tin mới", "/together/", workspace)
        with patch("journey.services.deliver_event", side_effect=RuntimeError("temporary")):
            with self.assertLogs("journey.services", level="ERROR"):
                s.deliver_safely(event.pk)
        event.refresh_from_db()
        self.assertFalse(event.delivered)
        s.deliver_event(event.pk)
        s.deliver_event(event.pk)
        self.assertEqual(m.Notification.objects.filter(event=event, profile=self.a).count(), 1)
        self.assertFalse(m.Notification.objects.filter(event=event, profile=self.b).exists())
        s.leave_workspace(self.a, workspace.pk)
        self.client.force_login(self.a.user)
        self.assertNotContains(self.client.get(reverse("journey:notifications")), "Thông tin mới")
        from .context import navigation
        from django.test import RequestFactory
        request = RequestFactory().get("/")
        request.user = self.a.user
        self.assertEqual(navigation(request)["journey_unread"], 1)  # The match notification remains valid.

    def test_resume_rechecks_membership_and_rejects_external_redirect(self):
        workspace = self.together()
        self.client.force_login(self.a.user)
        self.client.get(reverse("journey:workspace", args=[workspace.pk]))
        self.assertRedirects(self.client.get(reverse("journey:resume")), reverse("journey:workspace", args=[workspace.pk]))
        s.leave_workspace(self.b, workspace.pk)
        self.assertRedirects(self.client.get(reverse("journey:resume")), reverse("journey:hub"))
        m.JourneyCheckpoint.objects.filter(profile=self.a).update(path="https://attacker.invalid", workspace=None)
        self.assertRedirects(self.client.get(reverse("journey:resume")), reverse("journey:hub"))

    def test_all_authenticated_pages_render_with_populated_journey(self):
        workspace, room, _ = self.agreed()
        private = self.known_room()
        m.SavedCandidate.objects.bulk_create([m.SavedCandidate(owner=self.a, candidate=p) for p in (self.b, self.c)])
        m.MoveInTask.objects.create(workspace=workspace, title="Dọn", assignee=self.b)
        self.client.force_login(self.a.user)
        pages = [(name, []) for name in ("discover", "saved", "hub", "preferences", "rooms", "room-new", "notifications")]
        pages += [("candidate", [self.b.pk]), ("chat", [workspace.conversation_id]), ("workspace", [workspace.pk]), ("agreement", [workspace.pk]), ("room", [room.pk]), ("room-edit", [private.pk])]
        for name, args in pages:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse("journey:" + name, args=args)).status_code, 200)

    def test_anonymous_feature_off_and_csrf_gate(self):
        self.assertEqual(self.client.get(reverse("journey:hub")).status_code, 302)
        self.client.force_login(self.a.user)
        with override_settings(ROOMORA_JOURNEY_ENABLED=False):
            self.assertEqual(self.client.get(reverse("journey:hub")).status_code, 404)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.a.user)
        self.assertEqual(csrf_client.post(reverse("journey:action", args=["like"]), {"target": self.b.pk, "mutation_key": uuid.uuid4()}).status_code, 403)
        self.assertEqual(self.client.get(reverse("journey:action", args=["like"])).status_code, 405)

    def test_reports_do_not_change_match_or_trigger_automatic_block(self):
        conversation = self.matched()
        self.assertEqual(self.post(self.a, "report", target=self.b.pk, reason="Cần xem xét").status_code, 200)
        self.assertEqual(m.Report.objects.get().reporter, self.a)
        self.assertTrue(m.Connection.objects.get(pk=conversation.connection_id).active)
        self.assertFalse(s.is_blocked(self.a, self.b))
        self.assertEqual(self.post(self.a, "report", target=self.a.pk, reason="X").status_code, 400)

    def test_cost_state_database_invariant(self):
        room = self.known_room()
        with self.assertRaises(IntegrityError), transaction.atomic():
            room.costs.create(label="Không hợp lệ", period="monthly", state="unknown", amount=0)

    def test_private_images_are_authenticated_and_pins_use_correct_percentages(self):
        room = self.known_room()
        stream = io.BytesIO()
        Image.new("RGB", (32, 20), "#cccccc").save(stream, format="PNG")
        with tempfile.TemporaryDirectory() as directory, override_settings(ROOMORA_PRIVATE_MEDIA_ROOT=Path(directory)):
            image = SimpleUploadedFile("test.png", stream.getvalue(), content_type="image/png")
            self.assertEqual(self.post(self.a, "image-upload", room=room.pk, image=image, caption="Cửa sổ").status_code, 200)
            saved = room.images.get()
            self.assertTrue(Path(saved.image.path).is_file())
            with self.assertRaises(ValueError):
                _ = saved.image.url
            response = self.client.get(reverse("journey:image", args=[saved.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "private, no-store")
            served = b"".join(response.streaming_content)
            with Image.open(io.BytesIO(served)) as decoded:
                self.assertEqual(decoded.size, (32, 20))
                self.assertEqual(decoded.getpixel((0, 0)), (204, 204, 204))
            self.assertEqual(self.post(self.a, "image-pin", room=room.pk, image=saved.pk, x=.5, y=.25, question="Nắng sáng?").status_code, 200)
            self.assertContains(self.client.get(reverse("journey:room", args=[room.pk])), "left:50.0%;top:25.0%")
            self.client.force_login(self.b.user)
            self.assertEqual(self.client.get(reverse("journey:image", args=[saved.pk]), HTTP_ACCEPT="application/json").status_code, 403)
            self.assertEqual(self.post(self.a, "image-pin", room=room.pk, image=saved.pk, x=2, y=.5, question="X").status_code, 400)
            corrupt = SimpleUploadedFile("evil.png", b"not an image", content_type="image/png")
            self.assertEqual(self.post(self.a, "image-upload", room=room.pk, image=corrupt).status_code, 400)

    def test_person_image_count_spans_rooms_and_retry_does_not_spend_twice(self):
        first = self.known_room()
        second = self.known_room()
        other_room = m.RoomOption.objects.create(owner=self.b, title="Căn riêng", area="Cầu Giấy")
        stream = io.BytesIO()
        Image.new("RGB", (10, 10), "blue").save(stream, format="PNG")
        def upload():
            return SimpleUploadedFile("room.png", stream.getvalue(), content_type="image/png")
        with tempfile.TemporaryDirectory() as directory, override_settings(
            ROOMORA_PRIVATE_MEDIA_ROOT=Path(directory), ROOMORA_PERSON_IMAGE_COUNT=1, ROOMORA_PERSON_IMAGE_BYTES=0):
            key = uuid.uuid4()
            for _ in range(2):
                self.assertEqual(self.post(self.a, "image-upload", room=first.pk, image=upload(), mutation_key=key).status_code, 200)
            self.assertEqual(first.images.count(), 1)
            receipts = m.MutationReceipt.objects.count()
            self.assertEqual(self.post(self.a, "image-upload", room=second.pk, image=upload()).status_code, 409)
            self.assertEqual(second.images.count(), 0)
            self.assertEqual(m.MutationReceipt.objects.count(), receipts)
            self.assertEqual(self.post(self.b, "image-upload", room=other_room.pk, image=upload()).status_code, 200)
            self.assertEqual(other_room.images.count(), 1)

    def test_person_byte_limit_counts_normalized_files_at_exact_boundary(self):
        room = self.known_room()
        stream = io.BytesIO()
        Image.new("RGB", (10, 10), "blue").save(stream, format="PNG")
        def upload():
            return SimpleUploadedFile("room.png", stream.getvalue(), content_type="image/png")
        form = f.ImageUploadForm({}, {"image": upload()})
        self.assertTrue(form.is_valid())
        size = form.cleaned_data["image"].size
        with tempfile.TemporaryDirectory() as directory, override_settings(
            ROOMORA_PRIVATE_MEDIA_ROOT=Path(directory), ROOMORA_PERSON_IMAGE_COUNT=20, ROOMORA_PERSON_IMAGE_BYTES=size * 2):
            for _ in range(2):
                self.assertEqual(self.post(self.a, "image-upload", room=room.pk, image=upload()).status_code, 200)
            self.assertEqual(self.post(self.a, "image-upload", room=room.pk, image=upload()).status_code, 409)
            self.assertEqual(room.images.count(), 2)
            self.assertTrue(all(Path(image.image.path).exists() for image in room.images.all()))

    def test_missing_existing_file_prevents_understating_person_usage(self):
        room = self.known_room()
        with tempfile.TemporaryDirectory() as directory, override_settings(
            ROOMORA_PRIVATE_MEDIA_ROOT=Path(directory), ROOMORA_PERSON_IMAGE_COUNT=20, ROOMORA_PERSON_IMAGE_BYTES=8 * 1024 * 1024):
            m.RoomImage.objects.create(room=room, creator=self.a, image="rooms/missing.png")
            stream = io.BytesIO()
            Image.new("RGB", (10, 10), "blue").save(stream, format="PNG")
            uploaded = SimpleUploadedFile("room.png", stream.getvalue(), content_type="image/png")
            self.assertEqual(self.post(self.a, "image-upload", room=room.pk, image=uploaded).status_code, 503)
            self.assertEqual(room.images.count(), 1)
            self.assertIn("20 ảnh", f.ImageUploadForm().fields["image"].help_text)
            self.assertIn("8 MB", f.ImageUploadForm().fields["image"].help_text)

    def test_image_capacity_rejection_rolls_back_mutation_and_keeps_room(self):
        room = self.known_room()
        stream = io.BytesIO()
        Image.new("RGB", (32, 20), "blue").save(stream, format="PNG")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with override_settings(MEDIA_ROOT=root / "public", ROOMORA_PRIVATE_MEDIA_ROOT=root / "private",
                ROOMORA_DATA_ROOT=root / "data", ROOMORA_UPLOAD_BUDGET_BYTES=1,
                ROOMORA_UPLOAD_FREE_RESERVE_BYTES=0):
                before = m.MutationReceipt.objects.count()
                image = SimpleUploadedFile("room.png", stream.getvalue(), content_type="image/png")
                response = self.post(self.a, "image-upload", room=room.pk, image=image)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(room.images.count(), 0)
                self.assertEqual(m.MutationReceipt.objects.count(), before)
                self.assertFalse(list((root / "private").rglob("*")))
                self.assertEqual(self.client.get(reverse("journey:room", args=[room.pk])).status_code, 200)

    def test_upload_retries_do_not_duplicate_and_unexpected_files_are_rejected(self):
        room = self.known_room()
        stream = io.BytesIO()
        Image.new("RGB", (4, 4), "white").save(stream, format="PNG")
        key = uuid.uuid4()
        with tempfile.TemporaryDirectory() as directory, override_settings(ROOMORA_PRIVATE_MEDIA_ROOT=Path(directory)):
            for _ in range(2):
                file = SimpleUploadedFile("room.png", stream.getvalue(), content_type="image/png")
                self.assertEqual(self.post(self.a, "image-upload", room=room.pk, image=file, mutation_key=key).status_code, 200)
            self.assertEqual(room.images.count(), 1)
            file = SimpleUploadedFile("room.png", stream.getvalue(), content_type="image/png")
            self.assertEqual(self.post(self.a, "like", target=self.b.pk, image=file).status_code, 400)
            oversized = SimpleUploadedFile("large.png", b"x" * (5 * 1024 * 1024 + 1), content_type="image/png")
            self.assertEqual(self.post(self.a, "image-upload", room=room.pk, image=oversized).status_code, 400)

    @override_settings(DEBUG=False)
    def test_synthetic_candidates_are_not_available_in_production(self):
        self.b.is_synthetic = True
        self.b.save()
        with self.assertRaises(s.DomainError):
            s.decide(self.a, self.b, "like")


@override_settings(ROOMORA_JOURNEY_ENABLED=True)
class ConcurrentJourneyTests(TransactionTestCase):
    def setUp(self):
        if "memory" in str(connection.settings_dict["NAME"]):
            self.skipTest("Run with --settings=config.test_settings to verify file-backed SQLite concurrency.")
        self.a, self.b = profile("race-a@test.com"), profile("race-b@test.com")

    def parallel(self, operations):
        def worker(operation):
            try:
                return operation()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            return list(executor.map(worker, operations))

    def test_free_beta_immediate_transactions_serialize_person_upload_budget(self):
        from django.core.files.base import ContentFile
        from .upload_limits import check_room_image_budget
        if connection.vendor != "sqlite":
            self.skipTest("Exercises the free-beta SQLite transaction mode.")
        original_options = connection.settings_dict["OPTIONS"]
        connection.close()
        connection.settings_dict["OPTIONS"] = {**original_options, "transaction_mode": "IMMEDIATE", "timeout": 20}
        try:
            room = m.RoomOption.objects.create(owner=self.a, title="Upload race fixture")
            def upload():
                def operation():
                    content = ContentFile(b"fixture", name="fixture.png")
                    check_room_image_budget(self.a, content)
                    m.RoomImage.objects.create(room=room, creator=self.a, image=content)
                    return {"saved": True}
                try:
                    s.run_mutation(self.a, "image-upload", uuid.uuid4(), {}, operation)
                    return True
                except s.DomainError as error:
                    self.assertEqual(error.status, 409)
                    return False
            with tempfile.TemporaryDirectory() as directory, override_settings(
                ROOMORA_PRIVATE_MEDIA_ROOT=Path(directory), ROOMORA_PERSON_IMAGE_COUNT=1, ROOMORA_PERSON_IMAGE_BYTES=100):
                results = self.parallel([upload] * 8)
                self.assertEqual(sum(results), 1)
                self.assertEqual(room.images.count(), 1)
                self.assertEqual(m.MutationReceipt.objects.filter(action="image-upload").count(), 1)
        finally:
            connection.close()
            connection.settings_dict["OPTIONS"] = original_options

    def test_simultaneous_likes_create_one_canonical_pair_and_conversation(self):
        self.parallel([lambda: s.decide(self.a, self.b, "like"), lambda: s.decide(self.b, self.a, "like")])
        self.assertEqual(m.Connection.objects.filter(active=True).count(), 1)
        self.assertEqual(m.Conversation.objects.count(), 1)

    def test_parallel_retries_create_one_receipt_and_decision(self):
        key = uuid.uuid4()
        def retry():
            return s.run_mutation(self.a, "like", key, {"target": self.b.pk}, lambda: {"matched": bool(s.decide(self.a, self.b, "like"))})
        results = self.parallel([retry] * 8)
        self.assertEqual(results, [{"matched": False}] * 8)
        self.assertEqual(m.MutationReceipt.objects.count(), 1)
        self.assertEqual(m.DecisionEvent.objects.count(), 1)

    def test_block_racing_with_match_always_revokes_permissions(self):
        s.decide(self.a, self.b, "like")
        def like():
            try:
                s.decide(self.b, self.a, "like")
            except s.DomainError as exc:
                self.assertEqual(exc.status, 403)
        self.parallel([like, lambda: s.block_profile(self.a, self.b)])
        self.assertTrue(s.is_blocked(self.a, self.b))
        self.assertFalse(m.Connection.objects.filter(active=True).exists())

    def test_cost_change_racing_with_consent_never_confirms_old_proposal(self):
        s.decide(self.a, self.b, "like")
        conversation = s.decide(self.b, self.a, "like")
        invite = s.invite_workspace(self.a, conversation.pk, "Nhà")
        workspace = s.respond_workspace(self.b, invite.pk, True)
        room = m.RoomOption.objects.create(owner=self.a, workspace=workspace, title="Căn")
        for period in ("monthly", "initial", "deposit"):
            room.costs.create(label=period, period=period, state="known", amount=100, source="Xác minh")
        weights = {str(self.a.pk): 1, str(self.b.pk): 1}
        scenario = s.save_scenario(self.a, room.pk, 1, weights)
        proposal = s.propose_room(self.a, room.pk, scenario.room_version)
        s.consent_choice(self.a, proposal.pk, proposal.room_version)
        def consent():
            try:
                s.consent_choice(self.b, proposal.pk, proposal.room_version)
            except s.DomainError as exc:
                self.assertEqual(exc.status, 409)
        self.parallel([consent, lambda: s.save_scenario(self.a, room.pk, scenario.room_version, weights)])
        proposal = m.RoomChoiceProposal.objects.select_related("room", "scenario", "workspace").get(pk=proposal.pk)
        self.assertFalse(s.proposal_confirmed(proposal))
