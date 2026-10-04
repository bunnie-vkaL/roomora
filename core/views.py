import csv
import hashlib
import json
import mimetypes
import uuid
from functools import wraps

from django.conf import settings
from django.contrib import messages as django_messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.constants import AREAS, GROUPS, QUESTIONS
from core.forms import (
    AgreementForm,
    EmailAuthenticationForm,
    ImageUploadForm,
    LifestyleQuestionForm,
    PilotExerciseForm,
    PinForm,
    PreferencesForm,
    ProfileForm,
    RegistrationForm,
    RoomCostFormSet,
    RoomForm,
    TaskForm,
    ViewingForm,
)
from core.models import (
    Agreement,
    ClauseResponse,
    Connection,
    ConnectionRequest,
    FactConsent,
    JourneyCheckpoint,
    LifestyleAnswers,
    LivingPreferences,
    OutboxEvent,
    PilotEvent,
    PilotExercise,
    PinnedFact,
    PrivateNote,
    Profile,
    Report,
    RoomChoiceProposal,
    RoomImage,
    RoomOpinion,
    SavedCandidate,
    SearchWorkspace,
    SwipeDecision,
    recommendable_profiles,
)
from core.scoring import REASON_TITLES, SCORING_VERSION, score_profiles
from core.services import (
    CLAUSES,
    DomainError,
    agreement_confirmed,
    assert_version,
    block_profile,
    blocked_profile_ids,
    checkpoint,
    consent_agreement,
    consent_choice,
    conversation_for,
    decide,
    deliver_safely,
    disconnect,
    eligible_target,
    eligible_target,
    emit,
    ensure_checklist,
    invite_workspace,
    leave_workspace,
    member_ids,
    members_for_cost,
    pair_chat_for,
    pair_query,
    proposal_confirmed,
    proposal_current,
    propose_room,
    respond_workspace,
    room_for,
    run_mutation,
    save_agreement,
    save_scenario,
    send_message,
    send_pair_message,
    share_room,
    undo_last,
    workspace_for,
)
from core.costs import calculate_shared_costs
from core.web.account import (
    dashboard,
    delete_avatar,
    login_view,
    logout_view,
    profile_edit,
    questionnaire,
    register,
    upload_avatar,
)
from core.web.pilot import pilot_exercise, pilot_export, pilot_results
from core.web.legacy_discovery import (
    blocked_pair,
    comparison,
    connect,
    connection_action,
    discover,
    ensure_user_profile_for_discovery,
    find_matches,
    overlap,
)
from core.web.common import clean_form, image_uuid, number, page, profile_by_id, text, yes_no
from core.web.chat import chat, hub, messages, pair_messages


# ==============================================================================
# Authentication and Public Page Views
# ==============================================================================

def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "core/home.html")


def about(request):
    profile = getattr(request.user, "profile", None) if request.user.is_authenticated else None
    selected_area = request.GET.get("area", "")
    if selected_area not in AREAS:
        selected_area = profile.areas[0] if profile and profile.areas else AREAS[0]
    can_recommend = bool(
        settings.ROOMORA_JOURNEY_ENABLED and profile and profile.is_published
        and profile.completed and selected_area in profile.areas
    )
    recommendations = []
    if can_recommend:
        recommendations = candidate_rows(profile, area=selected_area)[:3]
    return render(request, "core/about.html", {
        "areas": AREAS,
        "selected_area": selected_area,
        "profile": profile,
        "can_recommend": can_recommend,
        "recommendations": recommendations,
        "show_area_guide": request.path == "/about/",
    })


# ==============================================================================
# Roommate Discovery Views
# ==============================================================================

def candidate_card(actor, profile, result=None, context=None):
    result = result or eligible_target(actor, profile)
    living = getattr(profile, "living", None)
    source = getattr(profile, "sample_source", None)
    estimated_answers = set(source.estimated_answers) if source else set()
    lifestyle_sections = []
    answers = profile.answers.values if hasattr(profile, "answers") else {}
    for group_key, (group_title, _) in GROUPS.items():
        choices = [{"title": REASON_TITLES[key], "answer": options[answers[key]],
                    "estimated": key in estimated_answers}
                   for key, group, _, options in QUESTIONS if group == group_key and key in answers]
        if choices:
            lifestyle_sections.append({"title": group_title, "choices": choices})
    context_reason = ""
    if context:
        context_reason = f"Cùng cân nhắc {context.title}; cần trao đổi thêm về căn và phần tiền mỗi người."
    return {"profile": profile, "score": result.score, "score_version": result.version,
            "similarities": result.similarities, "differences": result.differences, "warnings": result.warnings,
            "living": living, "lifestyle_sections": lifestyle_sections,
            "behavior": source.behavior_metrics if source else None,
            "context_reason": context_reason,
            "saved": SavedCandidate.objects.filter(owner=actor, candidate=profile).exists()}


