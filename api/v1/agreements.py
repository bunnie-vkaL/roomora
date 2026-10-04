from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from django.utils import timezone
from core.models import Profile
from core import models as m
from core.services import (
    CLAUSES,
    DomainError,
    assert_version,
    consent_agreement,
    member_ids,
    save_agreement,
    workspace_for,
)
from api.dependencies import get_current_profile
from api.schemas.agreements import (
    ClauseResponseRequest,
    ClauseSaveRequest,
    ConsentAgreementRequest,
    MoveInTaskCreateRequest,
    MoveInTaskOut,
    MoveInTaskToggleRequest,
)

router = APIRouter(prefix="/agreements", tags=["Living Agreements & Move-in"])


@router.post("/{workspace_id}/clauses")
def update_agreement_clauses(
    workspace_id: int,
    payload: ClauseSaveRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Save or update the 5 draft agreement clauses."""
    try:
        agreement = save_agreement(
            actor=actor,
            workspace_id=workspace_id,
            clauses=payload.clauses,
            expected=payload.expected_version,
        )
        return {
            "success": True,
            "workspace_id": workspace_id,
            "version": agreement.version,
            "clauses": agreement.clauses,
            "announcement": "Đã lưu bản thống nhất mới.",
        }
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)


@router.post("/{workspace_id}/clauses/{clause_key}/respond")
def respond_to_clause(
    workspace_id: int,
    clause_key: str,
    payload: ClauseResponseRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Accept or mark a specific clause for discussion with optional notes."""
    if clause_key not in CLAUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Điều khoản không hợp lệ.")

    try:
        workspace = workspace_for(actor, workspace_id, lock=True)
        agreement = m.Agreement.objects.filter(workspace=workspace).first()
        if not agreement:
            raise DomainError("Chưa có bản thống nhất.", 404)
        assert_version(agreement, payload.expected_version)

        resp, _ = m.ClauseResponse.objects.update_or_create(
            agreement=agreement,
            member=actor,
            version=agreement.version,
            key=clause_key,
            defaults={
                "accepted": payload.accepted,
                "note": payload.note.strip()[:500],
            },
        )
        # Responding again clears past overall consent
        agreement.consents.filter(member=actor, version=agreement.version).delete()
        workspace.moving_in = False
        workspace.save(update_fields=["moving_in"])

        return {
            "success": True,
            "clause": clause_key,
            "accepted": resp.accepted,
            "note": resp.note,
            "agreement_version": agreement.version,
            "announcement": f"Đã ghi nhận phản hồi cho {CLAUSES[clause_key]}.",
        }
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)


@router.post("/{workspace_id}/consent")
def submit_agreement_consent(
    workspace_id: int,
    payload: ConsentAgreementRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Grant final consent to the current version of the entire living agreement."""
    try:
        consent_agreement(actor, workspace_id, payload.expected_version)
        return {
            "success": True,
            "workspace_id": workspace_id,
            "version": payload.expected_version,
            "announcement": "Bạn đã xác nhận toàn bộ bản thống nhất.",
        }
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)


@router.post("/{workspace_id}/tasks", response_model=MoveInTaskOut)
def create_move_in_task(
    workspace_id: int,
    payload: MoveInTaskCreateRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Add a move-in task to the workspace checklist."""
    try:
        workspace = workspace_for(actor, workspace_id, lock=True)
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)

    assignee = None
    if payload.assignee_id:
        assignee = workspace.members.filter(profile_id=payload.assignee_id, active=True).first()
        assignee = assignee.profile if assignee else None

    due_at = None
    if payload.due_at:
        try:
            from datetime import date
            due_at = date.fromisoformat(payload.due_at)
        except (ValueError, TypeError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ngày hết hạn không hợp lệ.")

    task = m.MoveInTask.objects.create(
        workspace=workspace,
        title=payload.title.strip()[:250],
        assignee=assignee,
        due_at=due_at,
    )

    return MoveInTaskOut(
        id=task.pk,
        title=task.title,
        done=task.done,
        assignee_id=task.assignee_id,
        assignee_name=task.assignee.name if task.assignee else None,
        due_at=str(task.due_at) if task.due_at else None,
        version=task.version,
    )


@router.post("/tasks/{task_id}/toggle", response_model=MoveInTaskOut)
def toggle_move_in_task(
    task_id: int,
    payload: MoveInTaskToggleRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Toggle completion status of a move-in task."""
    task = m.MoveInTask.objects.select_related("workspace", "assignee").filter(pk=task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy việc cần làm.")

    try:
        workspace_for(actor, task.workspace_id, lock=True)
        assert_version(task, payload.expected_version)
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)

    task.done = payload.done
    task.version += 1
    task.save()

    return MoveInTaskOut(
        id=task.pk,
        title=task.title,
        done=task.done,
        assignee_id=task.assignee_id,
        assignee_name=task.assignee.name if task.assignee else None,
        due_at=str(task.due_at) if task.due_at else None,
        version=task.version,
    )
