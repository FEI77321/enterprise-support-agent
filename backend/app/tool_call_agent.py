# 模块职责：工具调用 Agent 编排模块：结合会话历史选择 Planner，解析模型给出的工具调用，执行工具，并把执行结果转换为用户可读的最终回答。

from pydantic import BaseModel, Field
import os
from app.tool_call_executor import execute_tool_call_text
from app.tool_prompt_builder import build_tool_selection_prompt
from app.tool_call_planner import (
    plan_tool_call_with_deepseek,
    plan_tool_call_with_deepseek_native,
    plan_tool_call_with_mock_llm,
    plan_tool_call_with_openai,
)
from app.conversation_memory import get_recent_turns
from app.tool_confirmation import save_pending_confirmation
from app.tool_confirmation import (
    clear_pending_confirmation,
    consume_pending_confirmation,
    get_confirmation_decision,
    get_pending_confirmation,
)
from app.tool_registry import list_openai_tools, run_tool
from app.agent_harness import AgentHarness, create_harness_session
from app.config import get_agent_harness_max_steps, is_agent_harness_enabled
from app.access_control import can_approve_high_risk, get_current_actor, record_approval_event

class InvalidToolCallProviderError(ValueError):  # 类：表示配置了系统不支持的工具调用 Planner Provider。
    pass


class ToolCallAgentResponse(BaseModel):  # 类：封装工具调用 Agent 的规划文本、执行状态、工具结果和最终回答。
    message: str
    llm_output: str
    success: bool
    workflow_steps: list[str]
    tool_name: str | None = None
    answer: str | None = None
    decision_type: str | None = None
    error_type: str | None = None
    error: str | None = None
    requires_confirmation: bool = False
    confirmation_reason: str | None = None
    pending_arguments: dict[str, object] | None = None
    operation_id: str | None = None
    confirmation_expires_at: str | None = None
    harness_trace: list[dict[str, object]] = Field(default_factory=list)




def build_planner_input(message: str, session_id: str | None) -> str:  # 函数：负责 构建 规划器 输入 相关逻辑。
    if not session_id:
        return message

    recent_turns = get_recent_turns(session_id)

    if not recent_turns:
        return message

    history_lines = [
        f"{turn.role}: {turn.content}"
        for turn in recent_turns
    ]

    history_text = "\n".join(history_lines)

    return (
        f"历史对话：\n{history_text}\n\n"
        f"当前用户消息：{message}"
    )



def plan_tool_call(message: str) -> tuple[str, str]:  # 函数：负责 plan 工具 调用 相关逻辑。
    provider = os.environ.get("TOOL_CALL_PROVIDER", "mock").lower() or "mock"

    if provider == "mock":
        return plan_tool_call_with_mock_llm(message), "mock"

    if provider == "openai":
        return plan_tool_call_with_openai(message), "openai"

    if provider == "deepseek":
        return plan_tool_call_with_deepseek(message), "deepseek"

    if provider == "deepseek_native":  # ← 新增分支
        return plan_tool_call_with_deepseek_native(message), "deepseek_native"

    raise InvalidToolCallProviderError(
        f"Unsupported TOOL_CALL_PROVIDER: {provider}"
    )