def candidate_rows(actor, area="", rent=None, context=None, include_decided=False):
    if not actor.is_published or not actor.completed:
        return []
    candidates = recommendable_profiles().exclude(pk=actor.pk).select_related("answers", "living", "sample_source")
    if not include_decided:
        candidates = candidates.exclude(pk__in=actor.swipes.values("target_id"))
    rows = []
    for profile in candidates:
        if area and area not in profile.areas:
            continue
        if rent is not None and not profile.rent_min <= rent <= profile.rent_max:
            continue
        if not include_decided and Connection.objects.filter(pair_query(actor, profile), active=True).exists():
            continue
        try:
            result = eligible_target(actor, profile)
        except DomainError:
            continue
        rows.append(candidate_card(actor, profile, result, context))
    return sorted(rows, key=lambda row: (-row["score"], row["profile"].pk))


@page
def modern_discover(request):
    actor = request.actor
    context = room_for(actor, number(request.GET["room"])) if request.GET.get("room") else None
    area = request.GET.get("area", "")
    rent = number(request.GET.get("rent")) if request.GET.get("rent") else None

    # View mode: list or swipe (swipe is default)
    view_mode = request.GET.get("view", request.session.get("discover_view", "swipe"))
    if view_mode not in ("list", "swipe"):
        view_mode = "swipe"
    request.session["discover_view"] = view_mode

    rows = candidate_rows(actor, area, rent, context)

    # Graceful cursor: bad/stale cursor simply resets to start instead of 409
    start = 0
    if request.GET.get("cursor"):
        try:
            cursor = signing.loads(request.GET["cursor"], salt="journey-deck", max_age=3600)
            candidate_start = cursor.get("start", 0)
            if (cursor.get("actor") == actor.pk
                    and cursor.get("filters") == [area, rent, context.pk if context else None]
                    and isinstance(candidate_start, int)
                    and 0 <= candidate_start <= len(rows)):
                start = candidate_start
        except (signing.BadSignature, KeyError, TypeError):
            start = 0  # graceful fallback — no 409

    page_rows = rows[start:start + 10]
    # Build card dicts (resolve saved status, etc.) only for the current page
    cards = page_rows

    has_next = start + 10 < len(rows)
    next_cursor = (
        signing.dumps(
            {"actor": actor.pk, "filters": [area, rent, context.pk if context else None], "start": start + 10},
            salt="journey-deck",
        )
        if has_next else ""
    )

    checkpoint(actor, reverse("journey:discover"))
    guide_area = area or (actor.areas[0] if actor.areas else AREAS[0])
    guide_recommendations = candidate_rows(actor, guide_area, rent, context)[:3]

    # URL helpers for template
    def _url_with(extra):
        params = {k: v for k, v in request.GET.items() if k not in ("cursor", "view")}
        params.update(extra)
        from urllib.parse import urlencode
        return reverse("journey:discover") + "?" + urlencode({k: v for k, v in params.items() if v})

    list_url = _url_with({"view": "list"})
    swipe_url = _url_with({"view": "swipe"})
    all_areas_url = _url_with({"area": ""})
    next_url = _url_with({"cursor": next_cursor}) if next_cursor else ""

    return render(request, "journey/discover.html", {
        "cards": cards,
        "next_cursor": next_cursor,
        "next_url": next_url,
        "list_url": list_url,
        "swipe_url": swipe_url,
        "all_areas_url": all_areas_url,
        "view_mode": view_mode,
        "actor": actor,
        "profile": actor,
        "areas": AREAS,
        "selected_area": guide_area,
        "rent": rent or "",
        "room_context": context,
        "can_recommend": True,
        "recommendations": guide_recommendations,
    })


@page
def candidate(request, profile_id):
    profile = profile_by_id(profile_id)
    card = candidate_card(request.actor, profile)
    note = PrivateNote.objects.filter(owner=request.actor, candidate=profile).first()
    checkpoint(request.actor, request.path)
    return render(request, "journey/candidate.html", {"card": card, "actor": request.actor, "note": note})


@page
def saved(request):
    cards = []
    for row in request.actor.saved_candidates.select_related("candidate__answers", "candidate__living"):
        try:
            cards.append(candidate_card(request.actor, row.candidate))
        except DomainError:
            continue
    return render(request, "journey/saved.html", {"cards": cards})


@page
def compare_candidates(request):
    ids = request.GET.getlist("candidate")
    if not 2 <= len(ids) <= 3 or len(set(ids)) != len(ids):
        raise DomainError("Chọn hai hoặc ba người đã lưu để so sánh.")
    cards = []
    for profile_id in ids:
        profile = profile_by_id(profile_id)
        if not SavedCandidate.objects.filter(owner=request.actor, candidate=profile).exists():
            raise DomainError("Chỉ so sánh người bạn đã lưu.", 403)
        cards.append(candidate_card(request.actor, profile))
    return render(request, "journey/compare.html", {"cards": cards, "actor": request.actor})


