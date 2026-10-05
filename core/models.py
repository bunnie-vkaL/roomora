"""Roomora Core Models: Identity, Lifestyle, Matching, Chat, Rooms, and Agreements."""
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.db.models import F, Q
from django.utils.functional import cached_property

from .constants import AREAS, GENDER_CHOICES, QUESTIONS


# ==============================================================================
# Storage
# ==============================================================================

class PrivateStorage(FileSystemStorage):
    @cached_property
    def base_location(self):
        return settings.ROOMORA_PRIVATE_MEDIA_ROOT

    def _clear_cached_properties(self, setting, **kwargs):
        super()._clear_cached_properties(setting, **kwargs)
        if setting == "ROOMORA_PRIVATE_MEDIA_ROOT":
            for attr in ("base_location", "location"):
                self.__dict__.pop(attr, None)

    def url(self, name):
        raise ValueError("Private images must be served through the authorized image view.")


def private_image_path(instance, filename):
    return f"rooms/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


# ==============================================================================
# Identity, Survey & Preferences
# ==============================================================================

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

    class Meta:
        indexes = [models.Index(fields=["is_published", "is_synthetic"])]

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


class LivingPreferences(models.Model):
    profile = models.OneToOneField(Profile, on_delete=models.CASCADE, related_name="living")
    move_in_from = models.DateField(null=True, blank=True)
    move_in_until = models.DateField(null=True, blank=True)
    needs = models.CharField(max_length=500, blank=True)
    sleep_at = models.TimeField(null=True, blank=True)
    wake_at = models.TimeField(null=True, blank=True)
    quiet_from = models.TimeField(null=True, blank=True)
    quiet_until = models.TimeField(null=True, blank=True)
    total_monthly_budget = models.PositiveIntegerField(null=True, blank=True)
    upfront_budget = models.PositiveIntegerField(null=True, blank=True)
    notifications_enabled = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)


# ==============================================================================
# Matching, Connections & Safety
# ==============================================================================

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
        indexes = [models.Index(fields=["sender", "status"]), models.Index(fields=["recipient", "status"])]

    def clean(self):
        if self.sender_id == self.recipient_id:
            raise ValidationError("Không thể kết nối với chính mình.")


class Connection(models.Model):
    low = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="connections_low")
    high = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="connections_high")
    active = models.BooleanField(default=False)
    generation = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["low", "high"], name="core_unique_pair"),
            models.CheckConstraint(condition=Q(low__lt=F("high")), name="core_ordered_pair"),
        ]
        indexes = [models.Index(fields=["low", "active"]), models.Index(fields=["high", "active"])]

    def other(self, profile):
        return self.high if self.low_id == profile.pk else self.low


class SwipeDecision(models.Model):
    LIKE, PASS = "like", "pass"
    actor = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="swipes")
    target = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="incoming_swipes")
    choice = models.CharField(max_length=4, choices=[(LIKE, "Muốn kết nối"), (PASS, "Bỏ qua")])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["actor", "target"], name="core_unique_swipe"),
            models.CheckConstraint(condition=~Q(actor=F("target")), name="core_no_self_swipe"),
        ]
        indexes = [models.Index(fields=["actor", "choice", "updated_at"]), models.Index(fields=["target", "choice", "updated_at"])]


class DecisionEvent(models.Model):
    actor = models.ForeignKey(Profile, on_delete=models.CASCADE)
    target = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="decision_events")
    choice = models.CharField(max_length=4)
    previous_choice = models.CharField(max_length=4, blank=True)
    undone = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class SavedCandidate(models.Model):
    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="saved_candidates")
    candidate = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="saved_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "candidate"], name="core_unique_saved")]


class PrivateNote(models.Model):
    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="private_notes")
    candidate = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="notes_about")
    body = models.TextField(max_length=3000, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "candidate"], name="core_unique_note")]


class UserBlock(models.Model):
    actor = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="blocks")
    target = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="blocked_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["actor", "target"], name="core_unique_block")]
        indexes = [models.Index(fields=["target", "actor"])]


class Report(models.Model):
    reporter = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="reports_made")
    target = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="reports_received")
    reason = models.CharField(max_length=1000)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


# ==============================================================================
# Chat & Pinned Facts
# ==============================================================================

