# 模块职责：工具调用 Agent 单元评估：覆盖工单不存在、参数缺失和无需工具等决策分支，验证 Agent 对执行结果的整理方式。

from eval_path import setup_backend_path


setup_backend_path()

from app.tool_call_agent import (
    handle_tool_call_demo,
    handle_tool_call_demo_auto,
)

from app.tool_confirmation import (
    clear_pending_confirmation,
    get_pending_confirmation,
    save_pending_confirmation,
)

from app.tool_registry import run_tool
from app.tools import delete_ticket


def test_confirmed_delete_ticket_is_executed() -> tuple[bool, str]:  # 测试函数：验证用户确认后，待确认的删除工单操作会被真正执行并清除待确认记录。
    session_id = "test-confirmed-delete-ticket"
    clear_pending_confirmation(session_id)

    created = run_tool(
        "create_ticket",
        message="用于测试确认删除流程的临时工单",
    )

    if not created.success:
        return False, f"创建测试工单失败，实际为 {created}"

    ticket = (created.data or {}).get("ticket") or {}
    ticket_id = ticket.get("ticket_id")

    if not isinstance(ticket_id, str):
        return False, f"期望获得测试工单号，实际为 {ticket_id}"

    save_pending_confirmation(
        session_id=session_id,
        tool_name="delete_ticket",
        arguments={
            "ticket_id": ticket_id,
        },
        reason="删除工单会永久移除数据，需要用户确认。",
    )

    try:
        response = handle_tool_call_demo_auto(
            message="确认删除",
            session_id=session_id,
        )

        if not response.success:
            return False, f"期望确认后执行成功，实际为 {response}"

        if response.decision_type != "confirmed_tool_call":
            return False, (
                "期望 decision_type=confirmed_tool_call，"
                f"实际为 {response.decision_type}"
            )

        if "已确认并删除工单" not in (response.answer or ""):
            return False, f"期望返回删除成功提示，实际为 {response.answer}"

        pending = get_pending_confirmation(session_id)

        if pending is not None:
            return False, f"期望确认后清除待确认操作，实际为 {pending}"

        queried = run_tool(
            "query_ticket_status",
            ticket_id=ticket_id,
        )

        if (queried.data or {}).get("found"):
            return False, "期望确认后工单已被删除，但查询结果仍显示存在"

        return True, ""
    finally:
        delete_ticket(ticket_id)


def test_tool_call_confirmation_is_saved_to_session() -> tuple[bool, str]:  # 测试函数：验证高风险工具调用会把待确认操作保存到对应会话。
    session_id = "test-agent-confirmation-session"

    clear_pending_confirmation(session_id)

    response = handle_tool_call_demo(
        message="删除工单 TICKET-20260724-0001",
        llm_output=(
            '{"tool_name": "delete_ticket", '
            '"arguments": {"ticket_id": "TICKET-20260724-0001"}}'
        ),
        session_id=session_id,
    )

    if not response.requires_confirmation:
        return False, "期望 Agent 返回 requires_confirmation=True"

    pending = get_pending_confirmation(session_id)

    if pending is None:
        return False, "期望待确认操作已保存到 session，实际为 None"

    if pending.tool_name != "delete_ticket":
        return False, f"期望待确认工具为 delete_ticket，实际为 {pending.tool_name}"

    if pending.arguments.get("ticket_id") != "TICKET-20260724-0001":
        return False, f"期望保存待删除工单号，实际为 {pending.arguments}"

    return True, ""


