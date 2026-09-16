"""所有编排引擎共享的输入安全、查询改写与 Trace 收口层。"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from app.models import ChatResponse
from app.query_rewrite import rewrite_query
from app.safety_guard import assess_user_input
from app.trace_store import persist_trace
from app.access_control import get_current_actor
from app.memory_service import get_active_memories, write_explicit_memory
from app.context_compression import compose_context


def execute_agent_request(
    message: str,
    request_id: str | None,
    engine: str,
    core_handler: Callable[[str, str | None, str | None], ChatResponse],
    session_id: str | None = None,
) -> ChatResponse:
    """在编排前做安全边界与受控改写，在编排后统一落 Trace。"""
    resolved_request_id = request_id or f"req-{uuid4().hex[:12]}"
    safety = assess_user_input(message)
    rewrite = rewrite_query(message)
    if safety.action == "block":
        response = ChatResponse(
            request_id=resolved_request_id,
            type="clarify",
            answer="该请求包含可能改变系统边界、获取内部提示或绕过审批的内容，无法执行。请只描述需要解决的企业 IT 问题。",
            workflow_steps=["input_guard_blocked"],
        )
    else:
        response = core_handler(rewrite.effective_query, resolved_request_id, session_id)

    actor = get_current_actor()
    memory_write = write_explicit_memory(actor.actor_id, message)
    active_memories = get_active_memories(actor.actor_id)
    response.trace_id = response.request_id
    response.safety = safety.to_public_dict()
    response.query_rewrite = rewrite.to_public_dict()
    response.memory = {
        "owner_scope": actor.actor_id,
        "retrieved_count": len(active_memories),
        "write": memory_write.to_public_dict(),
    }
    response.context = compose_context(
        session_id=session_id,
        sources=response.sources,
        active_memories=active_memories,
    ).decision
    persist_trace(
        response,
        original_message=message,
        effective_query=rewrite.effective_query,
        engine=engine,
    )
    return response
