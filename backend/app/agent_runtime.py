"""所有编排引擎共享的输入安全、查询改写与 Trace 收口层。"""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from uuid import uuid4

from app.models import ChatResponse
from app.query_rewrite import rewrite_query
from app.safety_guard import assess_user_input
from app.trace_store import persist_trace
from app.access_control import get_current_actor
from app.memory_service import get_active_memories, write_explicit_memory
from app.context_compression import compose_context
from app.prompt_registry import resolve_prompt


def execute_agent_request(
    message: str,
    request_id: str | None,
    engine: str,
    core_handler: Callable[[str, str | None, str | None], ChatResponse],
    session_id: str | None = None,
) -> ChatResponse:
    """在编排前做安全边界与受控改写，在编排后统一落 Trace。"""
    started_at = perf_counter()
    resolved_request_id = request_id or f"req-{uuid4().hex[:12]}"
    phase_started = perf_counter()
    safety = assess_user_input(message)
    safety_ms = (perf_counter() - phase_started) * 1000
    phase_started = perf_counter()
    rewrite = rewrite_query(message)
    rewrite_ms = (perf_counter() - phase_started) * 1000
    phase_started = perf_counter()
    if safety.action == "block":
        response = ChatResponse(
            request_id=resolved_request_id,
            type="clarify",
            answer="该请求包含可能改变系统边界、获取内部提示或绕过审批的内容，无法执行。请只描述需要解决的企业 IT 问题。",
            workflow_steps=["input_guard_blocked"],
        )
    else:
        response = core_handler(rewrite.effective_query, resolved_request_id, session_id)
    core_ms = (perf_counter() - phase_started) * 1000

    actor = get_current_actor()
    phase_started = perf_counter()
    memory_write = write_explicit_memory(actor.actor_id, message)
    active_memories = get_active_memories(actor.actor_id)
    memory_ms = (perf_counter() - phase_started) * 1000
    response.trace_id = response.request_id
    response.safety = safety.to_public_dict()
    response.query_rewrite = rewrite.to_public_dict()
    response.memory = {
        "owner_scope": actor.actor_id,
        "retrieved_count": len(active_memories),
        "write": memory_write.to_public_dict(),
    }
    phase_started = perf_counter()
    response.context = compose_context(
        session_id=session_id,
        sources=response.sources,
        active_memories=active_memories,
    ).decision
    context_ms = (perf_counter() - phase_started) * 1000
    response.prompt = resolve_prompt(session_id or resolved_request_id).to_trace_dict()
    response.timing = {
        "total_ms": round((perf_counter() - started_at) * 1000, 3),
        "input_guard_ms": round(safety_ms, 3),
        "query_rewrite_ms": round(rewrite_ms, 3),
        "agent_core_ms": round(core_ms, 3),
        "memory_ms": round(memory_ms, 3),
        "context_compose_ms": round(context_ms, 3),
    }
    persist_trace(
        response,
        original_message=message,
        effective_query=rewrite.effective_query,
        engine=engine,
    )
    return response
