from typing import Any, Dict, List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class CostItemIn(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    period: Literal["monthly", "initial", "deposit"]
    state: Literal["unknown", "estimated", "known"]
    amount: Optional[int] = Field(None, ge=0, le=10**12)
    source: str = Field("", max_length=250)


class CostSplitRequest(BaseModel):
    room_id: Optional[int] = None
    costs: List[CostItemIn]
    weights: Optional[Dict[str, int]] = None


class MemberShareOut(BaseModel):
    id: int
    monthly: int
    initial: int
    deposit: int
    upfront: int
    monthly_budget: Optional[int] = None
    upfront_budget: Optional[int] = None
    monthly_over_budget: bool = False
    upfront_over_budget: bool = False


class SharedCostResultOut(BaseModel):
    totals: Dict[str, int]
    members: List[MemberShareOut]
    weights: Dict[str, int]
    unknown: List[Dict[str, str]]
    estimated: List[str]
    complete: bool
    details: List[Dict[str, Any]]


class CostScenarioSaveRequest(BaseModel):
    room_id: int
    expected_version: int
    weights: Dict[str, int]
    mutation_key: UUID
