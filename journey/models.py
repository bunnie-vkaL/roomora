"""Persistent records for the roommate journey. Consent always belongs to a version."""
import uuid
from pathlib import Path

from django.conf import settings
from core.storage import BudgetFileSystemStorage
from django.db import models
from django.db.models import F, Q
from django.utils.functional import cached_property


class PrivateStorage(BudgetFileSystemStorage):
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


class LivingPreferences(models.Model):
    profile = models.OneToOneField("core.Profile", on_delete=models.CASCADE, related_name="living")
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


class Connection(models.Model):
    low = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="connections_low")
    high = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="connections_high")
    active = models.BooleanField(default=False)
    generation = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["low", "high"], name="journey_unique_pair"),
            models.CheckConstraint(condition=Q(low__lt=F("high")), name="journey_ordered_pair"),
        ]

    def other(self, profile):
        return self.high if self.low_id == profile.pk else self.low


class SwipeDecision(models.Model):
    LIKE, PASS = "like", "pass"
    actor = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="swipes")
    target = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="incoming_swipes")
    choice = models.CharField(max_length=4, choices=[(LIKE, "Muốn kết nối"), (PASS, "Bỏ qua")])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["actor", "target"], name="journey_unique_swipe"),
            models.CheckConstraint(condition=~Q(actor=F("target")), name="journey_no_self_swipe"),
        ]


class DecisionEvent(models.Model):
    actor = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    target = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="decision_events")
    choice = models.CharField(max_length=4)
    previous_choice = models.CharField(max_length=4, blank=True)
    undone = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class SavedCandidate(models.Model):
    owner = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="saved_candidates")
    candidate = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="saved_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "candidate"], name="journey_unique_saved")]


class PrivateNote(models.Model):
    owner = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="private_notes")
    candidate = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="notes_about")
    body = models.TextField(max_length=3000, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "candidate"], name="journey_unique_note")]


class UserBlock(models.Model):
    actor = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="blocks")
    target = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="blocked_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["actor", "target"], name="journey_unique_block")]


class Report(models.Model):
    reporter = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="reports_made")
    target = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="reports_received")
    reason = models.CharField(max_length=1000)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class Conversation(models.Model):
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="conversations")
    generation = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["connection", "generation"], name="journey_unique_conversation")]


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    client_id = models.UUIDField(default=uuid.uuid4)
    body = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "sender", "client_id"], name="journey_unique_message")]
        ordering = ["pk"]


class PinnedFact(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="facts")
    source = models.ForeignKey(Message, on_delete=models.CASCADE)
    author = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    body = models.CharField(max_length=1000)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)


class FactConsent(models.Model):
    fact = models.ForeignKey(PinnedFact, on_delete=models.CASCADE, related_name="consents")
    member = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    version = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["fact", "member", "version"], name="journey_unique_fact_consent")]


class SearchWorkspace(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="workspaces")
    title = models.CharField(max_length=120, default="Cùng tìm nơi muốn về")
    inviter = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="workspace_invitations")
    invitee = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="workspace_received")
    status = models.CharField(max_length=10, default="pending", choices=[("pending", "Chờ đồng ý"), ("active", "Cùng tìm"), ("declined", "Đã từ chối"), ("closed", "Đã kết thúc")])
    member_version = models.PositiveIntegerField(default=1)
    moving_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation"], condition=Q(status__in=["pending", "active"]), name="journey_one_open_workspace")]


class WorkspaceMember(models.Model):
    workspace = models.ForeignKey(SearchWorkspace, on_delete=models.CASCADE, related_name="members")
    profile = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="workspaces")
    active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "profile"], name="journey_unique_member")]


class RoomOption(models.Model):
    owner = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="room_options")
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
        constraints = [models.CheckConstraint(condition=(Q(state="unknown", amount__isnull=True) | Q(state__in=["estimated", "known"], amount__isnull=False)), name="journey_cost_state_amount")]


class RoomImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE, related_name="images")
    image = models.FileField(storage=PrivateStorage(), upload_to=private_image_path)
    caption = models.CharField(max_length=200, blank=True)
    creator = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


class ImagePin(models.Model):
    image = models.ForeignKey(RoomImage, on_delete=models.CASCADE, related_name="pins")
    author = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
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
        constraints = [models.CheckConstraint(condition=Q(x__gte=0, x__lte=1, y__gte=0, y__lte=1), name="journey_pin_bounds")]


class RoomOpinion(models.Model):
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE, related_name="opinions")
    member = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    choice = models.CharField(max_length=12, choices=[("interested", "Quan tâm"), ("unsure", "Chưa chắc"), ("no", "Không phù hợp")])
    note = models.CharField(max_length=500, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["room", "member"], name="journey_unique_room_opinion")]