@page
def preferences(request):
    living = LivingPreferences.objects.filter(profile=request.actor).first()
    checkpoint(request.actor, request.path)
    return render(request, "journey/preferences.html", {"form": PreferencesForm(instance=living), "version": living.version if living else 0})


# ==============================================================================
# Workspace, Rooms, and Photos Views
# ==============================================================================

def choice_context(workspace):
    proposal = workspace.proposals.select_related("room", "scenario", "workspace").order_by("-pk").first()
    calculation = None
    if proposal:
        calculation = proposal.scenario.calculation
        profiles = {profile.pk: profile for profile in Profile.objects.filter(pk__in=[row["id"] for row in calculation["members"]])}
        for row in calculation["members"]:
            row["profile"] = profiles.get(row["id"])
    return {"proposal": proposal, "proposal_current": proposal_current(proposal) if proposal else False,
            "proposal_confirmed": proposal_confirmed(proposal) if proposal else False,
            "proposal_calculation": calculation,
            "choice_consents": set(proposal.consents.values_list("member_id", flat=True)) if proposal else set()}


def room_cost_overview(room_option, member_count=1):
    """Return a lightweight cost summary dict for a room option card.

    Keys:
        monthly_total   – total monthly rent (VNĐ)
        deposit_total   – total deposit
        per_person_monthly  – monthly / member_count
        per_person_upfront  – (deposit + initial) / member_count
        has_costs       – whether any costs are defined
    """
    costs = list(room_option.costs.values("label", "period", "state", "amount"))
    if not costs:
        return {"monthly_total": 0, "deposit_total": 0,
                "per_person_monthly": 0, "per_person_upfront": 0, "has_costs": False}
    monthly_total = sum(c["amount"] or 0 for c in costs if c["period"] == "monthly" and c["state"] != "unknown")
    deposit_total = sum(c["amount"] or 0 for c in costs if c["period"] == "deposit" and c["state"] != "unknown")
    initial_total = sum(c["amount"] or 0 for c in costs if c["period"] == "initial" and c["state"] != "unknown")
    n = max(member_count, 1)
    return {
        "monthly_total": monthly_total,
        "deposit_total": deposit_total,
        "per_person_monthly": monthly_total // n,
        "per_person_upfront": (deposit_total + initial_total) // n,
        "has_costs": bool(costs),
    }




@page
def workspace(request, workspace_id):
    ws = workspace_for(request.actor, workspace_id)
    checkpoint(request.actor, request.path, ws)
    context = choice_context(ws)
    agreement_obj = Agreement.objects.filter(workspace=ws).select_related("choice__room", "choice__scenario", "choice__workspace").first()
    active_members = list(ws.members.filter(active=True).select_related("profile"))
    member_count = len(active_members) or 1
    board_rooms = list(ws.rooms.prefetch_related("opinions__member", "images", "costs"))
    for option in board_rooms:
        option.member_opinions = opinions_for_room(option)
        option.cost_overview = room_cost_overview(option, member_count=member_count)
    context.update({"workspace": ws, "actor": request.actor, "rooms": board_rooms,
                    "members": active_members,
                    "member_count": member_count,
                    "agreement_confirmed": agreement_confirmed(agreement_obj) if agreement_obj else False,
                    "tasks": [{"task": task, "form": TaskForm(instance=task, workspace=ws, auto_id=f"id_task_{task.pk}_%s")} for task in ws.tasks.select_related("assignee")],
                    "task_form": TaskForm(workspace=ws),
                    "private_rooms": request.actor.room_options.filter(workspace__isnull=True)})
    return render(request, "journey/workspace.html", context)


@page
def rooms(request):
    private_rooms = list(request.actor.room_options.filter(workspace__isnull=True).prefetch_related("images", "costs"))
    for option in private_rooms:
        option.cost_overview = room_cost_overview(option, member_count=1)
    workspaces = list(request.actor.workspaces.filter(active=True, workspace__status="active").select_related("workspace"))
    return render(request, "journey/rooms.html", {"rooms": private_rooms, "workspaces": workspaces})


@page
def edit_room(request, room_id=None):
    room_obj = room_for(request.actor, room_id) if room_id else None
    ws = room_obj.workspace if room_obj else workspace_for(request.actor, number(request.GET["workspace"])) if request.GET.get("workspace") else None
    initial_costs = [{"label": "Tiền thuê", "period": "monthly", "state": "unknown"},
                     {"label": "Tiền cọc", "period": "deposit", "state": "unknown"},
                     {"label": "Khoản một lần đầu kỳ", "period": "initial", "state": "unknown"}]
    return render(request, "journey/room_edit.html", {"form": RoomForm(instance=room_obj), "costs": RoomCostFormSet(instance=room_obj, prefix="costs", initial=initial_costs if room_obj is None else None), "room": room_obj, "workspace": ws})


