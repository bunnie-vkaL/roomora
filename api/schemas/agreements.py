from typing import Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class ClauseSaveRequest(BaseModel):
    workspace_id: int
    clauses: Dict[str, str]
    expected_version: int


class ClauseResponseRequest(BaseModel):
    agreement_id: int
    key: str
    accepted: bool
    note: str = Field("", max_length=500)
    expected_version: int


class ConsentAgreementRequest(BaseModel):
    workspace_id: int
    expected_version: int


class MoveInTaskCreateRequest(BaseModel):
    workspace_id: int
    title: str = Field(min_length=1, max_length=250)
    assignee_id: Optional[int] = None
    due_at: Optional[str] = None


class MoveInTaskToggleRequest(BaseModel):
    done: bool
    expected_version: int


class MoveInTaskOut(BaseModel):
    id: int
    title: str
    done: bool
    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None
    due_at: Optional[str] = None
    version: int
