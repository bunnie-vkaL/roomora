from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class RoomOpinionRequest(BaseModel):
    room_id: int
    choice: Literal["interested", "unsure", "no"]
    note: str = Field("", max_length=500)
    mutation_key: UUID


class ImagePinRequest(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    question: str = Field(min_length=1, max_length=500)


class ImagePinOut(BaseModel):
    id: int
    image_id: str
    author_id: int
    author_name: str
    x: float
    y: float
    x_percent: float
    y_percent: float
    question: str


class ChecklistToggleRequest(BaseModel):
    done: bool
    note: str = Field("", max_length=500)
    expected_version: int


class ChecklistItemOut(BaseModel):
    id: int
    title: str
    done: bool
    note: str
    checked_by_name: Optional[str] = None
    checked_at: Optional[str] = None
    version: int


class ShareRoomRequest(BaseModel):
    room_id: int
    workspace_id: int
    mutation_key: UUID
