from fastapi import APIRouter, Depends, HTTPException, status
from django.shortcuts import get_object_or_404
from django.urls import reverse
from core import models as m
from core.models import Profile
from core.services import DomainError, decide, run_mutation, undo_last
from api.dependencies import get_current_profile
from api.schemas.discovery import (
    SaveCandidateRequest,
    SaveCandidateResponse,
    SwipeRequest,
    SwipeResponse,
    UndoRequest,
    UndoResponse,
)

router = APIRouter(prefix="/discovery", tags=["Discovery & Matching"])


@router.post("/swipe", response_model=SwipeResponse)
def swipe(
    payload: SwipeRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Execute a swipe (Like or Pass) on a candidate with idempotent mutation."""
    target = get_object_or_404(Profile, pk=payload.target_id)

    def operation():
        conversation = decide(actor, target, payload.choice)
        if conversation:
            return {
                "matched": True,
                "choice": payload.choice,
                "target_id": target.pk,
                "conversation_id": conversation.pk,
                "redirect_url": reverse("journey:chat", args=[conversation.pk]),
                "announcement": "Hai bạn đã cùng muốn kết nối!",
            }
        return {
            "matched": False,
            "choice": payload.choice,
            "target_id": target.pk,
            "conversation_id": None,
            "redirect_url": reverse("journey:hub") if payload.choice == "like" else None,
            "announcement": f"Đã {'chọn kết nối với' if payload.choice == 'like' else 'bỏ qua'} {target.name}.",
        }

    try:
        result = run_mutation(
            actor=actor,
            action=payload.choice,
            key=payload.mutation_key,
            payload={"target_id": payload.target_id, "choice": payload.choice},
            operation=operation,
        )
        return result
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)


@router.post("/undo", response_model=UndoResponse)
def undo_swipe(
    payload: UndoRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Undo the last un-matched swipe decision."""
    def operation():
        undo_last(actor)
        return {
            "success": True,
            "announcement": "Đã hoàn tác lượt quẹt gần nhất.",
        }

    try:
        result = run_mutation(
            actor=actor,
            action="undo",
            key=payload.mutation_key,
            payload={},
            operation=operation,
        )
        return result
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)


@router.post("/save", response_model=SaveCandidateResponse)
def toggle_save_candidate(
    payload: SaveCandidateRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Save or un-save a candidate for later viewing (independent of Like/Pass)."""
    target = get_object_or_404(Profile, pk=payload.candidate_id)

    def operation():
        if payload.saved:
            m.SavedCandidate.objects.get_or_create(owner=actor, candidate=target)
            announcement = f"Đã lưu {target.name} để xem sau."
        else:
            m.SavedCandidate.objects.filter(owner=actor, candidate=target).delete()
            announcement = f"Đã bỏ lưu {target.name}."
        return {
            "candidate_id": target.pk,
            "saved": payload.saved,
            "announcement": announcement,
        }

    try:
        result = run_mutation(
            actor=actor,
            action="save" if payload.saved else "unsave",
            key=payload.mutation_key,
            payload={"candidate_id": payload.candidate_id, "saved": payload.saved},
            operation=operation,
        )
        return result
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
