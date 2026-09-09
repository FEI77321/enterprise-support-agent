"""Agent 运行时治理：统一工具策略、步数限制与请求级 Trace。"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.tool_action_policy import get_tool_action_policy
from app.tool_registry import ToolResult, validate_tool_arguments, run_tool

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
        self, *, session: HarnessSession, tool_name: str, arguments: dict[str, Any], confirmed: bool = False
    ) -> HarnessExecutionResult:
        policy = get_tool_action_policy(tool_name)
        summary = _argument_summary(arguments)
        step_number = session.executed_steps + 1

        if session.executed_steps >= session.max_steps:
            session.trace_steps.append(HarnessTraceStep(
                step_number=step_number, tool_name=tool_name, risk_level=policy.risk_level,
                argument_summary=summary, status="max_steps_exceeded", error_type="max_steps_exceeded",
            ))
            return HarnessExecutionResult(status="max_steps_exceeded", reason="本次 Agent 工具执行已达到最大步数。")

        validation_error = validate_tool_arguments(tool_name, arguments)
        if validation_error is not None:
            session.trace_steps.append(HarnessTraceStep(
                step_number=step_number, tool_name=tool_name, risk_level=policy.risk_level,
                argument_summary=summary, status="blocked", error_type=validation_error.error_type,
            ))
            return HarnessExecutionResult(status="blocked", tool_result=validation_error, reason=validation_error.error)

        if policy.requires_confirmation and not confirmed:
            session.trace_steps.append(HarnessTraceStep(
                step_number=step_number, tool_name=tool_name, risk_level=policy.risk_level,
                argument_summary=summary, status="confirmation_required",
            ))
            return HarnessExecutionResult(
                status="confirmation_required", reason=policy.reason,
                requires_confirmation=True, confirmation_reason=policy.reason,
            )

        session.executed_steps += 1
        started_at = perf_counter()
        tool_result = run_tool(tool_name, **arguments)
        status: HarnessStatus = "completed" if tool_result.success else "failed"
        session.trace_steps.append(HarnessTraceStep(
            step_number=step_number, tool_name=tool_name, risk_level=policy.risk_level,
            argument_summary=summary, status=status,
            elapsed_ms=round((perf_counter() - started_at) * 1000, 2),
            error_type=tool_result.error_type,
        ))
        return HarnessExecutionResult(status=status, tool_result=tool_result, reason=tool_result.error)
