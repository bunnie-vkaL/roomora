import hashlib
import json
import logging
import uuid

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from core.models import ConnectionRequest, Profile
from core.scoring import score_profiles
from . import models as m
from .costs import calculate_shared_costs

logger = logging.getLogger(__name__)
CLAUSES = {"money": "Tiền và cách thanh toán", "cleaning": "Vệ sinh và việc nhà",
           "guests": "Khách đến chơi", "quiet": "Giờ yên tĩnh", "privacy": "Riêng tư và đồ dùng"}


class DomainError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status
        super().__init__(message)


def assert_version(obj, expected):
    try:
        valid = obj.version == int(expected)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise DomainError("Nội dung đã thay đổi. Tải lại để xem bản mới trước khi xác nhận.", 409)


def pair_query(a, b):
    return Q(low_id=min(a.pk, b.pk), high_id=max(a.pk, b.pk))


def is_blocked(a, b):
    query = Q(actor=a, target=b) | Q(actor=b, target=a)
    legacy = Q(sender=a, recipient=b) | Q(sender=b, recipient=a)
    return m.UserBlock.objects.filter(query).exists() or ConnectionRequest.objects.filter(legacy, status="blocked").exists()


def eligible_target(actor, target):
    from core.views import overlap
    if (actor.pk == target.pk or not actor.is_published or not target.is_published
            or not actor.completed or not target.completed or is_blocked(actor, target) or not overlap(actor, target)):
        raise DomainError("Hồ sơ không còn khả dụng để kết nối.", 403)
    from django.conf import settings
    if (actor.is_synthetic or target.is_synthetic) and not settings.DEBUG:
        raise DomainError("Hồ sơ mẫu chỉ dùng trong môi trường thử nghiệm.", 403)
    result = score_profiles(actor, target)
    if result.excluded or result.score is None:
        raise DomainError("Hồ sơ không đáp ứng điều kiện phù hợp.", 403)
    return result


def connection_for(actor, connection_id, lock=False):
    query = m.Connection.objects.select_related("low", "high")
    if lock:
        query = query.select_for_update()
    connection = query.filter(pk=connection_id, active=True).first()
    if not connection or actor.pk not in (connection.low_id, connection.high_id) or is_blocked(connection.low, connection.high):
        raise DomainError("Kết nối không còn khả dụng.", 403)
    return connection


def conversation_for(actor, conversation_id, lock=False):
    conversation = m.Conversation.objects.select_related("connection__low", "connection__high").filter(pk=conversation_id).first()
    if not conversation:
        raise DomainError("Cuộc trò chuyện không khả dụng.", 404)
    connection = connection_for(actor, conversation.connection_id, lock)
    if connection.generation != conversation.generation:
        raise DomainError("Cuộc trò chuyện đã kết thúc.", 403)
    return conversation


def workspace_for(actor, workspace_id, lock=False):
    query = m.SearchWorkspace.objects.select_related("conversation__connection", "inviter", "invitee")
    workspace = query.filter(pk=workspace_id, status="active").first()
    if not workspace or not workspace.members.filter(profile=actor, active=True).exists():
        raise DomainError("Bạn không còn quyền vào không gian này.", 403)
    conversation_for(actor, workspace.conversation_id, lock)
    if lock:
        workspace = m.SearchWorkspace.objects.select_for_update().get(pk=workspace_id)
        if workspace.status != "active" or not workspace.members.filter(profile=actor, active=True).exists():
            raise DomainError("Bạn không còn quyền vào không gian này.", 403)
    return workspace


def room_for(actor, room_id, lock=False):
    query = m.RoomOption.objects.select_related("workspace", "owner")
    room = query.filter(pk=room_id).first()
    if not room:
        raise DomainError("Không tìm thấy căn đã lưu.", 404)
    if room.workspace_id:
        workspace_for(actor, room.workspace_id, lock)
    elif room.owner_id != actor.pk:
        raise DomainError("Căn này đang được lưu riêng.", 403)
    if lock:
        room = m.RoomOption.objects.select_for_update().select_related("workspace", "owner").get(pk=room_id)
    return room


def member_ids(workspace):
    return list(workspace.members.filter(active=True).order_by("profile_id").values_list("profile_id", flat=True))