def room_calculation(room_obj):
    scenario = room_obj.scenarios.filter(room_version=room_obj.version).order_by("-pk").first()
    costs = list(room_obj.costs.values("label", "period", "state", "amount", "source"))
    calculation = calculate_shared_costs(costs, members_for_cost(room_obj), scenario.weights if scenario else None)
    profiles = {profile.pk: profile for profile in Profile.objects.filter(pk__in=[row["id"] for row in calculation["members"]]).select_related("living")}
    for row in calculation["members"]:
        row["profile"] = profiles[row["id"]]
        row["living"] = getattr(profiles[row["id"]], "living", None)
        row["weight"] = scenario.weights.get(str(row["id"]), 1) if scenario else 1
    return calculation, scenario


def opinions_for_room(room_obj):
    if not room_obj.workspace_id:
        return []
    opinions = {opinion.member_id: opinion for opinion in room_obj.opinions.all()}
    return [{"profile": profile, "opinion": opinions.get(profile.pk)}
            for profile in Profile.objects.filter(pk__in=member_ids(room_obj.workspace)).order_by("pk")]


@page
def room(request, room_id):
    room_obj = room_for(request.actor, room_id)
    checkpoint(request.actor, request.path, room_obj.workspace)
    calculation, scenario = room_calculation(room_obj)
    ws_member_ids = set(member_ids(room_obj.workspace)) if room_obj.workspace_id else {request.actor.pk}
    viewings = []
    for plan in room_obj.viewings.order_by("-at"):
        accepted = set(plan.responses.filter(version=plan.version, accepted=True).values_list("member_id", flat=True))
        viewings.append({"plan": plan, "confirmed": not plan.cancelled and accepted == ws_member_ids, "accepted": accepted})
    return render(request, "journey/room.html", {"room": room_obj, "actor": request.actor, "calculation": calculation, "scenario": scenario,
                  "member_opinions": opinions_for_room(room_obj),
                  "opinion": room_obj.opinions.filter(member=request.actor).first(), "images": room_obj.images.prefetch_related("pins__author"),
                  "viewings": viewings, "viewing_form": ViewingForm(), "checklist": room_obj.checklist.select_related("checked_by"),
                  "evidence": room_obj.evidence.select_related("author", "image").order_by("-pk"), "private_workspaces": request.actor.workspaces.filter(active=True, workspace__status="active").select_related("workspace") if not room_obj.workspace_id else []})


@page
def compare_rooms(request):
    ids = request.GET.getlist("room")
    if not 2 <= len(ids) <= 3 or len(set(ids)) != len(ids):
        raise DomainError("Chọn hai hoặc ba căn để so sánh.")
    options = []
    for room_id in ids:
        option = room_for(request.actor, number(room_id))
        calculation, _ = room_calculation(option)
        options.append({"room": option, "calculation": calculation, "member_opinions": opinions_for_room(option)})
    return render(request, "journey/room_compare.html", {"options": options})


@page
def image(request, image_id):
    img = RoomImage.objects.filter(pk=image_id).first()
    if not img:
        raise Http404
    room_for(request.actor, img.room_id)
    try:
        response = FileResponse(img.image.open("rb"), content_type=mimetypes.guess_type(img.image.name)[0] or "application/octet-stream")
    except FileNotFoundError:
        raise Http404
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


# ==============================================================================
# Living Agreement Views
# ==============================================================================

@page
def agreement(request, workspace_id):
    ws = workspace_for(request.actor, workspace_id)
    agreement_obj = Agreement.objects.filter(workspace=ws).select_related("choice__room", "choice__scenario", "choice__workspace").first()
    clauses = agreement_obj.clauses if agreement_obj else {
        "money": "",
        "cleaning": "Luân phiên dọn khu vực chung; cùng thống nhất lịch cụ thể.",
        "guests": "Trao đổi trước khi mời khách ở lại.",
        "quiet": "",
        "privacy": "Tôn trọng không gian riêng; hỏi trước khi dùng đồ của nhau."
    }
    if not agreement_obj:
        proposal = ws.proposals.select_related("room", "scenario").order_by("-pk").first()
        if proposal and proposal_confirmed(proposal):
            clauses["money"] = f"Căn: {proposal.room.title}. Các khoản và phần tiền theo cách chia đã xác nhận #{proposal.scenario_id}."
    responses = []
    if agreement_obj:
        for key, label in CLAUSES.items():
            responses.append({
                "key": key,
                "label": label,
                "text": agreement_obj.clauses.get(key, ""),
                "responses": agreement_obj.responses.filter(version=agreement_obj.version, key=key).select_related("member")
            })
    checkpoint(request.actor, request.path, ws)
    return render(request, "journey/agreement.html", {
        "workspace": ws,
        "agreement": agreement_obj,
        "form": AgreementForm(initial=clauses),
        "responses": responses,
        "confirmed": agreement_confirmed(agreement_obj) if agreement_obj else False,
        "consents": set(agreement_obj.consents.filter(version=agreement_obj.version).values_list("member_id", flat=True)) if agreement_obj else set(),
        "actor": request.actor
    })


