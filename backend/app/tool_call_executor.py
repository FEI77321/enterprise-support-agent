# 模块职责：工具调用执行模块：把模型输出的 JSON 依次经过解析、参数校验和工具注册表执行，返回包含成功状态、错误类型和工具结果的统一对象。

from typing import Any

from pydantic import BaseModel, Field

from app.tool_call_parser import parse_and_validate_tool_call
from app.tool_registry import ToolResult, run_tool
from app.tool_action_policy import get_tool_action_policy
from app.agent_harness import AgentHarness, HarnessSession, create_harness_session
from app.config import get_agent_harness_max_steps, is_agent_harness_enabled
from app.observability import get_request_id

class ToolCallExecutionResult(BaseModel):  # 类：封装工具调用从解析到执行后的统一结果。
    success: bool
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    tool_result: ToolResult | None = None
    error_type: str | None = None
    error: str | None = None
    requires_confirmation: bool = False
    confirmation_reason: str | None = None
    harness_trace: list[dict[str, Any]] = Field(default_factory=list)


def execute_tool_call_text(
    text: str,
    *,
    session: HarnessSession | None = None,
) -> ToolCallExecutionResult:  # 函数：负责 执行 工具 调用 文本 相关逻辑。
    parsed = parse_and_validate_tool_call(text)

    if not parsed.success:
        return ToolCallExecutionResult(
            success=False,
            tool_name=parsed.tool_name,
            arguments=parsed.arguments,
            error_type=parsed.error_type,
            error=parsed.error,
        )

    if parsed.tool_name is None:
        return ToolCallExecutionResult(
            success=True,
            tool_name=None,
            arguments=parsed.arguments,
            error_type="no_tool",
        )

    if is_agent_harness_enabled():
        current_request_id = get_request_id()
        active_session = session or create_harness_session(
            request_id=current_request_id if current_request_id != "-" else None,
            engine="tool_call",
            max_steps=get_agent_harness_max_steps(),
        )
        harness_result = AgentHarness().execute_tool(
            session=active_session,
            tool_name=parsed.tool_name,
            arguments=parsed.arguments,
        )
        return ToolCallExecutionResult(
            success=harness_result.status == "completed",
            tool_name=parsed.tool_name,
            arguments=parsed.arguments,
            tool_result=harness_result.tool_result,
            error_type=(
                None if harness_result.status == "completed"
                else (harness_result.tool_result.error_type if harness_result.tool_result else harness_result.status)
            ),
            error=harness_result.reason,
            requires_confirmation=harness_result.requires_confirmation,
            confirmation_reason=harness_result.confirmation_reason,
            harness_trace=[step.model_dump() for step in active_session.trace_steps],
        )

    policy = get_tool_action_policy(parsed.tool_name)

    if policy.requires_confirmation:
        return ToolCallExecutionResult(
            success=False,
            tool_name=parsed.tool_name,
            arguments=parsed.arguments,
            error_type="confirmation_required",
            error=policy.reason,
            requires_confirmation=True,
            confirmation_reason=policy.reason,
        )


    tool_result = run_tool(parsed.tool_name, **parsed.arguments)

    return ToolCallExecutionResult(
        success=tool_result.success,
        tool_name=parsed.tool_name,
        arguments=parsed.arguments,
        tool_result=tool_result,
        error_type=tool_result.error_type,
        error=tool_result.error,
    )
