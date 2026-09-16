"""Trace 查询接口：用于复盘一次 Agent 的安全、检索、工具与输出轨迹。"""

from fastapi import APIRouter, HTTPException

from app.trace_store import get_agentops_metrics, get_trace, get_trace_summary, get_trace_timeline


router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("/summary")
def trace_summary() -> dict[str, int]:
    return get_trace_summary()


@router.get("/agentops")
def agentops_dashboard() -> dict:
    return get_agentops_metrics()


@router.get("/{request_id}/timeline")
def trace_timeline(request_id: str) -> list[dict]:
    timeline = get_trace_timeline(request_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="trace_not_found")
    return timeline


@router.get("/{request_id}")
def trace_detail(request_id: str) -> dict:
    trace = get_trace(request_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace_not_found")
    return trace