# ==============================================================================
# Mutation Action Dispatcher, Notifications, and Resume Checkpoint Views
# ==============================================================================

@page
def notifications(request):
    for event_id in OutboxEvent.objects.filter(delivered=False).values_list("pk", flat=True)[:100]:
        deliver_safely(event_id)
    rows = []
    for notification in request.actor.notifications.select_related("event").order_by("-pk")[:100]:
        if notification.event.workspace_id:
            try:
                workspace_for(request.actor, notification.event.workspace_id)
            except DomainError:
                continue
        rows.append(notification)
    return render(request, "journey/notifications.html", {"notifications_list": rows})


@page
def resume(request):
    cp = JourneyCheckpoint.objects.filter(profile=request.actor).first()
    if cp:
        if cp.workspace_id:
            try:
                workspace_for(request.actor, cp.workspace_id)
            except DomainError:
                return redirect("journey:hub")
        # Checkpoints are written by our views; never trust a client supplied destination.
        if cp.path.startswith("/together/") and "//" not in cp.path and "\\" not in cp.path:
            return redirect(cp.path)
    return redirect("journey:hub")


def perform(request, action_name):
    actor, data = request.actor, request.POST
    expected = data.get("expected_version")
    destination = reverse("journey:hub")
    if action_name in ("like", "pass", "save-candidate", "note", "block", "report"):
        target = profile_by_id(data.get("target"))
        destination = reverse("journey:discover")
        if action_name in ("like", "pass"):
            conversation = decide(actor, target, action_name)
            if conversation:
                destination = reverse("journey:chat", args=[conversation.pk])
            elif action_name == "like":
                destination = f"{reverse('journey:hub')}?chat={target.pk}"
        elif action_name == "save-candidate":
            eligible_target(actor, target)
            if yes_no(data, "saved"):
                SavedCandidate.objects.get_or_create(owner=actor, candidate=target)
            else:
                SavedCandidate.objects.filter(owner=actor, candidate=target).delete()
            destination = reverse("journey:saved")
        elif action_name == "note":
            eligible_target(actor, target)
            note = PrivateNote.objects.filter(owner=actor, candidate=target).first()
            if note:
                assert_version(note, expected)
                note.version += 1
            elif str(expected) != "0":
                raise DomainError("Ghi chú đã thay đổi.", 409)
            else:
                note = PrivateNote(owner=actor, candidate=target)
            note.body = text(data, "body", 3000)
            note.save()
            destination = reverse("journey:candidate", args=[target.pk])
        elif action_name == "block":
            block_profile(actor, target)
        else:
            if target.pk == actor.pk:
                raise DomainError("Không thể báo cáo chính mình.")
            if Report.objects.filter(reporter=actor, created_at__date=timezone.localdate()).count() >= 20:
                raise DomainError("Bạn đã gửi nhiều báo cáo. Vui lòng thử lại vào ngày mai.", 429)
            Report.objects.create(reporter=actor, target=target, reason=text(data, "reason", 1000, True))
    elif action_name == "undo":
        undo_last(actor)
        destination = reverse("journey:discover")
    elif action_name == "disconnect":
        disconnect(actor, number(data.get("connection")))
    elif action_name == "preferences":
        living = LivingPreferences.objects.filter(profile=actor).first()
        if living:
            assert_version(living, expected)
        elif str(expected) != "0":
            raise DomainError("Nhu cầu đã thay đổi.", 409)
        form = PreferencesForm(data, instance=living)
        clean_form(form)
        living = form.save(commit=False)
        living.profile = actor
        if living.pk:
            living.version += 1
        living.save()
        destination = reverse("journey:preferences")
    elif action_name == "message" and data.get("target"):
        target = profile_by_id(data.get("target"))
        send_pair_message(actor, target, text(data, "body", 4000, True), data.get("client_id"))
        destination = reverse("journey:hub")
    elif action_name in ("message", "workspace-invite", "fact-pin", "fact-edit", "fact-consent"):
        conversation = conversation_for(actor, number(data.get("conversation")), lock=True,
                                        allow_pending=action_name == "message")
        destination = (reverse("journey:chat", args=[conversation.pk]) if conversation.connection.active
                       else f"{reverse('journey:hub')}?chat={conversation.connection.other(actor).pk}")
        if action_name == "message":
            send_message(actor, conversation.pk, text(data, "body", 4000, True), data.get("client_id"), allow_pending=True)
        elif action_name == "workspace-invite":
            ws = invite_workspace(actor, conversation.pk, text(data, "title", 120))
            if ws.status == "active":
                destination = reverse("journey:workspace", args=[ws.pk])
        elif action_name == "fact-pin":
            source = conversation.messages.filter(pk=number(data.get("source"))).first()
            if not source:
                raise DomainError("Tin nguồn không thuộc cuộc trò chuyện này.", 403)
            PinnedFact.objects.create(conversation=conversation, source=source, author=actor, body=text(data, "body", 1000, True))
        else:
            fact = conversation.facts.filter(pk=number(data.get("fact"))).first()
            if not fact:
                raise DomainError("Thông tin ghim không khả dụng.", 404)
            assert_version(fact, expected)
            if action_name == "fact-edit":
                if fact.author_id != actor.pk:
                    raise DomainError("Chỉ tác giả được sửa thông tin ghim.", 403)
                fact.body = text(data, "body", 1000, True)
                fact.version += 1
                fact.save()
            else:
                FactConsent.objects.get_or_create(fact=fact, member=actor, version=fact.version)
    elif action_name == "workspace-response":
        ws = respond_workspace(actor, number(data.get("workspace")), yes_no(data, "accepted"))
        if ws.status == "active":
            destination = reverse("journey:workspace", args=[ws.pk])
    elif action_name == "workspace-leave":
        leave_workspace(actor, number(data.get("workspace")))
    elif action_name == "room-save":
        room_id = number(data.get("room"), 0)
        room_obj = room_for(actor, room_id, lock=True) if room_id else None
        if room_obj:
            assert_version(room_obj, expected)
        elif str(expected) != "0":
            raise DomainError("Căn đã thay đổi.", 409)
        ws = room_obj.workspace if room_obj else workspace_for(actor, number(data["workspace"]), lock=True) if data.get("workspace") else None
        form = RoomForm(data, instance=room_obj)
        costs = RoomCostFormSet(data, instance=form.instance, prefix="costs")
        clean_form(form)
        if not costs.is_valid():
            raise DomainError(str(costs.errors) + str(costs.non_form_errors()))
        room_obj = form.save(commit=False)
        room_obj.owner = room_obj.owner if room_obj.pk else actor
        room_obj.workspace = ws
        if room_obj.pk:
            room_obj.version += 1
        room_obj.save()
        costs.instance = room_obj
        costs.save()
        ensure_checklist(room_obj)
        if ws:
            ws.moving_in = False
            ws.save(update_fields=["moving_in"])
            emit(member_ids(ws), "Thông tin căn đã thay đổi; hãy kiểm tra quyết định", reverse("journey:room", args=[room_obj.pk]), ws)
        destination = reverse("journey:room", args=[room_obj.pk])
    elif action_name == "room-share":
        room_obj = share_room(actor, number(data.get("room")), number(data.get("workspace")))
        destination = reverse("journey:room", args=[room_obj.pk])
    elif action_name in ("opinion", "scenario", "image-upload", "image-pin", "viewing-save", "viewing-response", "viewing-cancel", "checklist-add", "checklist-update", "evidence", "room-propose"):
        room_obj = room_for(actor, number(data.get("room")), lock=True)
        destination = reverse("journey:room", args=[room_obj.pk])
        if action_name == "opinion":
            if not room_obj.workspace_id:
                raise DomainError("Ý kiến riêng của mỗi thành viên dùng trên căn chung.")
            choice = data.get("choice")
            if choice not in ("interested", "unsure", "no"):
                raise DomainError("Ý kiến không hợp lệ.")
            opinion = room_obj.opinions.filter(member=actor).first()
            if opinion:
                assert_version(opinion, expected)
                opinion.version += 1
            elif str(expected) != "0":
                raise DomainError("Ý kiến đã thay đổi.", 409)
            else:
                opinion = RoomOpinion(room=room_obj, member=actor)
            opinion.choice, opinion.note = choice, text(data, "note", 500)
            opinion.save()
            emit(member_ids(room_obj.workspace), "Một thành viên đã cập nhật ý kiến về căn", destination, room_obj.workspace)
        elif action_name == "scenario":
            weights = {str(member["id"]): number(data.get(f"weight_{member['id']}")) for member in member_ids(room_obj.workspace) if False} # handled via members_for_cost below
            from core.services import members_for_cost
            weights = {str(member["id"]): number(data.get(f"weight_{member['id']}")) for member in members_for_cost(room_obj)}
            save_scenario(actor, room_obj.pk, expected, weights)
        elif action_name == "image-upload":
            form = ImageUploadForm(data, request.FILES)
            clean_form(form)
            RoomImage.objects.create(room=room_obj, image=form.cleaned_data["image"], caption=form.cleaned_data["caption"], creator=actor)
            if room_obj.workspace_id:
                emit(member_ids(room_obj.workspace), "Có ảnh mới để kiểm tra căn và điều cần hỏi", destination, room_obj.workspace)
        elif action_name == "image-pin":
            img = room_obj.images.filter(pk=image_uuid(data.get("image"))).first()
            if not img:
                raise DomainError("Ảnh không thuộc căn này.", 403)
            form = PinForm(data)
            clean_form(form)
            pin = form.save(commit=False)
            pin.image, pin.author = img, actor
            pin.save()
        elif action_name == "viewing-save":
            plan_id = number(data.get("plan"), 0)
            plan = room_obj.viewings.filter(pk=plan_id).first() if plan_id else None
            if plan_id and not plan:
                raise DomainError("Lịch xem không thuộc căn này.", 403)
            if plan:
                assert_version(plan, expected)
                plan.version += 1
            form = ViewingForm(data, instance=plan)
            clean_form(form)
            if form.cleaned_data["at"] <= timezone.now():
                raise DomainError("Hãy đề xuất thời gian trong tương lai.")
            plan = form.save(commit=False)
            plan.room, plan.author = room_obj, actor
            plan.cancelled = False
            plan.save()
            from core.models import ViewingResponse
            ViewingResponse.objects.create(plan=plan, member=actor, version=plan.version, accepted=True)
            if room_obj.workspace_id:
                emit(member_ids(room_obj.workspace), "Có thời gian đi xem nhà mới cần phản hồi", destination, room_obj.workspace)
        elif action_name == "viewing-response":
            plan = room_obj.viewings.filter(pk=number(data.get("plan"))).first()
            if not plan or plan.cancelled:
                raise DomainError("Lịch đi xem không khả dụng.", 404)
            assert_version(plan, expected)
            from core.models import ViewingResponse
            ViewingResponse.objects.update_or_create(plan=plan, member=actor, version=plan.version, defaults={"accepted": yes_no(data, "accepted")})
            if room_obj.workspace_id:
                emit(member_ids(room_obj.workspace), "Có phản hồi mới về thời gian đi xem nhà", destination, room_obj.workspace)
        elif action_name == "viewing-cancel":
            plan = room_obj.viewings.filter(pk=number(data.get("plan"))).first()
            if not plan:
                raise DomainError("Lịch xem không thuộc căn này.", 403)
            assert_version(plan, expected)
            plan.cancelled = True
            plan.version += 1
            plan.save(update_fields=["cancelled", "version"])
            if room_obj.workspace_id:
                emit(member_ids(room_obj.workspace), "Lịch đi xem đã hủy; hãy thống nhất lịch mới", destination, room_obj.workspace)
        elif action_name == "checklist-add":
            room_obj.checklist.create(title=text(data, "title", 250, True))
        elif action_name == "checklist-update":
            item = room_obj.checklist.filter(pk=number(data.get("item"))).first()
            if not item:
                raise DomainError("Mục kiểm tra không thuộc căn này.", 403)
            assert_version(item, expected)
            item.done, item.note = yes_no(data, "done"), text(data, "note", 500)
            item.checked_by, item.checked_at = actor, timezone.now()
            item.version += 1
            item.save()
        elif action_name == "evidence":
            img = room_obj.images.filter(pk=image_uuid(data.get("image"))).first() if data.get("image") else None
            if data.get("image") and not img:
                raise DomainError("Ảnh bằng chứng không thuộc căn này.", 403)
            room_obj.evidence.create(author=actor, note=text(data, "note", 3000, True), image=img)
            if room_obj.workspace_id:
                emit(member_ids(room_obj.workspace), "Có ghi nhận sau khi đi xem, hãy kiểm tra trước khi chọn căn", destination, room_obj.workspace)
        else:
            propose_room(actor, room_obj.pk, expected)
            destination = reverse("journey:workspace", args=[room_obj.workspace_id])
    elif action_name in ("choice-consent", "choice-withdraw"):
        proposal = RoomChoiceProposal.objects.filter(pk=number(data.get("proposal"))).first()
        if not proposal:
            raise DomainError("Không tìm thấy đề xuất.", 404)
        ws = workspace_for(actor, proposal.workspace_id, lock=True)
        if action_name == "choice-consent":
            consent_choice(actor, proposal.pk, expected)
        else:
            proposal.consents.filter(member=actor).delete()
            ws.moving_in = False
            ws.save(update_fields=["moving_in"])
        destination = reverse("journey:workspace", args=[ws.pk])
    elif action_name in ("agreement-save", "clause-response", "agreement-consent", "agreement-withdraw", "task-save", "task-update", "task-template", "move-in-start"):
        ws = workspace_for(actor, number(data.get("workspace")), lock=True)
        destination = reverse("journey:workspace", args=[ws.pk])
        if action_name == "agreement-save":
            form = AgreementForm(data)
            save_agreement(actor, ws.pk, clean_form(form), expected)
            destination = reverse("journey:agreement", args=[ws.pk])
        elif action_name in ("clause-response", "agreement-consent", "agreement-withdraw"):
            agreement_obj = Agreement.objects.filter(workspace=ws).first()
            if not agreement_obj:
                raise DomainError("Chưa có bản thống nhất.", 404)
            assert_version(agreement_obj, expected)
            if action_name == "clause-response":
                key = data.get("clause")
                if key not in CLAUSES:
                    raise DomainError("Điều khoản không hợp lệ.")
                ClauseResponse.objects.update_or_create(agreement=agreement_obj, member=actor, version=agreement_obj.version, key=key,
                                                         defaults={"accepted": yes_no(data, "accepted"), "note": text(data, "note", 500)})
                agreement_obj.consents.filter(member=actor, version=agreement_obj.version).delete()
                ws.moving_in = False
                ws.save(update_fields=["moving_in"])
            elif action_name == "agreement-consent":
                consent_agreement(actor, ws.pk, expected)
            else:
                agreement_obj.consents.filter(member=actor, version=agreement_obj.version).delete()
                ws.moving_in = False
                ws.save(update_fields=["moving_in"])
            destination = reverse("journey:agreement", args=[ws.pk])
        elif action_name == "task-save":
            task_id = number(data.get("task"), 0)
            task = ws.tasks.filter(pk=task_id).first() if task_id else None
            if task_id and not task:
                raise DomainError("Việc cần làm không thuộc không gian này.", 403)
            if task:
                assert_version(task, expected)
            form = TaskForm(data, instance=task, workspace=ws)
            clean_form(form)
            task = form.save(commit=False)
            task.workspace = ws
            if task.pk:
                task.version += 1
            task.save()
            emit(member_ids(ws), "Kế hoạch chuyển vào có việc hoặc phân công mới", destination, ws)
        elif action_name == "task-template":
            for title in ("Kiểm tra hợp đồng và các khoản tiền đã thống nhất", "Chốt ngày chuyển và phương tiện vận chuyển", "Chuẩn bị đồ dùng chung và đồ riêng", "Nhận chìa khóa, kiểm tra và ghi nhận bàn giao"):
                ws.tasks.get_or_create(title=title)
        elif action_name == "task-update":
            task = ws.tasks.filter(pk=number(data.get("task"))).first()
            if not task:
                raise DomainError("Việc cần làm không thuộc không gian này.", 403)
            assert_version(task, expected)
            task.done = yes_no(data, "done")
            task.version += 1
            task.save()
        else:
            agreement_obj = Agreement.objects.filter(workspace=ws).first()
            if not agreement_obj or not agreement_confirmed(agreement_obj):
                raise DomainError("Cần xác nhận bản thống nhất hiện tại trước khi bắt đầu chuyển vào.", 409)
            ws.moving_in = True
            ws.save(update_fields=["moving_in"])
    elif action_name == "notification-read":
        actor.notifications.filter(pk=number(data.get("notification"))).update(read=True)
        destination = reverse("journey:notifications")
    else:
        raise DomainError("Thao tác không được hỗ trợ.", 404)
    response = {"redirect": destination}
    if action_name == "note":
        response["version"] = note.version
    elif action_name == "preferences":
        response["version"] = living.version
    elif action_name == "agreement-save":
        response["version"] = Agreement.objects.get(workspace=ws).version
    return response


@page
@require_POST
def action(request, action):
    payload = {key: values for key, values in request.POST.lists() if key not in ("csrfmiddlewaretoken", "mutation_key")}
    if request.FILES and (action != "image-upload" or set(request.FILES) != {"image"}
                          or len(request.FILES.getlist("image")) != 1):
        raise DomainError("Chỉ gửi một ảnh trong thao tác thêm ảnh.")
    for key, uploaded in request.FILES.items():
        if uploaded.size > 5 * 1024 * 1024:
            raise DomainError("Ảnh cần nhỏ hơn 5 MB.")
        digest = hashlib.sha256()
        for chunk in uploaded.chunks():
            digest.update(chunk)
        payload["file:" + key] = digest.hexdigest()
        uploaded.seek(0)
    response = run_mutation(request.actor, action, request.POST.get("mutation_key"), payload, lambda: perform(request, action))
    if request.headers.get("Accept") == "application/json":
        return JsonResponse(response)
    return redirect(response["redirect"])


# ==============================================================================
# Backward Compatibility Aliases
# ==============================================================================

# urls.py references views.modern_discover as the journey discover endpoint
# and views.discover as the legacy discover endpoint — both are defined above.