def members_for_cost(room):
    profiles = Profile.objects.filter(pk__in=member_ids(room.workspace)) if room.workspace_id else Profile.objects.filter(pk=room.owner_id)
    output = []
    for profile in profiles.order_by("pk"):
        living = getattr(profile, "living", None)
        output.append({"id": profile.pk, "monthly_budget": living.total_monthly_budget if living else None,
                       "upfront_budget": living.upfront_budget if living else None})
    return output


def emit(recipients, title, path, workspace=None):
    event = m.OutboxEvent.objects.create(recipients=sorted(set(recipients)), title=title, path=path, workspace=workspace)
    transaction.on_commit(lambda: deliver_safely(event.pk))
    return event


def deliver_safely(event_id):
    try:
        deliver_event(event_id)
    except Exception:
        logger.exception("Notification event %s retained for retry", event_id)


@transaction.atomic
def deliver_event(event_id):
    event = m.OutboxEvent.objects.select_for_update().get(pk=event_id)
    if event.delivered:
        return
    for profile in Profile.objects.filter(pk__in=event.recipients):
        living = getattr(profile, "living", None)
        if living and not living.notifications_enabled:
            continue
        if event.workspace_id:
            try:
                workspace_for(profile, event.workspace_id)
            except DomainError:
                continue
        m.Notification.objects.get_or_create(event=event, profile=profile)
    event.delivered = True
    event.save(update_fields=["delivered"])


@transaction.atomic
def run_mutation(actor, action, key, payload, operation):
    try:
        key = uuid.UUID(str(key))
    except (ValueError, TypeError, AttributeError):
        raise DomainError("Thiếu mã thao tác. Tải lại trang và thử lại.")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    # Serialize this actor's mutations and prevent duplicate side effects on retries.
    Profile.objects.select_for_update().get(pk=actor.pk)
    receipt = m.MutationReceipt.objects.filter(actor=actor, action=action, key=key).first()
    if receipt:
        if receipt.payload_hash != digest:
            raise DomainError("Mã thao tác đã dùng cho nội dung khác.", 409)
        return receipt.response
    response = operation()
    m.MutationReceipt.objects.create(actor=actor, action=action, key=key, payload_hash=digest, response=response)
    return response


@transaction.atomic
def decide(actor, target, choice):
    eligible_target(actor, target)
    if choice not in ("like", "pass"):
        raise DomainError("Thao tác quẹt không hợp lệ.")
    connection, _ = m.Connection.objects.get_or_create(low_id=min(actor.pk, target.pk), high_id=max(actor.pk, target.pk))
    connection = m.Connection.objects.select_for_update().get(pk=connection.pk)
    if is_blocked(actor, target):
        raise DomainError("Hồ sơ không còn khả dụng để kết nối.", 403)
    if connection.active:
        raise DomainError("Hai bạn đã kết nối. Dùng hủy kết nối nếu muốn kết thúc.", 409)
    old = m.SwipeDecision.objects.filter(actor=actor, target=target).first()
    if not old or old.choice != choice:
        m.DecisionEvent.objects.create(actor=actor, target=target, choice=choice, previous_choice=old.choice if old else "")
        m.SwipeDecision.objects.update_or_create(actor=actor, target=target, defaults={"choice": choice})
    if choice == "like" and m.SwipeDecision.objects.filter(actor=target, target=actor, choice="like").exists():
        connection.active = True
        connection.generation += 1
        connection.save()
        conversation = m.Conversation.objects.create(connection=connection, generation=connection.generation)
        emit([actor.pk, target.pk], "Hai bạn đã cùng muốn kết nối", reverse("journey:chat", args=[conversation.pk]))
        return conversation
    return None


@transaction.atomic
def undo_last(actor):
    Profile.objects.select_for_update().get(pk=actor.pk)
    event = m.DecisionEvent.objects.filter(actor=actor, undone=False).order_by("-pk").first()
    if not event:
        raise DomainError("Chưa có lượt quẹt để hoàn tác.", 409)
    connection = m.Connection.objects.select_for_update().filter(pair_query(actor, event.target)).first()
    if connection and connection.active:
        raise DomainError("Lượt này đã tạo kết nối. Hãy dùng hủy kết nối thay vì hoàn tác.", 409)
    if is_blocked(actor, event.target):
        raise DomainError("Không thể hoàn tác hồ sơ đã chặn.", 403)
    if event.previous_choice:
        m.SwipeDecision.objects.update_or_create(actor=actor, target=event.target, defaults={"choice": event.previous_choice})
    else:
        m.SwipeDecision.objects.filter(actor=actor, target=event.target).delete()
    event.undone = True
    event.save(update_fields=["undone"])