def handle_confirmation_reply(  # 函数：处理用户对待确认高风险工具操作的确认或取消回复。
    message: str,
    session_id: str | None,
) -> ToolCallAgentResponse | None:
    if not session_id:
        return None

    pending = get_pending_confirmation(session_id)

    if pending is None:
        return None

    decision = get_confirmation_decision(message)

    if decision is None:
        return None

    if decision == "cancel":
        clear_pending_confirmation(session_id)
        record_approval_event(pending.operation_id, session_id, get_current_actor().actor_id, "cancelled")
        return ToolCallAgentResponse(
            message=message,
            llm_output="",
            success=True,
            workflow_steps=[
                "confirmation_received",
                "confirmation_cancelled",
            ],
            tool_name=pending.tool_name,
            answer="已取消该操作，工单未被删除。",
            decision_type="confirmation_cancelled",
        )

    approval = can_approve_high_risk(get_current_actor())
    if not approval.allowed:
        record_approval_event(pending.operation_id, session_id, get_current_actor().actor_id, "rejected", approval.reason)
        return ToolCallAgentResponse(
            message=message, llm_output="", success=False,
            workflow_steps=["confirmation_received", "approver_authorization_denied"],
            tool_name=pending.tool_name, decision_type="confirmation_rejected",
            error_type="approver_authorization_denied",
            error="高风险操作必须由管理员审批。",
        )

    consumed = consume_pending_confirmation(session_id, pending.operation_id)
    if consumed is None:
        return ToolCallAgentResponse(
            message=message, llm_output="", success=False,
            workflow_steps=["confirmation_received", "confirmation_invalid_or_expired"],
            tool_name=pending.tool_name, decision_type="confirmation_rejected",
            error_type="approval_invalid_or_expired",
            error="该审批已过期、被消费或与当前会话不匹配，请重新发起操作。",
        )
    record_approval_event(pending.operation_id, session_id, get_current_actor().actor_id, "approved")

    harness_trace: list[dict[str, object]] = []
    if is_agent_harness_enabled():
        session = create_harness_session(
            request_id=session_id,
            engine="tool_call",
            max_steps=get_agent_harness_max_steps(),
        )
        harness_result = AgentHarness().execute_tool(
            session=session,
            tool_name=pending.tool_name,
            arguments=pending.arguments,
            confirmed=True,
        )
        tool_result = harness_result.tool_result
        harness_trace = [step.model_dump() for step in session.trace_steps]
        if tool_result is None:
            from app.tool_registry import ToolResult
            tool_result = ToolResult(
                tool_name=pending.tool_name,
                success=False,
                error=harness_result.reason or "Harness blocked confirmed tool execution",
                error_type=harness_result.status,
            )
    else:
        tool_result = run_tool(pending.tool_name, **pending.arguments)

    if not tool_result.success:
        return ToolCallAgentResponse(
            message=message,
            llm_output="",
            success=False,
            workflow_steps=[
                "confirmation_received",
                "execute_confirmed_tool_call",
                "confirmed_tool_call_failed",
            ],
            tool_name=pending.tool_name,
            decision_type="confirmed_tool_call",
            error_type=tool_result.error_type,
            error=tool_result.error,
            harness_trace=harness_trace,
        )

    data = tool_result.data or {}

    if pending.tool_name == "delete_ticket":
        ticket_id = data.get("ticket_id")

        if data.get("deleted"):
            answer = f"已确认并删除工单 {ticket_id}。"
        else:
            answer = f"未找到工单 {ticket_id}，无需删除。"
    else:
        answer = f"已确认并执行工具 {pending.tool_name}。"

    return ToolCallAgentResponse(
        message=message,
        llm_output="",
        success=True,
        workflow_steps=[
            "confirmation_received",
            "execute_confirmed_tool_call",
            "confirmed_tool_call_completed",
        ],
        tool_name=pending.tool_name,
        answer=answer,
        decision_type="confirmed_tool_call",
        harness_trace=harness_trace,
    )


def handle_tool_call_demo_auto(
    message: str,
    session_id: str | None = None,
) -> ToolCallAgentResponse:
    # 函数：负责 处理 工具 调用 demo 自动 相关逻辑。
    confirmation_response = handle_confirmation_reply(
        message=message,
        session_id=session_id,
    )

    if confirmation_response is not None:
        return confirmation_response
    try:
        planner_input = build_planner_input(
            message=message,
            session_id=session_id,
        )

        llm_output, provider = plan_tool_call(planner_input)
    except InvalidToolCallProviderError as exc:
        return ToolCallAgentResponse(
            message=message,
            llm_output="",
            success=False,
            workflow_steps=["plan_tool_call_failed"],
            decision_type=None,
            error_type="invalid_tool_call_provider",
            error=str(exc),
        )

    response = handle_tool_call_demo(
        message=message,
        llm_output=llm_output,
        session_id=session_id,
    )

    response.workflow_steps.insert(0, f"plan_tool_call:{provider}")

    return response