class Conversation(models.Model):
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="conversations")
    generation = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["connection", "generation"], name="core_unique_conversation")]


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(Profile, on_delete=models.CASCADE)
    client_id = models.UUIDField(default=uuid.uuid4)
    body = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "sender", "client_id"], name="core_unique_message")]
        ordering = ["pk"]


class PinnedFact(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="facts")
    source = models.ForeignKey(Message, on_delete=models.CASCADE)
    author = models.ForeignKey(Profile, on_delete=models.CASCADE)
    body = models.CharField(max_length=1000)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)


class FactConsent(models.Model):
    fact = models.ForeignKey(PinnedFact, on_delete=models.CASCADE, related_name="consents")
    member = models.ForeignKey(Profile, on_delete=models.CASCADE)
    version = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["fact", "member", "version"], name="core_unique_fact_consent")]


# ==============================================================================
# Shared Workspace, Rooms, Inspection & Consensus
# ==============================================================================

class SearchWorkspace(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="workspaces")
    title = models.CharField(max_length=120, default="Cùng tìm nơi muốn về")
    inviter = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="workspace_invitations")
    invitee = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="workspace_received")
    status = models.CharField(max_length=10, default="pending", choices=[("pending", "Chờ đồng ý"), ("active", "Cùng tìm"), ("declined", "Đã từ chối"), ("closed", "Đã kết thúc")])
    member_version = models.PositiveIntegerField(default=1)
    moving_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation"], condition=Q(status__in=["pending", "active"]), name="core_one_open_workspace")]


class WorkspaceMember(models.Model):
    workspace = models.ForeignKey(SearchWorkspace, on_delete=models.CASCADE, related_name="members")
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="workspaces")
    active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "profile"], name="core_unique_member")]


class RoomOption(models.Model):
    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="room_options")
    workspace = models.ForeignKey(SearchWorkspace, null=True, blank=True, on_delete=models.CASCADE, related_name="rooms")
    source_room = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=120)
    url = models.URLField(max_length=1000, blank=True)
    area = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=250, blank=True)
    notes = models.TextField(max_length=3000, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)


class RoomCost(models.Model):
    PERIODS = [("monthly", "Hàng tháng"), ("initial", "Đầu kỳ / một lần"), ("deposit", "Tiền cọc")]
    STATES = [("unknown", "Chưa biết"), ("estimated", "Ước tính"), ("known", "Đã biết")]
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE, related_name="costs")
    label = models.CharField(max_length=100)
    period = models.CharField(max_length=10, choices=PERIODS)
    state = models.CharField(max_length=10, choices=STATES, default="unknown")
    amount = models.PositiveBigIntegerField(null=True, blank=True)
    source = models.CharField(max_length=250, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=(Q(state="unknown", amount__isnull=True) | Q(state__in=["estimated", "known"], amount__isnull=False)), name="core_cost_state_amount")]


class RoomImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE, related_name="images")
    image = models.FileField(storage=PrivateStorage(), upload_to=private_image_path)
    caption = models.CharField(max_length=200, blank=True)
    creator = models.ForeignKey(Profile, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


class ImagePin(models.Model):
    image = models.ForeignKey(RoomImage, on_delete=models.CASCADE, related_name="pins")
    author = models.ForeignKey(Profile, on_delete=models.CASCADE)
    x = models.FloatField()
    y = models.FloatField()
    question = models.CharField(max_length=500)

    @property
    def x_percent(self):
        return self.x * 100

    @property
    def y_percent(self):
        return self.y * 100

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(x__gte=0, x__lte=1, y__gte=0, y__lte=1), name="core_pin_bounds")]


class RoomOpinion(models.Model):
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE, related_name="opinions")
    member = models.ForeignKey(Profile, on_delete=models.CASCADE)
    choice = models.CharField(max_length=12, choices=[("interested", "Quan tâm"), ("unsure", "Chưa chắc"), ("no", "Không phù hợp")])
    note = models.CharField(max_length=500, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["room", "member"], name="core_unique_room_opinion")]


