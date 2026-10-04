from datetime import date, datetime, time

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from .constants import AREAS, BUDGET_CHOICES, QUESTIONS, QUESTION_WEIGHTS
from .forms import ProfileForm
from .models import ConnectionRequest, LifestyleAnswers, Profile
from .scoring import _calibrate, _similarity, score_profiles
from .management.commands.import_sample_profiles import parse_row, simulated_living


def profile(email, values=None, **extra):
    user = User.objects.create_user(email, email, "strong-password-123")
    data = {"name": f"Người dùng {email.split('@')[0]}", "age": 25, "birth_year": 2001, "hometown": "Hà Nội", "areas": ["Cầu Giấy"], "rent_min": 3000000, "rent_max": 5000000, "contact_type": "zalo", "contact_value": "zalo", "is_published": True}
    data.update(extra)
    item = Profile.objects.create(user=user, **data)
    LifestyleAnswers.objects.create(profile=item, values=values if values is not None else {key: 0 for key, *_ in QUESTIONS})
    return item


class AvatarValidationTests(SimpleTestCase):
    def clean_upload(self, data, name="claimed.jpg", content_type="image/jpeg"):
        from django.core.files.uploadedfile import SimpleUploadedFile
        form = ProfileForm()
        form.cleaned_data = {"avatar": SimpleUploadedFile(name, data, content_type=content_type)}
        return form.clean_avatar()

    def test_mime_and_extension_cannot_make_non_image_valid(self):
        from django.core.exceptions import ValidationError
        for name, mime in (("photo.jpg", "image/jpeg"), ("photo.txt", "image/png"),
                           ("photo.png", "text/html")):
            with self.assertRaises(ValidationError):
                self.clean_upload(b"<html>not image bytes</html>", name, mime)

    def test_verified_pixels_are_reencoded_with_safe_name_and_no_metadata(self):
        from io import BytesIO
        from PIL import Image, PngImagePlugin
        stream = BytesIO()
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("private-location", "do-not-publish")
        Image.new("RGBA", (12, 8), (30, 80, 140, 90)).save(stream, format="PNG", pnginfo=metadata)
        original = stream.getvalue() + b"APPENDED-INPUT-CONTENT"
        upload = self.clean_upload(original, "misleading.jpg", "text/html")
        self.assertRegex(upload.name, r"^[0-9a-f]{32}\.png$")
        self.assertEqual(upload.content_type, "image/png")
        self.assertNotIn(b"APPENDED-INPUT-CONTENT", upload.read())
        upload.seek(0)
        with Image.open(upload) as image:
            self.assertEqual(image.size, (12, 8))
            self.assertNotIn("private-location", image.info)
            self.assertEqual(image.getpixel((0, 0)), (30, 80, 140, 90))

    def test_unsupported_actual_format_and_oversize_upload_are_rejected(self):
        from io import BytesIO
        from PIL import Image
        from django.core.exceptions import ValidationError
        stream = BytesIO()
        Image.new("RGB", (2, 2)).save(stream, format="BMP")
        for data in (stream.getvalue(), b"x" * (5 * 1024 * 1024 + 1)):
            with self.assertRaises(ValidationError):
                self.clean_upload(data)


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

    def test_match_reasons_show_answers_instead_of_survey_questions(self):
        base = {key: 0 for key, *_ in QUESTIONS}
        changed = base.copy()
        changed["D4"] = 2
        a = profile("answers-a@test.com", base)
        b = profile("answers-b@test.com", changed)
        result = score_profiles(a, b)
        self.assertTrue(any("cả hai chọn “Rất sạch, gọn mỗi ngày”" in reason
                            for reason in result.similarities))
        self.assertTrue(any("Tiếng ồn: bạn “Rất yên tĩnh”, người ấy “Hơi ồn”" in reason
                            for reason in result.differences))
        self.assertFalse(any(question in reason for reason in result.similarities + result.differences
                             for _, _, question, _ in QUESTIONS))

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


class SampleLivingTests(TestCase):
    def test_import_fills_missing_survey_and_behavior_without_changing_source_cells(self):
        headers = [f"Cột {index}" for index in range(48)]
        row = [None] * 48
        row[0], row[1], row[2] = "RM001", "Nguyễn Hoài Vy", "Nữ"
        row[3], row[4] = datetime(2003, 1, 1), 23
        row[16], row[17], row[19], row[21] = 3, 3.5, datetime(2026, 11, 1), 3
        row[39], row[42], row[44] = 0, 0, 0
        item = parse_row(row, headers, 2)
        self.assertEqual(len(item["answers"]), 16)
        self.assertEqual(len(item["estimated_answers"]), 16)
        self.assertIsNone(item["source_data"][headers[22]])
        self.assertEqual(len(item["behavior_metrics"]["estimated_fields"]), 4)
        self.assertGreater(item["behavior_metrics"]["payment_on_time_pct"], 0)

    def test_simulated_routine_follows_lifestyle_and_is_repeatable(self):
        item = {
            "source_id": "RM001", "answers": {"A1": 0, "B1": 0, "C1": 0, "A3": 3, "D4": 0},
            "move_in_from": date(2026, 11, 1), "rent_max": 3_500_000, "min_stay_months": 3,
        }
        living = simulated_living(item)
        self.assertEqual(living, simulated_living(item))
        self.assertEqual(living["sleep_at"], time(22))
        self.assertEqual(living["wake_at"], time(6))
        self.assertEqual(living["quiet_from"], time(20))
        self.assertIn("Cần góc làm việc tại nhà", living["needs"])
        self.assertIn("3 tháng", living["needs"])
        self.assertLessEqual(len(living["needs"]), 500)