@transaction.atomic
def disconnect(actor, connection_id, block=False):
    connection = connection_for(actor, connection_id, lock=True)
    other = connection.other(actor)
    connection.active = False
    connection.save()
    if block:
        m.UserBlock.objects.get_or_create(actor=actor, target=other)
    m.SwipeDecision.objects.filter(Q(actor=actor, target=other) | Q(actor=other, target=actor)).delete()
    m.SearchWorkspace.objects.filter(conversation__connection=connection, status__in=["pending", "active"]).update(status="closed", moving_in=False)
    m.WorkspaceMember.objects.filter(workspace__conversation__connection=connection).update(active=False)
    ConnectionRequest.objects.filter(Q(sender=actor, recipient=other) | Q(sender=other, recipient=actor)).update(status="blocked" if block else "withdrawn")


@transaction.atomic
def block_profile(actor, target):
    if actor.pk == target.pk:
        raise DomainError("Không thể chặn chính mình.")
    connection, _ = m.Connection.objects.get_or_create(low_id=min(actor.pk, target.pk), high_id=max(actor.pk, target.pk))
    connection = m.Connection.objects.select_for_update().get(pk=connection.pk)
    if connection.active:
        disconnect(actor, connection.pk, block=True)
    else:
        m.UserBlock.objects.get_or_create(actor=actor, target=target)
        ConnectionRequest.objects.filter(Q(sender=actor, recipient=target) | Q(sender=target, recipient=actor)).update(status="blocked")


@transaction.atomic
def send_message(actor, conversation_id, body, client_id):
    conversation = conversation_for(actor, conversation_id, lock=True)
    body = body.strip()
    if not body or len(body) > 4000:
        raise DomainError("Tin nhắn cần có nội dung, tối đa 4.000 ký tự.")
    try:
        client_id = uuid.UUID(str(client_id))
    except (ValueError, TypeError):
        raise DomainError("Mã tin nhắn không hợp lệ.")
    message, created = m.Message.objects.get_or_create(conversation=conversation, sender=actor, client_id=client_id, defaults={"body": body})
    if not created and message.body != body:
        raise DomainError("Mã tin nhắn đã dùng cho nội dung khác.", 409)
    if created:
        emit([conversation.connection.other(actor).pk], "Có tin nhắn mới trong kết nối của bạn", reverse("journey:chat", args=[conversation.pk]))
    return message


@transaction.atomic
def invite_workspace(actor, conversation_id, title):
    conversation = conversation_for(actor, conversation_id, lock=True)
    existing = conversation.workspaces.filter(status__in=["pending", "active"]).first()
    if existing:
        return existing
    other = conversation.connection.other(actor)
    workspace = m.SearchWorkspace.objects.create(conversation=conversation, inviter=actor, invitee=other,
                                                 title=title.strip()[:120] or "Cùng tìm nơi muốn về")
    emit([other.pk], "Bạn có lời mời cùng tìm nhà", reverse("journey:hub"))
    return workspace


@transaction.atomic
def respond_workspace(actor, workspace_id, accept):
    workspace = m.SearchWorkspace.objects.filter(pk=workspace_id, status="pending", invitee=actor).first()
    if not workspace:
        raise DomainError("Lời mời đã thay đổi hoặc không dành cho bạn.", 409)
    conversation_for(actor, workspace.conversation_id, lock=True)
    workspace = m.SearchWorkspace.objects.select_for_update().get(pk=workspace.pk)
    if workspace.status != "pending" or workspace.invitee_id != actor.pk:
        raise DomainError("Lời mời đã thay đổi hoặc không dành cho bạn.", 409)
    workspace.status = "active" if accept else "declined"
    workspace.save()
    if accept:
        for profile_id in [workspace.inviter_id, workspace.invitee_id]:
            m.WorkspaceMember.objects.create(workspace=workspace, profile_id=profile_id)
        emit([workspace.inviter_id], "Lời mời cùng tìm nhà đã được đồng ý", reverse("journey:workspace", args=[workspace.pk]), workspace)
    return workspace


