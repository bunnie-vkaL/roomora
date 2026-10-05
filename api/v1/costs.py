from fastapi import APIRouter, Depends, HTTPException, status
from core.models import Profile
from core import models as m
from core.costs import calculate_shared_costs
from core.services import (
    DomainError,
    members_for_cost,
    room_for,
    run_mutation,
    save_scenario,
)
from api.dependencies import get_current_profile
from api.schemas.costs import (
    CostScenarioSaveRequest,
    CostSplitRequest,
    MemberShareOut,
    SharedCostResultOut,
)

router = APIRouter(prefix="/costs", tags=["Cost Allocation Engine"])


@router.post("/calculate", response_model=SharedCostResultOut)
def calculate_costs(
    payload: CostSplitRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Calculate exact integer VND cost distribution across members without rounding loss."""
    if payload.room_id:
        try:
            room = room_for(actor, payload.room_id)
            members = members_for_cost(room)
        except DomainError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.message)
    else:
        living = getattr(actor, "living", None)
        members = [
            {
                "id": actor.pk,
                "monthly_budget": living.total_monthly_budget if living else None,
                "upfront_budget": living.upfront_budget if living else None,
            }
        ]

    costs_data = [item.model_dump() for item in payload.costs]

    try:
        calc = calculate_shared_costs(costs_data, members, payload.weights)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    members_out = [
        MemberShareOut(
            id=m["id"],
            monthly=m["monthly"],
            initial=m["initial"],
            deposit=m["deposit"],
            upfront=m["upfront"],
            monthly_budget=m.get("monthly_budget"),
            upfront_budget=m.get("upfront_budget"),
            monthly_over_budget=m.get("monthly_over_budget", False),
            upfront_over_budget=m.get("upfront_over_budget", False),
        )
        for m in calc["members"]
    ]

    return SharedCostResultOut(
        totals=calc["totals"],
        members=members_out,
        weights=calc["weights"],
        unknown=calc["unknown"],
        estimated=calc["estimated"],
        complete=calc["complete"],
        details=calc["details"],
    )


@router.post("/scenario")
def save_cost_scenario(
    payload: CostScenarioSaveRequest,
    actor: Profile = Depends(get_current_profile),
):
    """Persist a verified cost scenario for a room version."""
    def operation():
        scenario = save_scenario(
            actor=actor,
            room_id=payload.room_id,
            expected=payload.expected_version,
            weights=payload.weights,
        )
        return {
            "scenario_id": scenario.pk,
            "room_version": scenario.room_version,
            "announcement": "Đã lưu cách chia chi phí hiện tại.",
        }

    try:
        result = run_mutation(
            actor=actor,
            action="scenario",
            key=payload.mutation_key,
            payload={
                "room_id": payload.room_id,
                "expected": payload.expected_version,
                "weights": payload.weights,
            },
            operation=operation,
        )
        return result
    except DomainError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
