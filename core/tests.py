from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from .constants import AREAS, BUDGET_CHOICES, QUESTIONS, QUESTION_WEIGHTS
from .forms import ProfileForm
from .models import ConnectionRequest, LifestyleAnswers, Profile
from .scoring import _calibrate, _similarity, score_profiles


def profile(email, values=None, **extra):
    user = User.objects.create_user(email, email, "strong-password-123")
    data = {"name": f"Người dùng {email.split('@')[0]}", "age": 25, "birth_year": 2001, "hometown": "Hà Nội", "areas": ["Cầu Giấy"], "rent_min": 3000000, "rent_max": 5000000, "contact_type": "zalo", "contact_value": "zalo", "is_published": True}
    data.update(extra)
    item = Profile.objects.create(user=user, **data)
    LifestyleAnswers.objects.create(profile=item, values=values if values is not None else {key: 0 for key, *_ in QUESTIONS})
    return item


class ScoringTests(TestCase):
    def test_survey_has_source_weights_and_calibration(self):
        self.assertEqual(len(QUESTIONS), 16)
        self.assertAlmostEqual(sum(QUESTION_WEIGHTS.values()), .92)
        self.assertEqual(_calibrate(.613), 50)
        self.assertEqual(_calibrate(.710), 78)
        self.assertEqual(_calibrate(1.15), 99)
        self.assertAlmostEqual(_similarity("C2", 0, 1), .85)
        self.assertAlmostEqual(_similarity("A1", 0, 1), 11 / 12)

    def test_identical_profiles_score_99_with_budget_bonus(self):
        a, b = profile("a@test.com"), profile("b@test.com")
        self.assertEqual(score_profiles(a, b).score, 99)

    def test_scoring_is_symmetric(self):
        left = {key: 0 for key, *_ in QUESTIONS}; right = left.copy()
        right.update(A1=1, A2=1, B1=1, C2=1, D4=1, E1=1, F2=1)
        a, b = profile("a@test.com", left), profile("b@test.com", right)
        self.assertEqual(score_profiles(a, b).score, score_profiles(b, a).score)

    def test_pet_allergy_excludes(self):
        values_a = {key: 0 for key, *_ in QUESTIONS}; values_b = values_a.copy(); values_a["D3"] = 1; values_b["D2"] = 2
        self.assertTrue(score_profiles(profile("a@test.com", values_a), profile("b@test.com", values_b)).excluded)

    def test_hard_conflict_and_cross_penalty(self):
        base = {key: 0 for key, *_ in QUESTIONS}
        mismatch = base.copy(); mismatch["B1"] = 2
        self.assertTrue(score_profiles(profile("a@test.com", base), profile("b@test.com", mismatch)).excluded)
        quiet = base.copy(); noisy = base.copy(); noisy["D4"] = 2
        quiet_profile = profile("c@test.com", quiet); noisy_profile = profile("d@test.com", noisy)
        result = score_profiles(quiet_profile, noisy_profile)
        self.assertFalse(result.excluded)
        self.assertLess(result.score, score_profiles(quiet_profile, quiet_profile).score)
        self.assertTrue(any("xung đột" in warning for warning in result.warnings))

    def test_invalid_or_legacy_answers_do_not_score(self):
        old = profile("old@test.com", values={"bedtime": 0})
        new = profile("new@test.com")
        self.assertIsNone(score_profiles(old, new).score)
        old.answers.values = new.answers.values.copy()
        old.answers.save()
        old.questionnaire_version = "2026.1"
        old.save(update_fields=["questionnaire_version"])
        self.assertIsNone(score_profiles(old, new).score)


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

    def test_cannot_publish_by_jumping_to_final_question(self):
        item = profile("skip@test.com", values={}, is_published=False)
        self.client.login(username="skip@test.com", password="strong-password-123")
        self.client.post("/questionnaire/", {"step": "16", QUESTIONS[-1][0]: "1", "action": "next"})
        item.refresh_from_db()
        self.assertFalse(item.is_published)

    def test_excluded_pair_cannot_connect(self):
        clean = {key: 0 for key, *_ in QUESTIONS}
        different = clean.copy(); different["B1"] = 3
        sender = profile("clean@test.com", clean)
        recipient = profile("messy@test.com", different)
        self.client.login(username="clean@test.com", password="strong-password-123")
        self.assertEqual(self.client.post(f"/connect/{recipient.pk}/").status_code, 403)
        self.assertFalse(ConnectionRequest.objects.filter(sender=sender, recipient=recipient).exists())

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

    @override_settings(DEBUG=True)
    def test_sample_candidate_matching_and_anonymous_rendering(self):
        user_profile = profile("tester@test.com", areas=["Cầu Giấy", "Đống Đa"], rent_min=3000000, rent_max=5000000)
        self.client.login(username="tester@test.com", password="strong-password-123")
        response = self.client.get("/discover/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mẫu thử #01")
        self.assertContains(response, "99%")
        # Ensure private personal information is not exposed on candidate cards
        self.assertNotContains(response, "tester@test.com")
        self.assertNotContains(response, "candidate-card__bio")