def handle_tool_call_demo(
    message: str,
    llm_output: str,
    session_id: str | None = None,
) -> ToolCallAgentResponse:  # 函数：负责 处理 工具 调用 demo 相关逻辑。
    workflow_steps: list[str] = []

    tools = list_openai_tools()
    _ = build_tool_selection_prompt(message, tools)
    workflow_steps.append("build_tool_selection_prompt")

    execution = execute_tool_call_text(llm_output)
    workflow_steps.append("parse_tool_call")

    if execution.error_type == "no_tool":
        workflow_steps.append("no_tool_selected")
        return ToolCallAgentResponse(
            message=message,
            llm_output=llm_output,
            success=True,
            workflow_steps=workflow_steps,
            tool_name=None,
            answer="当前不需要调用工具。",
            decision_type="no_tool",
            error_type=None,
        )

    if execution.requires_confirmation:
        workflow_steps.append("await_user_confirmation")

        ticket_id = execution.arguments.get("ticket_id")

        if isinstance(ticket_id, str):
            target = f"工单 {ticket_id}"
        else:
            target = "该操作"

        reason = execution.confirmation_reason or "该操作需要用户确认。"

        pending = None
        if session_id:
            pending = save_pending_confirmation(
                session_id=session_id,
                tool_name=execution.tool_name or "",
                arguments=execution.arguments,
                reason=reason,
            )

        return ToolCallAgentResponse(
            message=message,
            llm_output=llm_output,
            success=True,
            workflow_steps=workflow_steps,
            tool_name=execution.tool_name,
            answer=(f"{reason} 是否确认执行：删除{target}？" if pending is None else f"{reason} 是否确认执行：删除{target}？操作编号 {pending.operation_id}，5 分钟内有效。"),
            decision_type="confirmation_required",
            requires_confirmation=True,
            confirmation_reason=reason,
            pending_arguments=execution.arguments,
            operation_id=pending.operation_id if pending else None,
            confirmation_expires_at=pending.expires_at if pending else None,
            harness_trace=execution.harness_trace,
        )


    if not execution.success:
        workflow_steps.append("tool_call_failed")
        return ToolCallAgentResponse(
            message=message,
            llm_output=llm_output,
            success=False,
            workflow_steps=workflow_steps,
            tool_name=execution.tool_name,
            decision_type="tool_call",
            error_type=execution.error_type,
            error=execution.error,
            harness_trace=execution.harness_trace,
        )

    workflow_steps.append("execute_tool_call")

    answer = build_tool_call_answer(execution)
    workflow_steps.append("tool_call_completed")

    return ToolCallAgentResponse(
        message=message,
        llm_output=llm_output,
        success=True,
        workflow_steps=workflow_steps,
        tool_name=execution.tool_name,
        answer=answer,
        decision_type="tool_call",
        harness_trace=execution.harness_trace,
    )


def build_tool_call_answer(execution) -> str:  # 函数：负责 构建 工具 调用 回答 相关逻辑。
    if execution.tool_result is None:
        return "工具未返回结果。"

    data = execution.tool_result.data or {}

    if execution.tool_name == "query_ticket_status":
        if data.get("found"):
            ticket = data.get("ticket", {})
            return (
                f"工单 {ticket.get('ticket_id')} 当前状态为 "
                f"{ticket.get('status')}，处理人为 {ticket.get('assignee')}。"
            )

        return f"没有找到工单 {data.get('ticket_id')}。"

    if execution.tool_name == "create_ticket":
        ticket = data.get("ticket", {})
        return (
            f"已创建工单 {ticket.get('ticket_id')}，"
            f"优先级为 {ticket.get('priority')}，"
            f"当前状态为 {ticket.get('status')}。"
        )

    if execution.tool_name in {"search_knowledge_base", "search_vector_store"}:
        results = data.get("results", [])
        if not results:
            return "没有检索到相关知识库内容。"

        first_result = results[0]
        return (
            f"检索到相关知识片段：{first_result.get('file')} "
            f"({first_result.get('chunk_id')})。"
        )

    return "工具已执行完成。"
