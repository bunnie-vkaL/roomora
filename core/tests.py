from django.contrib.auth.models import User
from django.test import TestCase
from .constants import AREAS, BUDGET_CHOICES, QUESTIONS
from .forms import ProfileForm
from .models import ConnectionRequest, LifestyleAnswers, Profile
from .scoring import score_profiles


def profile(email, values=None, **extra):
    user = User.objects.create_user(email, email, "strong-password-123")
    data = {"name": f"Người dùng {email.split('@')[0]}", "age": 25, "birth_year": 2001, "hometown": "Hà Nội", "areas": ["Cầu Giấy"], "rent_min": 3000000, "rent_max": 5000000, "contact_type": "zalo", "contact_value": "zalo", "is_published": True}
    data.update(extra)
    item = Profile.objects.create(user=user, **data)
    LifestyleAnswers.objects.create(profile=item, values=values or {key: 0 for key, *_ in QUESTIONS})
    return item


class ScoringTests(TestCase):
    def test_identical_profiles_score_100(self):
        a, b = profile("a@test.com"), profile("b@test.com")
        self.assertEqual(score_profiles(a, b).score, 100)

    def test_scoring_is_symmetric(self):
        left = {key: 0 for key, *_ in QUESTIONS}; right = {key: len(options)-1 for key, _, _, options in QUESTIONS}
        a, b = profile("a@test.com", left), profile("b@test.com", right)
        self.assertEqual(score_profiles(a, b).score, score_profiles(b, a).score)

    def test_pet_allergy_excludes(self):
        values_a = {key: 0 for key, *_ in QUESTIONS}; values_b = values_a.copy(); values_a["has_pet"] = 2; values_b["pet_comfort"] = 0
        self.assertTrue(score_profiles(profile("a@test.com", values_a), profile("b@test.com", values_b)).excluded)

    def test_guest_and_smoking_warnings(self):
        a = {key: 0 for key, *_ in QUESTIONS}; b = a.copy(); a["guest_frequency"] = 4; b["privacy"] = 0; b["smoking"] = 2
        result = score_profiles(profile("a@test.com", a), profile("b@test.com", b))
        self.assertTrue(result.warnings); self.assertLessEqual(result.groups["guests"], 40)


class FlowTests(TestCase):
    def test_profile_form_offers_gender_other_area_and_budget_bounds(self):
        form = ProfileForm()
        self.assertEqual(list(form.fields["gender"].choices)[1:], [("male", "Nam"), ("female", "Nữ")])
        self.assertEqual(AREAS[-1], "Khác")
        self.assertEqual(list(form.fields["rent_min"].choices)[0], (1, "1 đồng"))
        self.assertEqual(list(form.fields["rent_max"].choices)[-1], (100_000_000, "100.000.000 đồng"))
        self.assertIn("birth_year", form.fields)
        self.assertIn("hometown", form.fields)
        self.assertIn("bio", form.fields)

    def test_questionnaire_saves_one_answer_per_page(self):
        item = profile("one-question@test.com", values={})
        self.client.login(username="one-question@test.com", password="strong-password-123")
        response = self.client.get("/questionnaire/?step=1")
        self.assertContains(response, QUESTIONS[0][2])
        self.assertNotContains(response, QUESTIONS[1][2])
        response = self.client.post("/questionnaire/", {"step": "1", QUESTIONS[0][0]: "2", "action": "next"})
        self.assertRedirects(response, "/questionnaire/?step=2")
        item.answers.refresh_from_db()
        self.assertEqual(item.answers.values[QUESTIONS[0][0]], 2)

    def test_contact_is_not_in_discovery_and_requires_acceptance(self):
        a, b = profile("a@test.com"), profile("b@test.com")
        self.client.login(username="a@test.com", password="strong-password-123")
        response = self.client.get("/discover/")
        self.assertContains(response, b.name); self.assertNotContains(response, b.contact_value)
        connection = ConnectionRequest.objects.create(sender=a, recipient=b)
        self.assertEqual(connection.status, "pending")
        response = self.client.get(f"/compare/{b.pk}/")
        self.assertNotContains(response, b.contact_value)
        connection.status = ConnectionRequest.ACCEPTED; connection.save()
        self.assertContains(self.client.get(f"/compare/{b.pk}/"), b.contact_value)

    def test_discovery_requires_area_and_budget_overlap(self):
        a = profile("a@test.com")
        no_area = profile("b@test.com", areas=["Ba Đình"])
        no_budget = profile("c@test.com", rent_min=6000000, rent_max=7000000)
        self.client.login(username="a@test.com", password="strong-password-123")
        response = self.client.get("/discover/")
        self.assertNotContains(response, no_area.name); self.assertNotContains(response, no_budget.name)

    def test_password_reset_renders_done_page(self):
        profile("reset@test.com")
        response = self.client.post("/password-reset/", {"email": "reset@test.com"}, follow=True)
        self.assertContains(response, "Đã gửi hướng dẫn")

    def test_reverse_request_cannot_duplicate_pending_connection(self):
        a, b = profile("a@test.com"), profile("b@test.com")
        ConnectionRequest.objects.create(sender=a, recipient=b)
        self.client.login(username="b@test.com", password="strong-password-123")
        self.client.post(f"/connect/{a.pk}/")
        self.assertEqual(ConnectionRequest.objects.count(), 1)

    def test_either_connected_user_can_block(self):
        a, b = profile("a@test.com"), profile("b@test.com")
        connection = ConnectionRequest.objects.create(sender=a, recipient=b, status=ConnectionRequest.ACCEPTED)
        self.client.login(username="a@test.com", password="strong-password-123")
        self.client.post(f"/connections/{connection.pk}/block/")
        connection.refresh_from_db()
        self.assertEqual(connection.status, ConnectionRequest.BLOCKED)
