from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.tests import profile
from . import models as m, services as s
from .views import room_cost_overview


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RoomOverviewTests(TestCase):
    def setUp(self):
        self.actor = profile("overview-a@example.invalid")
        self.other = profile("overview-b@example.invalid")

    def test_missing_price_is_not_zero_and_explicit_zero_stays_zero(self):
        room = m.RoomOption.objects.create(owner=self.actor, title="Chưa hỏi giá")
        overview = room_cost_overview(room)
        self.assertIsNone(overview["monthly"])
        self.assertIsNone(overview["upfront"])
        self.assertEqual(overview["missing_count"], 3)
        for period in ("monthly", "initial", "deposit"):
            m.RoomCost.objects.create(room=room, label=period, period=period, state="known", amount=0)
        overview = room_cost_overview(room)
        self.assertEqual(overview["monthly"], 0)
        self.assertEqual(overview["upfront"], 0)
        self.assertFalse(overview["upfront_partial"])
        self.assertEqual(overview["missing_count"], 0)

    def test_partial_estimates_show_only_entered_totals_for_the_whole_room(self):
        room = m.RoomOption.objects.create(owner=self.actor, title="Đang xác minh")
        for label, period, state, amount in (
            ("Thuê", "monthly", "known", 6000000),
            ("Điện", "monthly", "estimated", 300000),
            ("Nước", "monthly", "unknown", None),
            ("Cọc", "deposit", "known", 6000000),
        ):
            m.RoomCost.objects.create(room=room, label=label, period=period, state=state, amount=amount)
        overview = room_cost_overview(room)
        self.assertEqual(overview["monthly"], 6300000)
        self.assertEqual(overview["upfront"], 12300000)
        self.assertTrue(overview["monthly_partial"])
        self.assertTrue(overview["upfront_partial"])
        self.assertTrue(overview["estimated"])
        self.client.force_login(self.actor.user)
        response = self.client.get(reverse("journey:rooms"), secure=True)
        self.assertContains(response, "6.300.000 đ")
        self.assertContains(response, "Hàng tháng · đã nhập")
        self.assertContains(response, "Có khoản ước tính")

    def test_cost_loading_uses_two_queries_for_many_cards(self):
        for index in range(12):
            room = m.RoomOption.objects.create(owner=self.actor, title=f"Căn {index}")
            m.RoomCost.objects.create(room=room, label="Thuê", period="monthly", state="known", amount=3000000)
        with CaptureQueriesContext(connection) as queries:
            options = list(self.actor.room_options.prefetch_related("costs"))
            results = [room_cost_overview(option) for option in options]
        self.assertEqual(len(queries), 2)
        self.assertEqual(len(results), 12)

    def test_unknown_deposit_stays_unknown_on_detail_and_comparison(self):
        unknown = m.RoomOption.objects.create(owner=self.actor, title="Chưa có dữ kiện")
        zero = m.RoomOption.objects.create(owner=self.actor, title="Đã hỏi và không thu cọc")
        for period in ("monthly", "initial", "deposit"):
            m.RoomCost.objects.create(room=zero, label=period, period=period, state="known", amount=0)
        self.client.force_login(self.actor.user)
        detail = self.client.get(reverse("journey:room", args=[unknown.pk]), secure=True)
        self.assertContains(detail, "cọc Chưa biết")
        self.assertIsNone(detail.context["calculation"]["display_totals"]["deposit"])
        response = self.client.get(reverse("journey:room-compare"), {"room": [unknown.pk, zero.pk]}, secure=True)
        first, second = response.context["options"]
        self.assertIsNone(first["calculation"]["members"][0]["display"]["deposit"])
        self.assertEqual(second["calculation"]["display_totals"]["deposit"], 0)
        self.assertContains(response, "cọc Chưa biết")
        self.assertContains(response, "cọc 0 đ")

    def test_private_rooms_and_shared_boards_obey_current_access(self):
        mine = m.RoomOption.objects.create(owner=self.actor, title="Riêng của An")
        m.RoomOption.objects.create(owner=self.other, title="Riêng của Bình")
        s.decide(self.actor, self.other, "like")
        conversation = s.decide(self.other, self.actor, "like")
        workspace = s.invite_workspace(self.actor, conversation.pk, "Bảng nhà của hai người")
        s.respond_workspace(self.other, workspace.pk, True)
        m.RoomOption.objects.create(owner=self.other, workspace=workspace, title="Căn chung")
        self.client.force_login(self.actor.user)
        response = self.client.get(reverse("journey:rooms"), secure=True)
        self.assertEqual([room.pk for room in response.context["rooms"]], [mine.pk])
        self.assertEqual(response.context["workspaces"][0].room_count, 1)
        self.assertNotContains(response, "Riêng của Bình")
        board = self.client.get(reverse("journey:workspace", args=[workspace.pk]), secure=True)
        self.assertContains(board, "Căn chung")
        self.assertContains(board, "Chưa biết")
        block = m.UserBlock.objects.create(actor=self.other, target=self.actor)
        self.assertEqual(self.client.get(reverse("journey:rooms"), secure=True).context["workspaces"], [])
        self.assertEqual(self.client.get(reverse("journey:workspace", args=[workspace.pk]), secure=True).status_code, 403)
        block.delete()
        link = conversation.connection
        link.generation += 1
        link.save(update_fields=["generation"])
        self.assertEqual(self.client.get(reverse("journey:rooms"), secure=True).context["workspaces"], [])