class CostScenario(models.Model):
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE, related_name="scenarios")
    creator = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    room_version = models.PositiveIntegerField()
    weights = models.JSONField(default=dict)
    calculation = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class ViewingPlan(models.Model):
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE, related_name="viewings")
    author = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    at = models.DateTimeField()
    meeting_point = models.CharField(max_length=250, blank=True)
    version = models.PositiveIntegerField(default=1)
    cancelled = models.BooleanField(default=False)


class ViewingResponse(models.Model):
    plan = models.ForeignKey(ViewingPlan, on_delete=models.CASCADE, related_name="responses")
    member = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    accepted = models.BooleanField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["plan", "member", "version"], name="journey_unique_viewing_response")]


class ChecklistItem(models.Model):
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE, related_name="checklist")
    title = models.CharField(max_length=250)
    done = models.BooleanField(default=False)
    note = models.CharField(max_length=500, blank=True)
    checked_by = models.ForeignKey("core.Profile", null=True, blank=True, on_delete=models.SET_NULL)
    checked_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)


class ViewingEvidence(models.Model):
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE, related_name="evidence")
    author = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    note = models.TextField(max_length=3000)
    image = models.ForeignKey(RoomImage, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class RoomChoiceProposal(models.Model):
    workspace = models.ForeignKey(SearchWorkspace, on_delete=models.CASCADE, related_name="proposals")
    room = models.ForeignKey(RoomOption, on_delete=models.CASCADE)
    scenario = models.ForeignKey(CostScenario, on_delete=models.CASCADE)
    proposer = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    room_version = models.PositiveIntegerField()
    member_version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class ChoiceConsent(models.Model):
    proposal = models.ForeignKey(RoomChoiceProposal, on_delete=models.CASCADE, related_name="consents")
    member = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["proposal", "member"], name="journey_unique_choice_consent")]


class Agreement(models.Model):
    workspace = models.OneToOneField(SearchWorkspace, on_delete=models.CASCADE, related_name="agreement")
    choice = models.ForeignKey(RoomChoiceProposal, null=True, blank=True, on_delete=models.SET_NULL)
    clauses = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    member_version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)


class ClauseResponse(models.Model):
    agreement = models.ForeignKey(Agreement, on_delete=models.CASCADE, related_name="responses")
    member = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    key = models.CharField(max_length=30)
    accepted = models.BooleanField(default=False)
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["agreement", "member", "version", "key"], name="journey_unique_clause_response")]


class AgreementConsent(models.Model):
    agreement = models.ForeignKey(Agreement, on_delete=models.CASCADE, related_name="consents")
    member = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["agreement", "member", "version"], name="journey_unique_agreement_consent")]


class MoveInTask(models.Model):
    workspace = models.ForeignKey(SearchWorkspace, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=250)
    assignee = models.ForeignKey("core.Profile", null=True, blank=True, on_delete=models.SET_NULL)
    due_at = models.DateField(null=True, blank=True)
    done = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)


class JourneyCheckpoint(models.Model):
    profile = models.OneToOneField("core.Profile", on_delete=models.CASCADE, related_name="checkpoint")
    workspace = models.ForeignKey(SearchWorkspace, null=True, blank=True, on_delete=models.SET_NULL)
    path = models.CharField(max_length=250)
    updated_at = models.DateTimeField(auto_now=True)


class MutationReceipt(models.Model):
    actor = models.ForeignKey("core.Profile", on_delete=models.CASCADE)
    action = models.CharField(max_length=100)
    key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    response = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["actor", "action", "key"], name="journey_unique_mutation")]


class OutboxEvent(models.Model):
    recipients = models.JSONField(default=list)
    workspace = models.ForeignKey(SearchWorkspace, null=True, blank=True, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    path = models.CharField(max_length=250)
    delivered = models.BooleanField(default=False)
    delivery_attempts = models.PositiveIntegerField(default=0)
    retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OutboxRecipient(models.Model):
    event = models.ForeignKey(OutboxEvent, on_delete=models.CASCADE, related_name="recipient_links")
    profile = models.ForeignKey("core.Profile", on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "profile"], name="journey_unique_outbox_recipient")]


class Notification(models.Model):
    event = models.ForeignKey(OutboxEvent, on_delete=models.CASCADE)
    profile = models.ForeignKey("core.Profile", on_delete=models.CASCADE, related_name="notifications")
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "profile"], name="journey_unique_notification")]
