"""Actions, notifications, and resume views."""

import hashlib
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.forms import AgreementForm, ImageUploadForm, PinForm, PreferencesForm, RoomCostFormSet, RoomForm, TaskForm, ViewingForm
from core.models import (
    Agreement,
    ClauseResponse,
    FactConsent,
    JourneyCheckpoint,
    LivingPreferences,
    OutboxEvent,
    PinnedFact,
    PrivateNote,
    Report,
    RoomChoiceProposal,
    RoomImage,
    RoomOpinion,
    SavedCandidate,
)
from core.services import (
    CLAUSES,
    DomainError,
    agreement_confirmed,
    assert_version,
    block_profile,
    consent_agreement,
    consent_choice,
    conversation_for,
    decide,
    deliver_safely,
    disconnect,
    eligible_target,
    emit,
    ensure_checklist,
    invite_workspace,
    leave_workspace,
    member_ids,
    members_for_cost,
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
from core.web.common import clean_form, image_uuid, number, page, profile_by_id, text, yes_no


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
        if cp.path.startswith("/roommates/") and "//" not in cp.path and "\\" not in cp.path:
            return redirect(cp.path)
    return redirect("journey:hub")


def perform(request, action_name):
    actor, data = request.actor, request.POST
    expected = data.get("expected_version")
    destination = reverse("journey:hub")
    if action_name in ("like", "pass", "save-candidate", "note", "block", "report", "safety"):
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
            destination = reverse("journey:discover")
        elif action_name in ("block", "safety"):
            block_profile(actor, target)
            if action_name == "safety":
                if target.pk == actor.pk:
                    raise DomainError("Không thể báo cáo chính mình.")
                if Report.objects.filter(reporter=actor, created_at__date=timezone.localdate()).count() >= 20:
                    raise DomainError("Bạn đã gửi nhiều báo cáo. Vui lòng thử lại vào ngày mai.", 429)
                Report.objects.create(reporter=actor, target=target, reason=text(data, "reason", 1000, True))
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
