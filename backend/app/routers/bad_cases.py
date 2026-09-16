"""Bad Case API：从 Trace 标记失败、治理流转到回归用例导出。"""

from fastapi import APIRouter, Header, HTTPException

from app.access_control import can_manage_ticket, resolve_actor
from app.bad_case_store import create_bad_case, export_bad_case_as_eval_case, get_bad_case, list_bad_cases, transition_bad_case
from app.models import BadCaseCreateRequest, BadCaseStatusUpdate


router = APIRouter(prefix="/bad-cases", tags=["bad_cases"])


def _manager_actor(actor_id: str | None, actor_role: str | None):
    actor = resolve_actor(actor_id, actor_role)
    if not can_manage_ticket(actor).allowed:
        raise HTTPException(status_code=403, detail="support_role_required")
    return actor


@router.post("")
def report_bad_case(payload: BadCaseCreateRequest, x_actor_id: str | None = Header(default=None), x_actor_role: str | None = Header(default=None)) -> dict:
    actor = resolve_actor(x_actor_id, x_actor_role)
    try:
        return create_bad_case(**payload.model_dump(), reporter_id=actor.actor_id)
    except ValueError as exc:
        raise HTTPException(status_code=404 if str(exc) == "trace_not_found" else 400, detail=str(exc)) from exc


@router.get("")
def read_bad_cases(status: str | None = None, category: str | None = None) -> list[dict]:
    return list_bad_cases(status=status, category=category)


@router.get("/{bad_case_id}")
def read_bad_case(bad_case_id: str) -> dict:
    case = get_bad_case(bad_case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="bad_case_not_found")
    return case


@router.patch("/{bad_case_id}")
def update_bad_case(bad_case_id: str, payload: BadCaseStatusUpdate, x_actor_id: str | None = Header(default=None), x_actor_role: str | None = Header(default=None)) -> dict:
    actor = _manager_actor(x_actor_id, x_actor_role)
    try:
        return transition_bad_case(bad_case_id, payload.status, actor_id=actor.actor_id)
    except ValueError as exc:
        status_code = 404 if str(exc) == "bad_case_not_found" else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/{bad_case_id}/export")
def export_bad_case(bad_case_id: str, x_actor_id: str | None = Header(default=None), x_actor_role: str | None = Header(default=None)) -> dict:
    _manager_actor(x_actor_id, x_actor_role)
    try:
        return export_bad_case_as_eval_case(bad_case_id)
    except ValueError as exc:
        status_code = 404 if str(exc) == "bad_case_not_found" else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