@transaction.atomic
def leave_workspace(actor, workspace_id):
    workspace = workspace_for(actor, workspace_id, lock=True)
    workspace.member_version += 1
    workspace.status, workspace.moving_in = "closed", False
    workspace.save()
    workspace.members.update(active=False)


@transaction.atomic
def share_room(actor, room_id, workspace_id):
    source = room_for(actor, room_id, lock=True)
    workspace = workspace_for(actor, workspace_id, lock=True)
    if source.workspace_id or source.owner_id != actor.pk:
        raise DomainError("Chỉ chia sẻ căn đang lưu riêng của bạn.", 403)
    existing = workspace.rooms.filter(source_room=source).first()
    if existing:
        return existing
    copy = m.RoomOption.objects.create(owner=actor, workspace=workspace, source_room=source,
                                      title=source.title, url=source.url, area=source.area, address=source.address, notes=source.notes)
    for cost in source.costs.all():
        m.RoomCost.objects.create(room=copy, label=cost.label, period=cost.period, state=cost.state, amount=cost.amount, source=cost.source)
    for image in source.images.all():
        m.RoomImage.objects.create(room=copy, image=image.image.name, caption=image.caption, creator=actor)
    ensure_checklist(copy)
    emit(member_ids(workspace), "Có một căn mới trên bảng nhà chung", reverse("journey:room", args=[copy.pk]), workspace)
    return copy


def ensure_checklist(room):
    titles = ["Kiểm tra hợp đồng và người cho thuê", "Kiểm tra ánh sáng, tiếng ồn và an toàn", "Kiểm tra điện, nước, mạng và đồ dùng"]
    titles += [f"Xác minh {cost.label}" for cost in room.costs.filter(state__in=["unknown", "estimated"])]
    for title in titles:
        room.checklist.get_or_create(title=title[:250])


@transaction.atomic
def save_scenario(actor, room_id, expected, weights):
    room = room_for(actor, room_id, lock=True)
    assert_version(room, expected)
    try:
        calculation = calculate_shared_costs(list(room.costs.values("label", "period", "state", "amount", "source")), members_for_cost(room), weights)
    except ValueError as exc:
        raise DomainError(str(exc))
    room.version += 1
    room.save(update_fields=["version"])
    scenario = m.CostScenario.objects.create(room=room, creator=actor, room_version=room.version, weights=calculation["weights"], calculation=calculation)
    if room.workspace_id:
        room.workspace.moving_in = False
        room.workspace.save(update_fields=["moving_in"])
        emit(member_ids(room.workspace), "Cách chia chi phí đã thay đổi; hãy xem lại xác nhận", reverse("journey:room", args=[room.pk]), room.workspace)
    return scenario


def proposal_current(proposal):
    latest = proposal.workspace.proposals.order_by("-pk").first()
    return bool(latest and latest.pk == proposal.pk and proposal.workspace.status == "active"
                and proposal.room.version == proposal.room_version
                and proposal.scenario.room_version == proposal.room_version
                and proposal.workspace.member_version == proposal.member_version)


def proposal_confirmed(proposal):
    ids = set(member_ids(proposal.workspace))
    return proposal_current(proposal) and len(ids) >= 2 and ids == set(proposal.consents.values_list("member_id", flat=True))


@transaction.atomic
def propose_room(actor, room_id, expected):
    room = room_for(actor, room_id, lock=True)
    assert_version(room, expected)
    if not room.workspace_id:
        raise DomainError("Hãy chia sẻ căn vào không gian chung trước.")
    workspace = workspace_for(actor, room.workspace_id, lock=True)
    scenario = room.scenarios.filter(room_version=room.version).order_by("-pk").first()
    if not scenario or not scenario.calculation["complete"] or scenario.calculation["estimated"]:
        raise DomainError("Cần xác minh đủ chi phí và lưu cách chia hiện tại trước khi đề xuất chọn căn.")
    if any(not cost.source.strip() for cost in room.costs.all()):
        raise DomainError("Ghi nguồn xác minh cho từng khoản tiền trước khi đề xuất chọn căn.")
    proposal = m.RoomChoiceProposal.objects.create(workspace=workspace, room=room, scenario=scenario, proposer=actor,
                                                  room_version=room.version, member_version=workspace.member_version)
    workspace.moving_in = False
    workspace.save(update_fields=["moving_in"])
    emit(member_ids(workspace), "Có đề xuất chọn căn mới, cần xác nhận của từng người", reverse("journey:workspace", args=[workspace.pk]), workspace)
    return proposal


