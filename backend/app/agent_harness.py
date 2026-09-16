"""Agent 运行时治理：统一工具策略、步数限制与请求级 Trace。"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Literal
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextvars import copy_context

from pydantic import BaseModel, Field

from app.tool_action_policy import get_tool_action_policy
from app.tool_registry import ToolResult, validate_tool_arguments, run_tool
from app.access_control import authorize_tool, get_current_actor
from app.operation_store import begin_operation, finish_operation, mark_operation_unknown
from app.config import get_read_tool_retry_attempts, get_tool_execution_timeout_seconds

HarnessStatus = Literal[
    "completed", "confirmation_required", "blocked", "failed", "max_steps_exceeded"
]


class HarnessTraceStep(BaseModel):
    step_number: int
    tool_name: str
    risk_level: str
    argument_summary: str
    status: HarnessStatus
    elapsed_ms: float | None = None
    error_type: str | None = None
    actor_id: str | None = None
    authorization_reason: str | None = None
    operation_id: str | None = None


class HarnessSession(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    engine: Literal["rules", "tool_call", "langgraph"]
    max_steps: int = Field(ge=1)
    executed_steps: int = 0
    trace_steps: list[HarnessTraceStep] = Field(default_factory=list)


class HarnessExecutionResult(BaseModel):
    status: HarnessStatus
    tool_result: ToolResult | None = None
    reason: str | None = None
    requires_confirmation: bool = False
    confirmation_reason: str | None = None


def create_harness_session(
    *, request_id: str | None, engine: Literal["rules", "tool_call", "langgraph"], max_steps: int
) -> HarnessSession:
    return HarnessSession(request_id=request_id or str(uuid4()), engine=engine, max_steps=max_steps)


def _argument_summary(arguments: dict[str, Any]) -> str:
    """只记录键与受限长度的值，避免把长文本或敏感原文写入 Trace。"""
    return ", ".join(
        f"{key}={str(value).replace(chr(10), ' ')[:80]}"
        for key, value in sorted(arguments.items())
    )


class AgentHarness:
    """不参与业务规划，只治理每一次真实工具执行。"""

    def execute_tool(
        self, *, session: HarnessSession, tool_name: str, arguments: dict[str, Any], confirmed: bool = False,
        idempotency_key: str | None = None,
    ) -> HarnessExecutionResult:
        policy = get_tool_action_policy(tool_name)
        summary = _argument_summary(arguments)
        step_number = session.executed_steps + 1
        actor = get_current_actor()

        if session.executed_steps >= session.max_steps:
            session.trace_steps.append(HarnessTraceStep(
                step_number=step_number, tool_name=tool_name, risk_level=policy.risk_level,
                argument_summary=summary, status="max_steps_exceeded", error_type="max_steps_exceeded", actor_id=actor.actor_id,
            ))
            return HarnessExecutionResult(status="max_steps_exceeded", reason="本次 Agent 工具执行已达到最大步数。")

        validation_error = validate_tool_arguments(tool_name, arguments)
        if validation_error is not None:
            session.trace_steps.append(HarnessTraceStep(
                step_number=step_number, tool_name=tool_name, risk_level=policy.risk_level,
                argument_summary=summary, status="blocked", error_type=validation_error.error_type, actor_id=actor.actor_id,
            ))
            return HarnessExecutionResult(status="blocked", tool_result=validation_error, reason=validation_error.error)

        authorization = authorize_tool(actor, tool_name, arguments)
        if not authorization.allowed:
            error = ToolResult(tool_name=tool_name, success=False, error="当前身份无权执行该操作。", error_type="authorization_denied")
            session.trace_steps.append(HarnessTraceStep(
                step_number=step_number, tool_name=tool_name, risk_level=policy.risk_level,
                argument_summary=summary, status="blocked", error_type="authorization_denied",
                actor_id=actor.actor_id, authorization_reason=authorization.reason,
            ))
            return HarnessExecutionResult(status="blocked", tool_result=error, reason=error.error)

        if policy.requires_confirmation and not confirmed:
            session.trace_steps.append(HarnessTraceStep(
                step_number=step_number, tool_name=tool_name, risk_level=policy.risk_level,
                argument_summary=summary, status="confirmation_required", actor_id=actor.actor_id,
                authorization_reason=authorization.reason,
            ))
            return HarnessExecutionResult(
                status="confirmation_required", reason=policy.reason,
                requires_confirmation=True, confirmation_reason=policy.reason,
            )

        operation_id: str | None = None
        if policy.risk_level.startswith("write"):
            stable_key = idempotency_key or f"{session.request_id}:{tool_name}"
            try:
                operation, should_execute = begin_operation(actor.actor_id, tool_name, arguments, stable_key)
            except ValueError:
                result = ToolResult(tool_name=tool_name, success=False, error="同一个幂等键不能复用到不同操作。", error_type="idempotency_key_conflict")
                session.trace_steps.append(HarnessTraceStep(step_number=step_number, tool_name=tool_name, risk_level=policy.risk_level, argument_summary=summary, status="blocked", error_type=result.error_type, actor_id=actor.actor_id, authorization_reason=authorization.reason))
                return HarnessExecutionResult(status="blocked", tool_result=result, reason=result.error)
            operation_id = operation.operation_id
            if not should_execute:
                if operation.status == "succeeded" and operation.result is not None:
                    session.trace_steps.append(HarnessTraceStep(step_number=step_number, tool_name=tool_name, risk_level=policy.risk_level, argument_summary=summary, status="completed", actor_id=actor.actor_id, authorization_reason="idempotent_replay", operation_id=operation_id))
                    return HarnessExecutionResult(status="completed", tool_result=operation.result)
                result = ToolResult(tool_name=tool_name, success=False, error="该写操作结果未知或仍在执行中，请查询操作状态，禁止盲重试。", error_type="operation_result_unknown")
                session.trace_steps.append(HarnessTraceStep(step_number=step_number, tool_name=tool_name, risk_level=policy.risk_level, argument_summary=summary, status="blocked", error_type=result.error_type, actor_id=actor.actor_id, authorization_reason="idempotency_pending_or_unknown", operation_id=operation_id))
                return HarnessExecutionResult(status="blocked", tool_result=result, reason=result.error)

        session.executed_steps += 1
        started_at = perf_counter()
        tool_result, timed_out = _execute_with_reliability(
            tool_name, arguments, is_write=policy.risk_level.startswith("write")
        )
        if operation_id is not None:
            if timed_out:
                mark_operation_unknown(operation_id)
            else:
                finish_operation(operation_id, tool_result)
        status: HarnessStatus = "completed" if tool_result.success else "failed"
        session.trace_steps.append(HarnessTraceStep(
            step_number=step_number, tool_name=tool_name, risk_level=policy.risk_level,
            argument_summary=summary, status=status,
            elapsed_ms=round((perf_counter() - started_at) * 1000, 2),
            error_type=tool_result.error_type,
            actor_id=actor.actor_id,
            authorization_reason=authorization.reason,
            operation_id=operation_id,
        ))
        return HarnessExecutionResult(status=status, tool_result=tool_result, reason=tool_result.error)


def _execute_with_reliability(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    is_write: bool,
) -> tuple[ToolResult, bool]:
    """只读工具可受控重试；写工具超时后进入 unknown，绝不盲重试。"""
    attempts = 1 if is_write else get_read_tool_retry_attempts()
    timeout_seconds = get_tool_execution_timeout_seconds()
    last_result: ToolResult | None = None
    for _attempt in range(attempts):
        executor = ThreadPoolExecutor(max_workers=1)
        context = copy_context()
        future = executor.submit(context.run, run_tool, tool_name, **arguments)
        try:
            result = future.result(timeout=timeout_seconds)
        except FutureTimeout:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            error_type = "operation_result_unknown" if is_write else "tool_timeout"
            message = "写操作超时，执行结果未知，已禁止自动重试。" if is_write else "只读工具调用超时。"
            return ToolResult(tool_name=tool_name, success=False, error=message, error_type=error_type), True
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        last_result = result
        if result.success or result.error_type not in {"tool_exception", "tool_timeout"}:
            return result, False
    assert last_result is not None
    return last_result, False
