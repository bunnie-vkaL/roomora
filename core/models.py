from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from .constants import AREAS, GENDER_CHOICES, QUESTIONS


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    name = models.CharField(max_length=80)
    age = models.PositiveSmallIntegerField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True)
    hometown = models.CharField(max_length=100, blank=True)
    bio = models.CharField(max_length=280, blank=True)
    avatar = models.FileField(upload_to="avatars/", blank=True, null=True)
    areas = models.JSONField(default=list)
    rent_min = models.PositiveIntegerField()
    rent_max = models.PositiveIntegerField()
    contact_type = models.CharField(max_length=10, choices=[("zalo", "Zalo"), ("phone", "Điện thoại")])
    contact_value = models.CharField(max_length=100)
    is_published = models.BooleanField(default=False)
    is_synthetic = models.BooleanField(default=False)
    questionnaire_version = models.CharField(max_length=20, default="2026.2")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.age < 18:
            raise ValidationError({"age": "Bạn cần từ 18 tuổi trở lên."})
        if self.birth_year and not 1900 <= self.birth_year <= 2008:
            raise ValidationError({"birth_year": "Năm sinh phải nằm trong khoảng 1900 đến 2008."})
        if self.rent_min > self.rent_max:
            raise ValidationError({"rent_max": "Mức tối đa phải lớn hơn hoặc bằng mức tối thiểu."})
        if not 1 <= self.rent_min <= 100_000_000 or not 1 <= self.rent_max <= 100_000_000:
            raise ValidationError("Ngân sách phải nằm trong khoảng 1 đồng đến 100 triệu đồng mỗi tháng.")
        if not self.areas or any(area not in AREAS for area in self.areas):
            raise ValidationError({"areas": "Chọn ít nhất một khu vực Hà Nội hợp lệ."})

    @property
    def completed(self):
        return hasattr(self, "answers") and self.answers.is_complete

    @property
    def rent_display(self):
        if not self.rent_min and not self.rent_max:
            return "Chưa cập nhật"
        return f"{self.rent_min:,} – {self.rent_max:,} đ/tháng".replace(",", ".")


def recommendable_profiles():
    """Profiles with a person's name that may appear in recommendation lists."""

    candidates = Profile.objects.filter(is_published=True)
    candidates = candidates.exclude(name__iexact="freshuser").exclude(name__iexact="Tài khoản thử nghiệm")
    if settings.DEBUG:
        return candidates.filter(
            models.Q(is_synthetic=False)
            | models.Q(is_synthetic=True, user__username__startswith="sample-rm")
        )
    return candidates.filter(is_synthetic=False)


class LifestyleAnswers(models.Model):
    profile = models.OneToOneField(Profile, on_delete=models.CASCADE, related_name="answers")
    values = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_complete(self):
        return all(type(self.values.get(key)) is int and 0 <= self.values[key] < len(options)
                   for key, _, _, options in QUESTIONS)


class ImportedSampleProfile(models.Model):
    """Original spreadsheet fields that the live profile schema does not model yet."""

    profile = models.OneToOneField(Profile, on_delete=models.CASCADE, related_name="sample_source")
    source_id = models.CharField(max_length=20, unique=True)
    source_data = models.JSONField(default=dict)
    estimated_answers = models.JSONField(default=list)
    behavior_metrics = models.JSONField(default=dict)
    imported_at = models.DateTimeField(auto_now=True)


class ConnectionRequest(models.Model):
    PENDING, ACCEPTED, DECLINED, WITHDRAWN, BLOCKED = "pending", "accepted", "declined", "withdrawn", "blocked"
    STATUS_CHOICES = [(PENDING, "Đang chờ"), (ACCEPTED, "Đã kết nối"), (DECLINED, "Đã từ chối"), (WITHDRAWN, "Đã thu hồi"), (BLOCKED, "Đã chặn")]
    sender = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="sent_requests")
    recipient = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="received_requests")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["sender", "recipient"], name="unique_connection_direction")]

    def clean(self):
        if self.sender_id == self.recipient_id:
            raise ValidationError("Không thể kết nối với chính mình.")


class PilotExercise(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    score_first = models.BooleanField()
    candidate_ids = models.JSONField(default=list)
    basic_choice = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name="basic_choices")
    score_choice = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name="score_choices")
    basic_trust = models.PositiveSmallIntegerField(null=True, blank=True)
    score_trust = models.PositiveSmallIntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class PilotEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    kind = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
