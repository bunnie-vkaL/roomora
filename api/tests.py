import uuid
from django.contrib.auth.models import User
from django.test import TransactionTestCase
from starlette.testclient import TestClient
from core.models import LifestyleAnswers, Profile
from core.constants import QUESTIONS
from core import models as m
from api.main import api_app


def create_test_profile(username, **extra):
    user = User.objects.create_user(username, f"{username}@test.local", "test-pass-123")
    defaults = {
        "name": f"User {username}",
        "age": 22,
        "birth_year": 2004,
        "hometown": "Hà Nội",
        "areas": ["Cầu Giấy", "Đống Đa"],
        "rent_min": 2_000_000,
        "rent_max": 5_000_000,
        "contact_type": "zalo",
        "contact_value": "0987654321",
        "is_published": True,
    }
    defaults.update(extra)
    profile = Profile.objects.create(user=user, **defaults)
    LifestyleAnswers.objects.create(
        profile=profile,
        values={key: 0 for key, *_ in QUESTIONS},
    )
    return profile


class FastApiBridgeTests(TransactionTestCase):
    def setUp(self):
        self.client = TestClient(api_app)
        self.profile1 = create_test_profile("user1")
        self.profile2 = create_test_profile("user2")

    def test_health_check(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_openapi_docs(self):
        resp = self.client.get("/docs")
        self.assertEqual(resp.status_code, 200)
        resp_json = self.client.get("/openapi.json")
        self.assertEqual(resp_json.status_code, 200)
        schema = resp_json.json()
        self.assertIn("paths", schema)
        self.assertIn("/v1/discovery/swipe", schema["paths"])
        self.assertIn("/v1/costs/calculate", schema["paths"])

    def test_swipe_like_and_pass(self):
        mutation_key = str(uuid.uuid4())
        resp = self.client.post(
            "/v1/discovery/swipe",
            json={
                "target_id": self.profile2.pk,
                "choice": "like",
                "mutation_key": mutation_key,
            },
            headers={"X-User-ID": str(self.profile1.user.pk)},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["matched"])
        self.assertEqual(data["choice"], "like")

        # Reciprocal like from profile2 creates mutual match
        reciprocal_key = str(uuid.uuid4())
        resp2 = self.client.post(
            "/v1/discovery/swipe",
            json={
                "target_id": self.profile1.pk,
                "choice": "like",
                "mutation_key": reciprocal_key,
            },
            headers={"X-User-ID": str(self.profile2.user.pk)},
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertTrue(data2["matched"])
        self.assertIsNotNone(data2["conversation_id"])

    def test_undo_swipe(self):
        profile3 = create_test_profile("user3")
        swipe_key = str(uuid.uuid4())
        self.client.post(
            "/v1/discovery/swipe",
            json={
                "target_id": profile3.pk,
                "choice": "pass",
                "mutation_key": swipe_key,
            },
            headers={"X-User-ID": str(self.profile1.user.pk)},
        )
        self.assertTrue(m.SwipeDecision.objects.filter(actor=self.profile1, target=profile3, choice="pass").exists())

        undo_key = str(uuid.uuid4())
        resp = self.client.post(
            "/v1/discovery/undo",
            json={"mutation_key": undo_key},
            headers={"X-User-ID": str(self.profile1.user.pk)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(m.SwipeDecision.objects.filter(actor=self.profile1, target=profile3).exists())

    def test_save_and_unsave_candidate(self):
        save_key = str(uuid.uuid4())
        resp = self.client.post(
            "/v1/discovery/save",
            json={
                "candidate_id": self.profile2.pk,
                "saved": True,
                "mutation_key": save_key,
            },
            headers={"X-User-ID": str(self.profile1.user.pk)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(m.SavedCandidate.objects.filter(owner=self.profile1, candidate=self.profile2).exists())

        unsave_key = str(uuid.uuid4())
        resp_unsave = self.client.post(
            "/v1/discovery/save",
            json={
                "candidate_id": self.profile2.pk,
                "saved": False,
                "mutation_key": unsave_key,
            },
            headers={"X-User-ID": str(self.profile1.user.pk)},
        )
        self.assertEqual(resp_unsave.status_code, 200)
        self.assertFalse(m.SavedCandidate.objects.filter(owner=self.profile1, candidate=self.profile2).exists())

    def test_costs_calculate_integer_vnd(self):
        resp = self.client.post(
            "/v1/costs/calculate",
            json={
                "costs": [
                    {"label": "Tiền phòng", "period": "monthly", "state": "known", "amount": 6_000_000, "source": "Chủ nhà"},
                    {"label": "Tiền cọc", "period": "deposit", "state": "known", "amount": 6_000_000, "source": "Hợp đồng"},
                    {"label": "Đồ dùng ban đầu", "period": "initial", "state": "known", "amount": 1_000_000, "source": "Ước tính"},
                ],
                "weights": {str(self.profile1.pk): 1},
            },
            headers={"X-User-ID": str(self.profile1.user.pk)},
        )
        self.assertEqual(resp.status_code, 200)
        calc = resp.json()
        self.assertEqual(calc["totals"]["monthly"], 6_000_000)
        self.assertEqual(calc["totals"]["deposit"], 6_000_000)
        self.assertEqual(calc["totals"]["initial"], 1_000_000)
        self.assertTrue(calc["complete"])
        self.assertEqual(calc["members"][0]["upfront"], 13_000_000)

    def test_unauthenticated_request_rejected(self):
        resp = self.client.post(
            "/v1/discovery/swipe",
            json={
                "target_id": self.profile2.pk,
                "choice": "like",
                "mutation_key": str(uuid.uuid4()),
            },
        )
        self.assertEqual(resp.status_code, 401)