def test_tool_call_demo_requires_confirmation() -> tuple[bool, str]:  # 测试函数：验证高风险删除工单操作会返回用户确认提示，而不是直接执行。
    response = handle_tool_call_demo(
        message="删除工单 TICKET-20260724-0001",
        llm_output=(
            '{"tool_name": "delete_ticket", '
            '"arguments": {"ticket_id": "TICKET-20260724-0001"}}'
        ),
    )

    if not response.success:
        return False, f"期望 Agent 正常返回确认请求，实际为 {response}"

    if response.decision_type != "confirmation_required":
        return False, (
            "期望 decision_type=confirmation_required，"
            f"实际为 {response.decision_type}"
        )

    if not response.requires_confirmation:
        return False, "期望 requires_confirmation=True"

    if response.tool_name != "delete_ticket":
        return False, f"期望 tool_name=delete_ticket，实际为 {response.tool_name}"

    if "确认" not in (response.answer or ""):
        return False, f"期望 answer 包含确认提示，实际为 {response.answer}"

    return True, ""




def test_tool_call_demo_query_ticket_not_found() -> tuple[bool, str]:  # 测试函数：验证 工具 调用 demo 查询 工单 不 存在 场景。
    response = handle_tool_call_demo(
        message="帮我查一下 TICKET-20990101-9999",
        llm_output='{"tool_name": "query_ticket_status", "arguments": {"ticket_id": "TICKET-20990101-9999"}}',
    )

    if not response.success:
        return False, f"期望 tool call demo 成功，实际 error={response.error}"

    if response.tool_name != "query_ticket_status":
        return False, f"期望 tool_name=query_ticket_status，实际为 {response.tool_name}"

    if "没有找到工单" not in (response.answer or ""):
        return False, f"期望回答包含没有找到工单，实际 answer={response.answer}"

    expected_steps = [
        "build_tool_selection_prompt",
        "parse_tool_call",
        "execute_tool_call",
        "tool_call_completed",
    ]

    for step in expected_steps:
        if step not in response.workflow_steps:
            return False, f"workflow_steps 缺少 {step}: {response.workflow_steps}"

    return True, ""


def test_tool_call_demo_missing_arguments() -> tuple[bool, str]:  # 测试函数：验证 工具 调用 demo 缺少 参数 场景。
    response = handle_tool_call_demo(
        message="帮我查一下工单",
        llm_output='{"tool_name": "query_ticket_status", "arguments": {}}',
    )

    if response.success:
        return False, "期望缺少参数时 demo 失败"

    if response.error_type != "missing_arguments":
        return False, f"期望 error_type=missing_arguments，实际为 {response.error_type}"

    if "tool_call_failed" not in response.workflow_steps:
        return False, f"期望 workflow_steps 包含 tool_call_failed，实际为 {response.workflow_steps}"

    return True, ""


def test_tool_call_demo_no_tool() -> tuple[bool, str]:  # 测试函数：验证 工具 调用 demo 无 工具 场景。
    response = handle_tool_call_demo(
        message="你好",
        llm_output='{"tool_name": null, "arguments": {}}',
    )

    if not response.success:
        return False, f"期望 no_tool 场景成功，实际 error={response.error}"

    if response.decision_type != "no_tool":
        return False, f"期望 error_type=no_tool，实际为 {response.error_type}"

    if response.error_type is not None:
        return False, f"期望 error_type=None，实际为 {response.error_type}"

    if response.tool_name is not None:
        return False, f"期望 tool_name=None，实际为 {response.tool_name}"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        (
            "tool_call_demo_query_ticket_not_found",
            test_tool_call_demo_query_ticket_not_found
        ),
        (
            "tool_call_demo_missing_arguments",
            test_tool_call_demo_missing_arguments
        ),
        (
            "tool_call_demo_no_tool",
            test_tool_call_demo_no_tool
        ),
        (
            "tool_call_confirmation_is_saved_to_session",
            test_tool_call_confirmation_is_saved_to_session,
        ),
        (
            "confirmed_delete_ticket_is_executed",
            test_confirmed_delete_ticket_is_executed,
        ),
    ]

    passed = 0

    for name, test_func in tests:
        ok, reason = test_func()
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}")

        if ok:
            passed += 1
        else:
            print(f"  Reason: {reason}")

    print()
    print(f"Passed: {passed}/{len(tests)}")

    if passed != len(tests):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