@transaction.atomic
def consent_choice(actor, proposal_id, expected_room_version):
    proposal = m.RoomChoiceProposal.objects.select_related("workspace", "room", "scenario").get(pk=proposal_id)
    workspace = workspace_for(actor, proposal.workspace_id, lock=True)
    room = room_for(actor, proposal.room_id, lock=True)
    assert_version(room, expected_room_version)
    proposal.room, proposal.workspace = room, workspace
    if not proposal_current(proposal):
        raise DomainError("Đề xuất đã thay đổi. Hãy xem và xác nhận đề xuất hiện tại.", 409)
    m.ChoiceConsent.objects.get_or_create(proposal=proposal, member=actor)
    emit(member_ids(proposal.workspace), "Một thành viên đã xác nhận đề xuất chọn căn", reverse("journey:workspace", args=[proposal.workspace_id]), proposal.workspace)


def agreement_confirmed(agreement):
    ids = set(member_ids(agreement.workspace))
    return bool(agreement.choice_id and agreement.member_version == agreement.workspace.member_version
                and proposal_confirmed(agreement.choice)
                and ids == set(agreement.consents.filter(version=agreement.version).values_list("member_id", flat=True)))


@transaction.atomic
def save_agreement(actor, workspace_id, clauses, expected):
    workspace = workspace_for(actor, workspace_id, lock=True)
    if set(clauses) != set(CLAUSES) or any(not isinstance(value, str) or len(value) > 2000 for value in clauses.values()):
        raise DomainError("Nội dung bản thống nhất không hợp lệ.")
    agreement = m.Agreement.objects.filter(workspace=workspace).first()
    if agreement:
        assert_version(agreement, expected)
        agreement.version += 1
    elif str(expected) != "0":
        raise DomainError("Bản thống nhất đã thay đổi.", 409)
    else:
        agreement = m.Agreement(workspace=workspace)
    agreement.clauses = clauses
    agreement.choice = workspace.proposals.order_by("-pk").first()
    agreement.member_version = workspace.member_version
    agreement.save()
    workspace.moving_in = False
    workspace.save(update_fields=["moving_in"])
    emit(member_ids(workspace), "Bản thống nhất có phiên bản mới, cần xác nhận lại", reverse("journey:agreement", args=[workspace.pk]), workspace)
    return agreement


@transaction.atomic
def consent_agreement(actor, workspace_id, expected):
    workspace = workspace_for(actor, workspace_id, lock=True)
    agreement = m.Agreement.objects.select_related("choice__room", "choice__scenario", "choice__workspace").filter(workspace=workspace).first()
    if not agreement:
        raise DomainError("Chưa có bản thống nhất.")
    assert_version(agreement, expected)
    if not agreement.choice_id or not proposal_confirmed(agreement.choice) or agreement.member_version != workspace.member_version:
        raise DomainError("Cần tất cả thành viên xác nhận đề xuất chọn căn hiện tại trước.", 409)
    if any(not agreement.clauses.get(key, "").strip() for key in CLAUSES):
        raise DomainError("Hãy hoàn thiện tất cả điều khoản trước khi xác nhận.")
    responses = agreement.responses.filter(member=actor, version=agreement.version, accepted=True).values_list("key", flat=True)
    if set(responses) != set(CLAUSES):
        raise DomainError("Hãy đồng ý từng điều khoản hoặc đánh dấu điều cần trao đổi trước.")
    m.AgreementConsent.objects.get_or_create(agreement=agreement, member=actor, version=agreement.version)
    emit(member_ids(workspace), "Một thành viên đã xác nhận bản thống nhất", reverse("journey:agreement", args=[workspace.pk]), workspace)


def checkpoint(actor, path, workspace=None):
    m.JourneyCheckpoint.objects.update_or_create(profile=actor, defaults={"path": path, "workspace": workspace})
