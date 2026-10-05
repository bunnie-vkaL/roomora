"""Workspace, rooms, costs, and agreement web views."""

import mimetypes
from django.http import FileResponse, Http404
from django.shortcuts import render

from core.costs import calculate_shared_costs
from core.forms import AgreementForm, RoomCostFormSet, RoomForm, TaskForm, ViewingForm
from core.models import Agreement, Profile, RoomImage, RoomOpinion
from core.services import (
    CLAUSES,
    DomainError,
    agreement_confirmed,
    checkpoint,
    member_ids,
    members_for_cost,
    proposal_confirmed,
    proposal_current,
    room_for,
    workspace_for,
)
from core.web.common import number, page


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
    costs = list(room_option.costs.values("label", "period", "state", "amount"))
    if not costs:
        return {"monthly": 0, "upfront": 0, "monthly_total": 0, "deposit_total": 0,
                "per_person_monthly": 0, "per_person_upfront": 0, "has_costs": False,
                "missing_count": 0, "estimated": False}
    monthly_costs = [c for c in costs if c["period"] == "monthly"]
    deposit_costs = [c for c in costs if c["period"] == "deposit"]
    initial_costs = [c for c in costs if c["period"] == "initial"]
    
    monthly_total = sum(c["amount"] or 0 for c in monthly_costs if c["state"] != "unknown")
    deposit_total = sum(c["amount"] or 0 for c in deposit_costs if c["state"] != "unknown")
    initial_total = sum(c["amount"] or 0 for c in initial_costs if c["state"] != "unknown")
    
    upfront_total = deposit_total + initial_total
    missing_count = sum(1 for c in costs if c["state"] == "unknown")
    estimated = any(c["state"] == "estimated" for c in costs)
    
    n = max(member_count, 1)
    return {
        "monthly": monthly_total,
        "upfront": upfront_total,
        "monthly_total": monthly_total,
        "deposit_total": deposit_total,
        "per_person_monthly": monthly_total // n,
        "per_person_upfront": upfront_total // n,
        "has_costs": bool(costs),
        "monthly_partial": any(c["state"] == "unknown" for c in monthly_costs) and any(c["state"] != "unknown" for c in monthly_costs),
        "upfront_partial": any(c["state"] == "unknown" for c in deposit_costs + initial_costs) and any(c["state"] != "unknown" for c in deposit_costs + initial_costs),
        "missing_count": missing_count,
        "estimated": estimated,
    }


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
