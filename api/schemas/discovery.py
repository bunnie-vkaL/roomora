from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class SwipeRequest(BaseModel):
    target_id: int
    choice: Literal["like", "pass"]
    mutation_key: UUID = Field(description="Client UUID to ensure idempotency")


class SwipeResponse(BaseModel):
    matched: bool
    choice: str
    target_id: int
    conversation_id: Optional[int] = None
    redirect_url: Optional[str] = None
    announcement: str


class UndoRequest(BaseModel):
    mutation_key: UUID


class UndoResponse(BaseModel):
    success: bool
    announcement: str


class SaveCandidateRequest(BaseModel):
    candidate_id: int
    saved: bool
    mutation_key: UUID


class SaveCandidateResponse(BaseModel):
    candidate_id: int
    saved: bool
    announcement: str


class CandidateCardOut(BaseModel):
    id: int
    name: str
    age: int
    gender: str
    hometown: str
    bio: str
    avatar_url: Optional[str] = None
    areas: List[str]
    rent_min: int
    rent_max: int
    score: Optional[int] = None
    similarities: List[str]
    differences: List[str]
    warnings: List[str]
    is_saved: bool = False
    sleep_at: Optional[str] = None
    wake_at: Optional[str] = None
    move_in_from: Optional[str] = None
    move_in_until: Optional[str] = None
    needs: Optional[str] = None