class CostScenario(models.Model):
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE, related_name="scenarios")
    creator = models.ForeignKey(Profile, on_delete=models.CASCADE)
    room_version = models.PositiveIntegerField()
    weights = models.JSONField(default=dict)
    calculation = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class ViewingPlan(models.Model):
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE, related_name="viewings")
    author = models.ForeignKey(Profile, on_delete=models.CASCADE)
    at = models.DateTimeField()
    meeting_point = models.CharField(max_length=250, blank=True)
    version = models.PositiveIntegerField(default=1)
    cancelled = models.BooleanField(default=False)


class ViewingResponse(models.Model):
    plan = models.ForeignKey(ViewingPlan, on_delete=models.CASCADE, related_name="responses")
    member = models.ForeignKey(Profile, on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    accepted = models.BooleanField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["plan", "member", "version"], name="core_unique_viewing_response")]


class ChecklistItem(models.Model):
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE, related_name="checklist")
    title = models.CharField(max_length=250)
    done = models.BooleanField(default=False)
    note = models.CharField(max_length=500, blank=True)
    checked_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL)
    checked_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)


class ViewingEvidence(models.Model):
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE, related_name="evidence")
    author = models.ForeignKey(Profile, on_delete=models.CASCADE)
    note = models.TextField(max_length=3000)
    image = models.ForeignKey(RoomImage, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class RoomChoiceProposal(models.Model):
    workspace = models.ForeignKey(SearchWorkspace, on_delete=models.CASCADE, related_name="proposals")
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE)
    scenario = models.ForeignKey(CostScenario, on_delete=models.CASCADE)
    proposer = models.ForeignKey(Profile, on_delete=models.CASCADE)
    room_version = models.PositiveIntegerField()
    member_version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class ChoiceConsent(models.Model):
    proposal = models.ForeignKey(RoomChoiceProposal, on_delete=models.CASCADE, related_name="consents")
    member = models.ForeignKey(Profile, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["proposal", "member"], name="core_unique_choice_consent")]


# ==============================================================================
# Living Agreement & Move-in
# ==============================================================================

class Agreement(models.Model):
    workspace = models.OneToOneField(SearchWorkspace, on_delete=models.CASCADE, related_name="agreement")
    choice = models.ForeignKey(RoomChoiceProposal, null=True, blank=True, on_delete=models.SET_NULL)
    clauses = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    member_version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)


class ClauseResponse(models.Model):
    agreement = models.ForeignKey(Agreement, on_delete=models.CASCADE, related_name="responses")
    member = models.ForeignKey(Profile, on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    key = models.CharField(max_length=30)
    accepted = models.BooleanField(default=False)
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["agreement", "member", "version", "key"], name="core_unique_clause_response")]


class AgreementConsent(models.Model):
    agreement = models.ForeignKey(Agreement, on_delete=models.CASCADE, related_name="consents")
    member = models.ForeignKey(Profile, on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["agreement", "member", "version"], name="core_unique_agreement_consent")]


class MoveInTask(models.Model):
    workspace = models.ForeignKey(SearchWorkspace, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=250)
    assignee = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL)
    due_at = models.DateField(null=True, blank=True)
    done = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)


# ==============================================================================
# Telemetry, Mutations, Notifications & Checkpoints
# ==============================================================================

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


class JourneyCheckpoint(models.Model):
    profile = models.OneToOneField(Profile, on_delete=models.CASCADE, related_name="checkpoint")
    workspace = models.ForeignKey(SearchWorkspace, null=True, blank=True, on_delete=models.SET_NULL)
    path = models.CharField(max_length=250)
    updated_at = models.DateTimeField(auto_now=True)


class MutationReceipt(models.Model):
    actor = models.ForeignKey(Profile, on_delete=models.CASCADE)
    action = models.CharField(max_length=100)
    key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    response = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["actor", "action", "key"], name="core_unique_mutation")]


class OutboxEvent(models.Model):
    recipients = models.JSONField(default=list)
    workspace = models.ForeignKey(SearchWorkspace, null=True, blank=True, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    path = models.CharField(max_length=250)
    delivered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    event = models.ForeignKey(OutboxEvent, on_delete=models.CASCADE)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="notifications")
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "profile"], name="core_unique_notification")]
        indexes = [models.Index(fields=["profile", "created_at"]), models.Index(fields=["profile", "read", "created_at"])]
