import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from django.urls import reverse
from core.models import Profile
from core import models as m
from core.services import (
    DomainError,
    assert_version,
    emit,
    member_ids,
    room_for,
    run_mutation,
    share_room,
)
from api.dependencies import get_current_profile
from api.schemas.rooms import (
    ChecklistItemOut,
    ChecklistToggleRequest,
    ImagePinOut,
    ImagePinRequest,
    RoomOpinionRequest,
    ShareRoomRequest,
)

router = APIRouter(prefix="/rooms", tags=["Shared Rooms & Inspection"])


@router.post("/{room_id}/opinion")
def set_room_opinion(
    room_id: int,
    payload: RoomOpinionRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Submit an opinion (interested / unsure / no) for a shared workspace room."""
    def operation():
        room = room_for(actor, room_id, lock=True)
        if not room.workspace_id:
            raise DomainError("Ý kiến riêng của mỗi thành viên dùng trên căn chung.")

        opinion = room.opinions.filter(member=actor).first()
        if opinion:
            opinion.version += 1
        else:
            opinion = m.RoomOpinion(room=room, member=actor)

        opinion.choice = payload.choice
        opinion.note = payload.note
        opinion.save()

        emit(
            member_ids(room.workspace),
            "Một thành viên đã cập nhật ý kiến về căn",
            reverse("journey:room", args=[room.pk]),
            room.workspace,
        )
        return {
            "success": True,
            "room_id": room.pk,
            "choice": opinion.choice,
            "note": opinion.note,
            "announcement": "Đã lưu ý kiến về căn.",
        }

    try:
        result = run_mutation(
            actor=actor,
            action="opinion",
            key=payload.mutation_key,
            payload={"room_id": room_id, "choice": payload.choice, "note": payload.note},
            operation=operation,
        )
        return result
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)


@router.post("/images/{image_id}/pin", response_model=ImagePinOut)
def add_image_pin(
    image_id: str,
    payload: ImagePinRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Place a pin and question directly on a room image coordinate."""
    try:
        img_uuid = uuid.UUID(image_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã ảnh không hợp lệ.")

    image = m.RoomImage.objects.select_related("room").filter(pk=img_uuid).first()
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ảnh.")

    try:
        room_for(actor, image.room_id)
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)

    pin = m.ImagePin.objects.create(
        image=image,
        author=actor,
        x=payload.x,
        y=payload.y,
        question=payload.question.strip()[:500],
    )

    return ImagePinOut(
        id=pin.pk,
        image_id=str(image.pk),
        author_id=actor.pk,
        author_name=actor.name,
        x=pin.x,
        y=pin.y,
        x_percent=pin.x_percent,
        y_percent=pin.y_percent,
        question=pin.question,
    )


@router.post("/checklist/{checklist_id}/toggle", response_model=ChecklistItemOut)
def toggle_checklist(
    checklist_id: int,
    payload: ChecklistToggleRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Toggle completion status and note for a room viewing checklist item."""
    item = m.ChecklistItem.objects.select_related("room").filter(pk=checklist_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy mục kiểm tra.")

    try:
        room_for(actor, item.room_id, lock=True)
        assert_version(item, payload.expected_version)
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)

    from django.utils import timezone
    item.done = payload.done
    item.note = payload.note.strip()[:500]
    item.checked_by = actor if payload.done else None
    item.checked_at = timezone.now() if payload.done else None
    item.version += 1
    item.save()

    return ChecklistItemOut(
        id=item.pk,
        title=item.title,
        done=item.done,
        note=item.note,
        checked_by_name=item.checked_by.name if item.checked_by else None,
        checked_at=item.checked_at.strftime("%H:%M, %d/%m") if item.checked_at else None,
        version=item.version,
    )


@router.post("/{room_id}/share")
def share_room_to_workspace(
    room_id: int,
    payload: ShareRoomRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Share a privately saved room into a shared workspace as a snapshot."""
    def operation():
        shared = share_room(actor, room_id, payload.workspace_id)
        return {
            "success": True,
            "shared_room_id": shared.pk,
            "redirect_url": reverse("journey:room", args=[shared.pk]),
            "announcement": "Đã chia sẻ căn lên bảng nhà chung.",
        }

    try:
        result = run_mutation(
            actor=actor,
            action="room-share",
            key=payload.mutation_key,
            payload={"room_id": room_id, "workspace_id": payload.workspace_id},
            operation=operation,
        )
        return result
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