class FlowTests(TestCase):
    def test_dashboard_guides_new_users_and_sends_completed_users_to_one_recommendation_page(self):
        newcomer = profile("new@test.com", values={}, is_published=False, areas=[], rent_min=0, rent_max=0, contact_value="")
        self.client.force_login(newcomer.user)
        response = self.client.get("/dashboard/")
        self.assertContains(response, "Bắt đầu hồ sơ")
        self.assertContains(response, "Lifestyle")
        newcomer.areas = ["Cầu Giấy"]
        newcomer.rent_min = 3_000_000
        newcomer.rent_max = 5_000_000
        newcomer.contact_value = "zalo"
        newcomer.save()
        newcomer.answers.values = {key: 0 for key, *_ in QUESTIONS}
        newcomer.answers.save()
        newcomer.is_published = True
        newcomer.save()
        self.assertRedirects(self.client.get("/dashboard/"), "/together/discover/")

    def test_about_shows_area_recommendations_only_for_selected_profile_area(self):
        self.assertContains(self.client.get("/about/"), "Gợi ý theo khu vực")
        actor = profile("area-a@test.com")
        other = profile("area-b@test.com")
        self.client.force_login(actor.user)
        response = self.client.get("/about/?area=C%E1%BA%A7u%20Gi%E1%BA%A5y")
        self.assertContains(response, other.name)
        response = self.client.get("/about/?area=Ba%20%C4%90%C3%ACnh")
        self.assertNotContains(response, other.name)
        self.assertContains(response, "Cập nhật khu vực")

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

    def test_survey_resumes_first_valid_missing_answer_and_preserves_navigation(self):
        item = profile("resume-survey@test.com", values={"A1": 1, "A2": True, "A3": 99}, is_published=False)
        self.client.force_login(item.user)
        response = self.client.get("/questionnaire/")
        self.assertEqual(response.context["step"], 2)
        self.assertEqual(response.context["answered_count"], 1)
        self.assertContains(response, 'aria-valuenow="1"')
        before = item.answers.values.copy()
        self.client.get("/questionnaire/?step=1")
        item.answers.refresh_from_db()
        self.assertEqual(item.answers.values, before)
        self.assertRedirects(self.client.post("/questionnaire/", {"step": 2, "A2": 1, "action": "next"}), "/questionnaire/?step=3")
        self.assertEqual(self.client.get("/questionnaire/").context["step"], 3)
        response = self.client.get("/questionnaire/?step=2")
        self.assertEqual(response.context["form"]["A2"].value(), 1)

    def test_survey_invalid_submission_does_not_save_or_publish(self):
        item = profile("invalid-survey@test.com", values={}, is_published=False)
        self.client.force_login(item.user)
        for value in ("", "99", "true"):
            response = self.client.post("/questionnaire/", {"step": 1, "A1": value, "action": "next"})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'role="alert"')
            item.answers.refresh_from_db()
            self.assertEqual(item.answers.values, {})
        item.refresh_from_db()
        self.assertFalse(item.is_published)

    def test_survey_publication_requires_explicit_complete_submit(self):
        item = profile("finish-survey@test.com", is_published=False)
        self.client.force_login(item.user)
        self.client.get("/questionnaire/?step=16")
        item.refresh_from_db()
        self.assertFalse(item.is_published)
        response = self.client.post("/questionnaire/", {"step": 16, "F2": 1, "action": "next"})
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertTrue(item.is_published)
        self.assertEqual(item.questionnaire_version, "2026.2")

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
    def test_recommendations_show_person_names_without_placeholder_profiles(self):
        user_profile = profile("tester@test.com", areas=["Cầu Giấy", "Đống Đa"], rent_min=3000000, rent_max=5000000)
        named = profile("sample-rm001@roomora.local", name="Nguyễn Hoài Vy", is_synthetic=True)
        profile("sample-01@roomora.local", name="Mẫu thử #01", is_synthetic=True)
        profile("freshuser@roomora.local", name="freshuser")
        self.client.login(username="tester@test.com", password="strong-password-123")
        response = self.client.get("/discover/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, named.name)
        self.assertNotContains(response, "Mẫu thử #01")
        self.assertNotContains(response, "freshuser")
        self.assertContains(response, "99%")
        # Ensure private personal information is not exposed on candidate cards
        self.assertNotContains(response, "tester@test.com")
        self.assertNotContains(response, "candidate-card__bio")
