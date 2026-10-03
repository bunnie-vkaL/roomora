import hashlib
import json
import mimetypes
import uuid
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import LifestyleAnswers, Profile
from core.scoring import score_profiles
from . import forms as f, models as m, services as s
from .costs import calculate_shared_costs


def page(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not settings.ROOMORA_JOURNEY_ENABLED:
            raise Http404
        request.actor, _ = Profile.objects.get_or_create(user=request.user, defaults={"name": "", "age": 18, "areas": [], "rent_min": 0, "rent_max": 0, "contact_type": "zalo", "contact_value": ""})
        try:
            if request.actor.is_synthetic and not settings.DEBUG:
                raise s.DomainError("Tài khoản mẫu chỉ dùng trong môi trường thử nghiệm.", 403)
            return view(request, *args, **kwargs)
        except s.DomainError as exc:
            if request.headers.get("Accept") == "application/json":
                return JsonResponse({"error": exc.message}, status=exc.status)
            return render(request, "journey/error.html", {"error": exc.message}, status=exc.status)
    return wrapped


def number(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        if default is not None:
            return default
        raise s.DomainError("Mã hoặc số nhập vào không hợp lệ.")


def image_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise s.DomainError("Mã ảnh không hợp lệ.")


def text(data, key, limit, required=False):
    value = data.get(key, "").strip()
    if len(value) > limit or (required and not value):
        raise s.DomainError(f"Nội dung cần có độ dài từ {1 if required else 0} đến {limit} ký tự.")
    return value


def yes_no(data, key):
    value = data.get(key)
    if value not in ("1", "0"):
        raise s.DomainError("Hãy chọn đồng ý hoặc không đồng ý.")
    return value == "1"


def profile_by_id(value):
    profile = Profile.objects.filter(pk=number(value)).first()
    if not profile:
        raise s.DomainError("Hồ sơ không tồn tại.", 404)
    return profile


def clean_form(form):
    if not form.is_valid():
        raise s.DomainError(form.errors.as_text())
    return form.cleaned_data


def candidate_card(actor, profile, result=None, context=None):
    result = result or s.eligible_target(actor, profile)
    living = getattr(profile, "living", None)
    context_reason = ""
    if context:
        context_reason = f"Cùng cân nhắc {context.title}; cần trao đổi thêm về căn và phần tiền mỗi người."
    return {"profile": profile, "score": result.score, "score_version": result.version,
            "similarities": result.similarities, "differences": result.differences, "warnings": result.warnings,
            "living": living, "context_reason": context_reason,
            "saved": m.SavedCandidate.objects.filter(owner=actor, candidate=profile).exists()}


def candidate_rows(actor, area="", rent=None, context=None, include_decided=False):
    if not actor.is_published or not actor.completed:
        return []
    candidates = Profile.objects.filter(is_published=True).exclude(pk=actor.pk).select_related("answers", "living")
    if not settings.DEBUG:
        candidates = candidates.filter(is_synthetic=False)
    if not include_decided:
        candidates = candidates.exclude(pk__in=actor.swipes.values("target_id"))
    rows = []
    for profile in candidates:
        if area and area not in profile.areas:
            continue
        if rent is not None and not profile.rent_min <= rent <= profile.rent_max:
            continue
        if not include_decided and m.Connection.objects.filter(s.pair_query(actor, profile), active=True).exists():
            continue
        try:
            result = s.eligible_target(actor, profile)
        except s.DomainError:
            continue
        rows.append(candidate_card(actor, profile, result, context))
    return sorted(rows, key=lambda row: (-row["score"], row["profile"].pk))


@page
def discover(request):
    actor = request.actor
    context = s.room_for(actor, number(request.GET["room"])) if request.GET.get("room") else None
    area = request.GET.get("area", "")
    rent = number(request.GET.get("rent")) if request.GET.get("rent") else None
    rows = candidate_rows(actor, area, rent, context)
    fingerprint = hashlib.sha256(json.dumps([(row["profile"].pk, row["score"], str(row["profile"].updated_at), row["living"].version if row["living"] else 0) for row in rows]).encode()).hexdigest()
    start = 0
    if request.GET.get("cursor"):
        try:
            cursor = signing.loads(request.GET["cursor"], salt="journey-deck", max_age=3600)
            if cursor["actor"] != actor.pk or cursor["fingerprint"] != fingerprint or cursor["filters"] != [area, rent, context.pk if context else None]:
                raise signing.BadSignature
            start = cursor["start"]
            if type(start) is not int or not 0 <= start <= len(rows):
                raise signing.BadSignature
        except (signing.BadSignature, KeyError, TypeError):
            raise s.DomainError("Danh sách đã thay đổi. Mở lại Tìm bạn để xem hồ sơ mới nhất.", 409)
    next_cursor = signing.dumps({"actor": actor.pk, "fingerprint": fingerprint, "filters": [area, rent, context.pk if context else None], "start": start + 10}, salt="journey-deck") if start + 10 < len(rows) else ""
    s.checkpoint(actor, reverse("journey:discover"))
    from core.constants import AREAS
    return render(request, "journey/discover.html", {"cards": rows[start:start + 10], "next_cursor": next_cursor,
                  "actor": actor, "areas": AREAS, "selected_area": area, "rent": rent or "", "room_context": context})


@page
def candidate(request, profile_id):
    profile = profile_by_id(profile_id)
    card = candidate_card(request.actor, profile)
    note = m.PrivateNote.objects.filter(owner=request.actor, candidate=profile).first()
    s.checkpoint(request.actor, request.path)
    return render(request, "journey/candidate.html", {"card": card, "actor": request.actor, "note": note})


@page
def saved(request):
    cards = []
    for row in request.actor.saved_candidates.select_related("candidate__answers", "candidate__living"):
        try:
            cards.append(candidate_card(request.actor, row.candidate))
        except s.DomainError:
            continue
    return render(request, "journey/saved.html", {"cards": cards})


@page
def compare_candidates(request):
    ids = request.GET.getlist("candidate")
    if not 2 <= len(ids) <= 3 or len(set(ids)) != len(ids):
        raise s.DomainError("Chọn hai hoặc ba người đã lưu để so sánh.")
    cards = []
    for profile_id in ids:
        profile = profile_by_id(profile_id)
        if not m.SavedCandidate.objects.filter(owner=request.actor, candidate=profile).exists():
            raise s.DomainError("Chỉ so sánh người bạn đã lưu.", 403)
        cards.append(candidate_card(request.actor, profile))
    return render(request, "journey/compare.html", {"cards": cards, "actor": request.actor})


@page
def preferences(request):
    living = m.LivingPreferences.objects.filter(profile=request.actor).first()
    s.checkpoint(request.actor, request.path)
    return render(request, "journey/preferences.html", {"form": f.PreferencesForm(instance=living), "version": living.version if living else 0})


@page
def hub(request):
    actor = request.actor
    conversations = []
    for connection in m.Connection.objects.filter(Q(low=actor) | Q(high=actor), active=True).select_related("low", "high"):
        if s.is_blocked(connection.low, connection.high):
            continue
        conversation = connection.conversations.filter(generation=connection.generation).first()
        if conversation:
            conversations.append({"conversation": conversation, "other": connection.other(actor)})
    incoming = []
    for swipe in m.SwipeDecision.objects.filter(target=actor, choice="like").select_related("actor__answers", "actor__living"):
        try:
            if not m.Connection.objects.filter(s.pair_query(actor, swipe.actor), active=True).exists():
                incoming.append(candidate_card(actor, swipe.actor))
        except s.DomainError:
            continue
    invites = []
    for workspace in m.SearchWorkspace.objects.filter(invitee=actor, status="pending").select_related("inviter"):
        try:
            s.conversation_for(actor, workspace.conversation_id)
            invites.append(workspace)
        except s.DomainError:
            continue
    workspaces = []
    for membership in actor.workspaces.filter(active=True).select_related("workspace"):
        try:
            workspaces.append(s.workspace_for(actor, membership.workspace_id))
        except s.DomainError:
            continue
    return render(request, "journey/hub.html", {"conversations": conversations, "incoming": incoming, "invites": invites, "workspaces": workspaces})


@page
def chat(request, conversation_id):
    conversation = s.conversation_for(request.actor, conversation_id)
    s.checkpoint(request.actor, request.path)
    other = conversation.connection.other(request.actor)
    result = score_profiles(request.actor, other)
    opener = f"Chào {other.name}, mình muốn trao đổi thêm về {result.similarities[0].lower()} và kế hoạch tìm nhà. Bạn thấy thế nào?" if result.similarities else f"Chào {other.name}, mình muốn tìm hiểu nhu cầu ở ghép của bạn. Mình cùng trao đổi nhé?"
    facts = []
    for fact in conversation.facts.select_related("source", "author").order_by("-pk"):
        consent_ids = set(fact.consents.filter(version=fact.version).values_list("member_id", flat=True))
        facts.append({"fact": fact, "confirmed": consent_ids == {conversation.connection.low_id, conversation.connection.high_id}, "mine": request.actor.pk in consent_ids})
    query = conversation.messages.select_related("sender")
    if request.GET.get("message"):
        source_id = number(request.GET["message"])
        if not query.filter(pk=source_id).exists():
            raise s.DomainError("Tin nguồn không thuộc cuộc trò chuyện này.", 404)
        messages_list = list(query.filter(pk__lte=source_id).order_by("-pk")[:25])[::-1] + list(query.filter(pk__gt=source_id).order_by("pk")[:25])
    else:
        messages_list = list(query.order_by("-pk")[:50])[::-1]
    older_cursor = messages_list[0].pk if messages_list and query.filter(pk__lt=messages_list[0].pk).exists() else None
    return render(request, "journey/chat.html", {"conversation": conversation, "other": other, "actor": request.actor,
                  "messages_list": messages_list,
                  "facts": facts, "opener": opener, "client_id": uuid.uuid4(),
                  "shared_workspace": conversation.workspaces.filter(status__in=["pending", "active"]).first(),
                  "older_cursor": older_cursor})


@page
def messages(request, conversation_id):
    conversation = s.conversation_for(request.actor, conversation_id)
    query = conversation.messages.select_related("sender")
    before = number(request.GET["before"]) if request.GET.get("before") else None
    after = number(request.GET.get("after"), 0)
    if before:
        rows = list(query.filter(pk__lt=before).order_by("-pk")[:50])[::-1]
    else:
        rows = list(query.filter(pk__gt=after).order_by("pk")[:50])
    return JsonResponse({"messages": [{"id": row.pk, "sender": row.sender.name, "mine": row.sender_id == request.actor.pk, "body": row.body, "created_at": row.created_at.isoformat()} for row in rows], "next_before": rows[0].pk if len(rows) == 50 else None})


def choice_context(workspace):
    proposal = workspace.proposals.select_related("room", "scenario", "workspace").order_by("-pk").first()
    calculation = None
    if proposal:
        calculation = proposal.scenario.calculation
        profiles = {profile.pk: profile for profile in Profile.objects.filter(pk__in=[row["id"] for row in calculation["members"]])}
        for row in calculation["members"]:
            row["profile"] = profiles.get(row["id"])
    return {"proposal": proposal, "proposal_current": s.proposal_current(proposal) if proposal else False,
            "proposal_confirmed": s.proposal_confirmed(proposal) if proposal else False,
            "proposal_calculation": calculation,
            "choice_consents": set(proposal.consents.values_list("member_id", flat=True)) if proposal else set()}


@page
def workspace(request, workspace_id):
    workspace = s.workspace_for(request.actor, workspace_id)
    s.checkpoint(request.actor, request.path, workspace)
    context = choice_context(workspace)
    agreement = m.Agreement.objects.filter(workspace=workspace).select_related("choice__room", "choice__scenario", "choice__workspace").first()
    board_rooms = list(workspace.rooms.prefetch_related("opinions__member", "images"))
    for option in board_rooms:
        option.member_opinions = opinions_for_room(option)
    context.update({"workspace": workspace, "actor": request.actor, "rooms": board_rooms,
                    "members": workspace.members.filter(active=True).select_related("profile"), "agreement_confirmed": s.agreement_confirmed(agreement) if agreement else False,
                    "tasks": [{"task": task, "form": f.TaskForm(instance=task, workspace=workspace, auto_id=f"id_task_{task.pk}_%s")} for task in workspace.tasks.select_related("assignee")],
                    "task_form": f.TaskForm(workspace=workspace),
                    "private_rooms": request.actor.room_options.filter(workspace__isnull=True)})
    return render(request, "journey/workspace.html", context)


@page
def rooms(request):
    return render(request, "journey/rooms.html", {"rooms": request.actor.room_options.filter(workspace__isnull=True).prefetch_related("images", "costs")})


@page
def edit_room(request, room_id=None):
    room = s.room_for(request.actor, room_id) if room_id else None
    workspace = room.workspace if room else s.workspace_for(request.actor, number(request.GET["workspace"])) if request.GET.get("workspace") else None
    initial_costs = [{"label": "Tiền thuê", "period": "monthly", "state": "unknown"},
                     {"label": "Tiền cọc", "period": "deposit", "state": "unknown"},
                     {"label": "Khoản một lần đầu kỳ", "period": "initial", "state": "unknown"}]
    return render(request, "journey/room_edit.html", {"form": f.RoomForm(instance=room), "costs": f.RoomCostFormSet(instance=room, prefix="costs", initial=initial_costs if room is None else None), "room": room, "workspace": workspace})


def room_calculation(room):
    scenario = room.scenarios.filter(room_version=room.version).order_by("-pk").first()
    costs = list(room.costs.values("label", "period", "state", "amount", "source"))
    calculation = calculate_shared_costs(costs, s.members_for_cost(room), scenario.weights if scenario else None)
    profiles = {profile.pk: profile for profile in Profile.objects.filter(pk__in=[row["id"] for row in calculation["members"]]).select_related("living")}
    for row in calculation["members"]:
        row["profile"] = profiles[row["id"]]
        row["living"] = getattr(profiles[row["id"]], "living", None)
        row["weight"] = scenario.weights.get(str(row["id"]), 1) if scenario else 1
    return calculation, scenario


def opinions_for_room(room):
    if not room.workspace_id:
        return []
    opinions = {opinion.member_id: opinion for opinion in room.opinions.all()}
    return [{"profile": profile, "opinion": opinions.get(profile.pk)}
            for profile in Profile.objects.filter(pk__in=s.member_ids(room.workspace)).order_by("pk")]


@page
def room(request, room_id):
    room = s.room_for(request.actor, room_id)
    s.checkpoint(request.actor, request.path, room.workspace)
    calculation, scenario = room_calculation(room)
    member_ids = set(s.member_ids(room.workspace)) if room.workspace_id else {request.actor.pk}
    viewings = []
    for plan in room.viewings.order_by("-at"):
        accepted = set(plan.responses.filter(version=plan.version, accepted=True).values_list("member_id", flat=True))
        viewings.append({"plan": plan, "confirmed": not plan.cancelled and accepted == member_ids, "accepted": accepted})
    return render(request, "journey/room.html", {"room": room, "actor": request.actor, "calculation": calculation, "scenario": scenario,
                  "member_opinions": opinions_for_room(room),
                  "opinion": room.opinions.filter(member=request.actor).first(), "images": room.images.prefetch_related("pins__author"),
                  "viewings": viewings, "viewing_form": f.ViewingForm(), "checklist": room.checklist.select_related("checked_by"),
                  "evidence": room.evidence.select_related("author", "image").order_by("-pk"), "private_workspaces": request.actor.workspaces.filter(active=True, workspace__status="active").select_related("workspace") if not room.workspace_id else []})


@page
def compare_rooms(request):
    ids = request.GET.getlist("room")
    if not 2 <= len(ids) <= 3 or len(set(ids)) != len(ids):
        raise s.DomainError("Chọn hai hoặc ba căn để so sánh.")
    options = []
    for room_id in ids:
        option = s.room_for(request.actor, number(room_id))
        calculation, _ = room_calculation(option)
        options.append({"room": option, "calculation": calculation, "member_opinions": opinions_for_room(option)})
    return render(request, "journey/room_compare.html", {"options": options})


@page
def image(request, image_id):
    image = m.RoomImage.objects.filter(pk=image_id).first()
    if not image:
        raise Http404
    s.room_for(request.actor, image.room_id)
    try:
        response = FileResponse(image.image.open("rb"), content_type=mimetypes.guess_type(image.image.name)[0] or "application/octet-stream")
    except FileNotFoundError:
        raise Http404
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@page
def agreement(request, workspace_id):
    workspace = s.workspace_for(request.actor, workspace_id)
    agreement = m.Agreement.objects.filter(workspace=workspace).select_related("choice__room", "choice__scenario", "choice__workspace").first()
    clauses = agreement.clauses if agreement else {"money": "", "cleaning": "Luân phiên dọn khu vực chung; cùng thống nhất lịch cụ thể.", "guests": "Trao đổi trước khi mời khách ở lại.", "quiet": "", "privacy": "Tôn trọng không gian riêng; hỏi trước khi dùng đồ của nhau."}
    if not agreement:
        proposal = workspace.proposals.select_related("room", "scenario").order_by("-pk").first()
        if proposal and s.proposal_confirmed(proposal):
            clauses["money"] = f"Căn: {proposal.room.title}. Các khoản và phần tiền theo cách chia đã xác nhận #{proposal.scenario_id}."
    responses = []
    if agreement:
        for key, label in s.CLAUSES.items():
            responses.append({"key": key, "label": label, "text": agreement.clauses.get(key, ""), "responses": agreement.responses.filter(version=agreement.version, key=key).select_related("member")})
    s.checkpoint(request.actor, request.path, workspace)
    return render(request, "journey/agreement.html", {"workspace": workspace, "agreement": agreement,
                  "form": f.AgreementForm(initial=clauses), "responses": responses,
                  "confirmed": s.agreement_confirmed(agreement) if agreement else False,
                  "consents": set(agreement.consents.filter(version=agreement.version).values_list("member_id", flat=True)) if agreement else set(),
                  "actor": request.actor})


@page
def notifications(request):
    for event_id in m.OutboxEvent.objects.filter(delivered=False).values_list("pk", flat=True)[:100]:
        s.deliver_safely(event_id)
    rows = []
    for notification in request.actor.notifications.select_related("event").order_by("-pk")[:100]:
        if notification.event.workspace_id:
            try:
                s.workspace_for(request.actor, notification.event.workspace_id)
            except s.DomainError:
                continue
        rows.append(notification)
    return render(request, "journey/notifications.html", {"notifications_list": rows})


@page
def resume(request):
    checkpoint = m.JourneyCheckpoint.objects.filter(profile=request.actor).first()
    if checkpoint:
        if checkpoint.workspace_id:
            try:
                s.workspace_for(request.actor, checkpoint.workspace_id)
            except s.DomainError:
                return redirect("journey:hub")
        # Checkpoints are written by our views; never trust a client supplied destination.
        if checkpoint.path.startswith("/together/") and "//" not in checkpoint.path and "\\" not in checkpoint.path:
            return redirect(checkpoint.path)
    return redirect("journey:hub")


def perform(request, action):
    actor, data = request.actor, request.POST
    expected = data.get("expected_version")
    destination = reverse("journey:hub")
    if action in ("like", "pass", "save-candidate", "note", "block", "report"):
        target = profile_by_id(data.get("target"))
        destination = reverse("journey:discover")
        if action in ("like", "pass"):
            conversation = s.decide(actor, target, action)
            if conversation:
                destination = reverse("journey:chat", args=[conversation.pk])
        elif action == "save-candidate":
            s.eligible_target(actor, target)
            if yes_no(data, "saved"):
                m.SavedCandidate.objects.get_or_create(owner=actor, candidate=target)
            else:
                m.SavedCandidate.objects.filter(owner=actor, candidate=target).delete()
            destination = reverse("journey:saved")
        elif action == "note":
            s.eligible_target(actor, target)
            note = m.PrivateNote.objects.filter(owner=actor, candidate=target).first()
            if note:
                s.assert_version(note, expected)
                note.version += 1
            elif str(expected) != "0":
                raise s.DomainError("Ghi chú đã thay đổi.", 409)
            else:
                note = m.PrivateNote(owner=actor, candidate=target)
            note.body = text(data, "body", 3000)
            note.save()
            destination = reverse("journey:candidate", args=[target.pk])
        elif action == "block":
            s.block_profile(actor, target)
        else:
            if target.pk == actor.pk:
                raise s.DomainError("Không thể báo cáo chính mình.")
            if m.Report.objects.filter(reporter=actor, created_at__date=timezone.localdate()).count() >= 20:
                raise s.DomainError("Bạn đã gửi nhiều báo cáo. Vui lòng thử lại vào ngày mai.", 429)
            m.Report.objects.create(reporter=actor, target=target, reason=text(data, "reason", 1000, True))
    elif action == "undo":
        s.undo_last(actor)
        destination = reverse("journey:discover")
    elif action == "disconnect":
        s.disconnect(actor, number(data.get("connection")))
    elif action == "preferences":
        living = m.LivingPreferences.objects.filter(profile=actor).first()
        if living:
            s.assert_version(living, expected)
        elif str(expected) != "0":
            raise s.DomainError("Nhu cầu đã thay đổi.", 409)
        form = f.PreferencesForm(data, instance=living)
        clean_form(form)
        living = form.save(commit=False)
        living.profile = actor
        if living.pk:
            living.version += 1
        living.save()
        destination = reverse("journey:preferences")
    elif action in ("message", "workspace-invite", "fact-pin", "fact-edit", "fact-consent"):
        conversation = s.conversation_for(actor, number(data.get("conversation")), lock=True)
        destination = reverse("journey:chat", args=[conversation.pk])
        if action == "message":
            s.send_message(actor, conversation.pk, text(data, "body", 4000, True), data.get("client_id"))
        elif action == "workspace-invite":
            workspace = s.invite_workspace(actor, conversation.pk, text(data, "title", 120))
            if workspace.status == "active":
                destination = reverse("journey:workspace", args=[workspace.pk])
        elif action == "fact-pin":
            source = conversation.messages.filter(pk=number(data.get("source"))).first()
            if not source:
                raise s.DomainError("Tin nguồn không thuộc cuộc trò chuyện này.", 403)
            m.PinnedFact.objects.create(conversation=conversation, source=source, author=actor, body=text(data, "body", 1000, True))
        else:
            fact = conversation.facts.filter(pk=number(data.get("fact"))).first()
            if not fact:
                raise s.DomainError("Thông tin ghim không khả dụng.", 404)
            s.assert_version(fact, expected)
            if action == "fact-edit":
                if fact.author_id != actor.pk:
                    raise s.DomainError("Chỉ tác giả được sửa thông tin ghim.", 403)
                fact.body = text(data, "body", 1000, True)
                fact.version += 1
                fact.save()
            else:
                m.FactConsent.objects.get_or_create(fact=fact, member=actor, version=fact.version)
    elif action == "workspace-response":
        workspace = s.respond_workspace(actor, number(data.get("workspace")), yes_no(data, "accepted"))
        if workspace.status == "active":
            destination = reverse("journey:workspace", args=[workspace.pk])
    elif action == "workspace-leave":
        s.leave_workspace(actor, number(data.get("workspace")))
    elif action == "room-save":
        room_id = number(data.get("room"), 0)
        room = s.room_for(actor, room_id, lock=True) if room_id else None
        if room:
            s.assert_version(room, expected)
        elif str(expected) != "0":
            raise s.DomainError("Căn đã thay đổi.", 409)
        workspace = room.workspace if room else s.workspace_for(actor, number(data["workspace"]), lock=True) if data.get("workspace") else None
        form = f.RoomForm(data, instance=room)
        costs = f.RoomCostFormSet(data, instance=form.instance, prefix="costs")
        clean_form(form)
        if not costs.is_valid():
            raise s.DomainError(str(costs.errors) + str(costs.non_form_errors()))
        room = form.save(commit=False)
        room.owner = room.owner if room.pk else actor
        room.workspace = workspace
        if room.pk:
            room.version += 1
        room.save()
        costs.instance = room
        costs.save()
        s.ensure_checklist(room)
        if workspace:
            workspace.moving_in = False
            workspace.save(update_fields=["moving_in"])
            s.emit(s.member_ids(workspace), "Thông tin căn đã thay đổi; hãy kiểm tra quyết định", reverse("journey:room", args=[room.pk]), workspace)
        destination = reverse("journey:room", args=[room.pk])
    elif action == "room-share":
        room = s.share_room(actor, number(data.get("room")), number(data.get("workspace")))
        destination = reverse("journey:room", args=[room.pk])
    elif action in ("opinion", "scenario", "image-upload", "image-pin", "viewing-save", "viewing-response", "viewing-cancel", "checklist-add", "checklist-update", "evidence", "room-propose"):
        room = s.room_for(actor, number(data.get("room")), lock=True)
        destination = reverse("journey:room", args=[room.pk])
        if action == "opinion":
            if not room.workspace_id:
                raise s.DomainError("Ý kiến riêng của mỗi thành viên dùng trên căn chung.")
            choice = data.get("choice")
            if choice not in ("interested", "unsure", "no"):
                raise s.DomainError("Ý kiến không hợp lệ.")
            opinion = room.opinions.filter(member=actor).first()
            if opinion:
                s.assert_version(opinion, expected)
                opinion.version += 1
            elif str(expected) != "0":
                raise s.DomainError("Ý kiến đã thay đổi.", 409)
            else:
                opinion = m.RoomOpinion(room=room, member=actor)
            opinion.choice, opinion.note = choice, text(data, "note", 500)
            opinion.save()
            s.emit(s.member_ids(room.workspace), "Một thành viên đã cập nhật ý kiến về căn", destination, room.workspace)
        elif action == "scenario":
            weights = {str(member["id"]): number(data.get(f"weight_{member['id']}")) for member in s.members_for_cost(room)}
            s.save_scenario(actor, room.pk, expected, weights)
        elif action == "image-upload":
            form = f.ImageUploadForm(data, request.FILES)
            clean_form(form)
            m.RoomImage.objects.create(room=room, image=form.cleaned_data["image"], caption=form.cleaned_data["caption"], creator=actor)
            if room.workspace_id:
                s.emit(s.member_ids(room.workspace), "Có ảnh mới để kiểm tra căn và điều cần hỏi", destination, room.workspace)
        elif action == "image-pin":
            image = room.images.filter(pk=image_uuid(data.get("image"))).first()
            if not image:
                raise s.DomainError("Ảnh không thuộc căn này.", 403)
            form = f.PinForm(data)
            clean_form(form)
            pin = form.save(commit=False)
            pin.image, pin.author = image, actor
            pin.save()
        elif action == "viewing-save":
            plan_id = number(data.get("plan"), 0)
            plan = room.viewings.filter(pk=plan_id).first() if plan_id else None
            if plan_id and not plan:
                raise s.DomainError("Lịch xem không thuộc căn này.", 403)
            if plan:
                s.assert_version(plan, expected)
                plan.version += 1
            form = f.ViewingForm(data, instance=plan)
            clean_form(form)
            if form.cleaned_data["at"] <= timezone.now():
                raise s.DomainError("Hãy đề xuất thời gian trong tương lai.")
            plan = form.save(commit=False)
            plan.room, plan.author = room, actor
            plan.cancelled = False
            plan.save()
            m.ViewingResponse.objects.create(plan=plan, member=actor, version=plan.version, accepted=True)
            if room.workspace_id:
                s.emit(s.member_ids(room.workspace), "Có thời gian đi xem nhà mới cần phản hồi", destination, room.workspace)
        elif action == "viewing-response":
            plan = room.viewings.filter(pk=number(data.get("plan"))).first()
            if not plan or plan.cancelled:
                raise s.DomainError("Lịch đi xem không khả dụng.", 404)
            s.assert_version(plan, expected)
            m.ViewingResponse.objects.update_or_create(plan=plan, member=actor, version=plan.version, defaults={"accepted": yes_no(data, "accepted")})
            if room.workspace_id:
                s.emit(s.member_ids(room.workspace), "Có phản hồi mới về thời gian đi xem nhà", destination, room.workspace)
        elif action == "viewing-cancel":
            plan = room.viewings.filter(pk=number(data.get("plan"))).first()
            if not plan:
                raise s.DomainError("Lịch xem không thuộc căn này.", 403)
            s.assert_version(plan, expected)
            plan.cancelled = True
            plan.version += 1
            plan.save(update_fields=["cancelled", "version"])
            if room.workspace_id:
                s.emit(s.member_ids(room.workspace), "Lịch đi xem đã hủy; hãy thống nhất lịch mới", destination, room.workspace)
        elif action == "checklist-add":
            room.checklist.create(title=text(data, "title", 250, True))
        elif action == "checklist-update":
            item = room.checklist.filter(pk=number(data.get("item"))).first()
            if not item:
                raise s.DomainError("Mục kiểm tra không thuộc căn này.", 403)
            s.assert_version(item, expected)
            item.done, item.note = yes_no(data, "done"), text(data, "note", 500)
            item.checked_by, item.checked_at = actor, timezone.now()
            item.version += 1
            item.save()
        elif action == "evidence":
            image = room.images.filter(pk=image_uuid(data.get("image"))).first() if data.get("image") else None
            if data.get("image") and not image:
                raise s.DomainError("Ảnh bằng chứng không thuộc căn này.", 403)
            room.evidence.create(author=actor, note=text(data, "note", 3000, True), image=image)
            if room.workspace_id:
                s.emit(s.member_ids(room.workspace), "Có ghi nhận sau khi đi xem, hãy kiểm tra trước khi chọn căn", destination, room.workspace)
        else:
            s.propose_room(actor, room.pk, expected)
            destination = reverse("journey:workspace", args=[room.workspace_id])
    elif action in ("choice-consent", "choice-withdraw"):
        proposal = m.RoomChoiceProposal.objects.filter(pk=number(data.get("proposal"))).first()
        if not proposal:
            raise s.DomainError("Không tìm thấy đề xuất.", 404)
        workspace = s.workspace_for(actor, proposal.workspace_id, lock=True)
        if action == "choice-consent":
            s.consent_choice(actor, proposal.pk, expected)
        else:
            proposal.consents.filter(member=actor).delete()
            workspace.moving_in = False
            workspace.save(update_fields=["moving_in"])
        destination = reverse("journey:workspace", args=[workspace.pk])
    elif action in ("agreement-save", "clause-response", "agreement-consent", "agreement-withdraw", "task-save", "task-update", "task-template", "move-in-start"):
        workspace = s.workspace_for(actor, number(data.get("workspace")), lock=True)
        destination = reverse("journey:workspace", args=[workspace.pk])
        if action == "agreement-save":
            form = f.AgreementForm(data)
            s.save_agreement(actor, workspace.pk, clean_form(form), expected)
            destination = reverse("journey:agreement", args=[workspace.pk])
        elif action in ("clause-response", "agreement-consent", "agreement-withdraw"):
            agreement = m.Agreement.objects.filter(workspace=workspace).first()
            if not agreement:
                raise s.DomainError("Chưa có bản thống nhất.", 404)
            s.assert_version(agreement, expected)
            if action == "clause-response":
                key = data.get("clause")
                if key not in s.CLAUSES:
                    raise s.DomainError("Điều khoản không hợp lệ.")
                m.ClauseResponse.objects.update_or_create(agreement=agreement, member=actor, version=agreement.version, key=key,
                                                         defaults={"accepted": yes_no(data, "accepted"), "note": text(data, "note", 500)})
                agreement.consents.filter(member=actor, version=agreement.version).delete()
                workspace.moving_in = False
                workspace.save(update_fields=["moving_in"])
            elif action == "agreement-consent":
                s.consent_agreement(actor, workspace.pk, expected)
            else:
                agreement.consents.filter(member=actor, version=agreement.version).delete()
                workspace.moving_in = False
                workspace.save(update_fields=["moving_in"])
            destination = reverse("journey:agreement", args=[workspace.pk])
        elif action == "task-save":
            task_id = number(data.get("task"), 0)
            task = workspace.tasks.filter(pk=task_id).first() if task_id else None
            if task_id and not task:
                raise s.DomainError("Việc cần làm không thuộc không gian này.", 403)
            if task:
                s.assert_version(task, expected)
            form = f.TaskForm(data, instance=task, workspace=workspace)
            clean_form(form)
            task = form.save(commit=False)
            task.workspace = workspace
            if task.pk:
                task.version += 1
            task.save()
            s.emit(s.member_ids(workspace), "Kế hoạch chuyển vào có việc hoặc phân công mới", destination, workspace)
        elif action == "task-template":
            for title in ("Kiểm tra hợp đồng và các khoản tiền đã thống nhất", "Chốt ngày chuyển và phương tiện vận chuyển", "Chuẩn bị đồ dùng chung và đồ riêng", "Nhận chìa khóa, kiểm tra và ghi nhận bàn giao"):
                workspace.tasks.get_or_create(title=title)
        elif action == "task-update":
            task = workspace.tasks.filter(pk=number(data.get("task"))).first()
            if not task:
                raise s.DomainError("Việc cần làm không thuộc không gian này.", 403)
            s.assert_version(task, expected)
            task.done = yes_no(data, "done")
            task.version += 1
            task.save()
        else:
            agreement = m.Agreement.objects.filter(workspace=workspace).first()
            if not agreement or not s.agreement_confirmed(agreement):
                raise s.DomainError("Cần xác nhận bản thống nhất hiện tại trước khi bắt đầu chuyển vào.", 409)
            workspace.moving_in = True
            workspace.save(update_fields=["moving_in"])
    elif action == "notification-read":
        actor.notifications.filter(pk=number(data.get("notification"))).update(read=True)
        destination = reverse("journey:notifications")
    else:
        raise s.DomainError("Thao tác không được hỗ trợ.", 404)
    response = {"redirect": destination}
    if action == "note":
        response["version"] = note.version
    elif action == "preferences":
        response["version"] = living.version
    elif action == "agreement-save":
        response["version"] = m.Agreement.objects.get(workspace=workspace).version
    return response


@page
@require_POST
def action(request, action):
    payload = {key: values for key, values in request.POST.lists() if key not in ("csrfmiddlewaretoken", "mutation_key")}
    if request.FILES and (action != "image-upload" or set(request.FILES) != {"image"}
                          or len(request.FILES.getlist("image")) != 1):
        raise s.DomainError("Chỉ gửi một ảnh trong thao tác thêm ảnh.")
    for key, uploaded in request.FILES.items():
        if uploaded.size > 5 * 1024 * 1024:
            raise s.DomainError("Ảnh cần nhỏ hơn 5 MB.")
        digest = hashlib.sha256()
        for chunk in uploaded.chunks():
            digest.update(chunk)
        payload["file:" + key] = digest.hexdigest()
        uploaded.seek(0)
    response = s.run_mutation(request.actor, action, request.POST.get("mutation_key"), payload, lambda: perform(request, action))
    if request.headers.get("Accept") == "application/json":
        return JsonResponse(response)
    return redirect(response["redirect"])
