# 模块职责：工具调用执行器评估：验证从 JSON 文本到解析、校验、工具运行和错误归类的完整执行链路。

from eval_path import setup_backend_path
import json
setup_backend_path()

from app.tool_call_executor import execute_tool_call_text

from app.tool_registry import run_tool
from app.tools import delete_ticket
def test_execute_known_tool() -> tuple[bool, str]:  # 测试函数：验证 执行 已知 工具 场景。
    result = execute_tool_call_text(
        '{"tool_name": "query_ticket_status", "arguments": {"ticket_id": "TICKET-20990101-9999"}}'
    )

    if not result.success:
        return False, f"期望工具执行链路成功，实际 error={result.error}"

    if result.tool_name != "query_ticket_status":
        return False, f"期望 tool_name=query_ticket_status，实际为 {result.tool_name}"

    if result.tool_result is None:
        return False, "期望返回 tool_result"

    if result.tool_result.data is None:
        return False, "期望 tool_result.data 非空"

    if result.tool_result.data.get("found") is not False:
        return False, f"期望未找到工单 found=False，实际 data={result.tool_result.data}"

    return True, ""


def test_execute_no_tool() -> tuple[bool, str]:  # 测试函数：验证 执行 无 工具 场景。
    result = execute_tool_call_text('{"tool_name": null, "arguments": {}}')

    if not result.success:
        return False, f"期望 no tool 场景 success=True，实际 error={result.error}"

    if result.tool_name is not None:
        return False, f"期望 tool_name=None，实际为 {result.tool_name}"

    if result.error_type != "no_tool":
        return False, f"期望 error_type=no_tool，实际为 {result.error_type}"

    if result.tool_result is not None:
        return False, f"期望 no tool 场景没有 tool_result，实际为 {result.tool_result}"

    return True, ""


def test_execute_invalid_json() -> tuple[bool, str]:  # 测试函数：验证 执行 非法 json 场景。
    result = execute_tool_call_text("not json")

    if result.success:
        return False, "期望 invalid json 执行失败"

    if result.error_type != "invalid_json":
        return False, f"期望 error_type=invalid_json，实际为 {result.error_type}"

    return True, ""


def test_execute_missing_arguments() -> tuple[bool, str]:  # 测试函数：验证 执行 缺少 参数 场景。
    result = execute_tool_call_text(
        '{"tool_name": "query_ticket_status", "arguments": {}}'
    )

    if result.success:
        return False, "期望缺少参数时执行失败"

    if result.error_type != "missing_arguments":
        return False, f"期望 error_type=missing_arguments，实际为 {result.error_type}"

    return True, ""

def test_delete_ticket_requires_confirmation() -> tuple[bool, str]:  # 测试函数：验证删除工单的工具调用会被确认策略拦截，且不会真的删除工单。
    created = run_tool(
        "create_ticket",
        message="用于测试删除确认流程的临时工单",
    )

    if not created.success:
        return False, f"创建测试工单失败，实际为 {created}"

    ticket = (created.data or {}).get("ticket") or {}
    ticket_id = ticket.get("ticket_id")

    if not ticket_id:
        return False, f"创建测试工单后未获得 ticket_id，实际为 {created.data}"

    try:
        result = execute_tool_call_text(
            json.dumps(
                {
                    "tool_name": "delete_ticket",
                    "arguments": {
                        "ticket_id": ticket_id,
                    },
                },
                ensure_ascii=False,
            )
        )

        if result.success:
            return False, "期望删除操作等待确认，实际却直接执行成功"

        if not result.requires_confirmation:
            return False, "期望 requires_confirmation=True"

        if result.error_type != "confirmation_required":
            return False, (
                "期望 error_type=confirmation_required，"
                f"实际为 {result.error_type}"
            )

        queried = run_tool(
            "query_ticket_status",
            ticket_id=ticket_id,
        )

        if not queried.success:
            return False, f"查询测试工单失败，实际为 {queried}"

        if not (queried.data or {}).get("found"):
            return False, "删除操作被拦截后，工单仍应存在"

        return True, ""
    finally:
        delete_ticket(ticket_id)



def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("execute_known_tool", test_execute_known_tool),
        ("execute_no_tool", test_execute_no_tool),
        ("execute_invalid_json", test_execute_invalid_json),
        ("execute_missing_arguments", test_execute_missing_arguments),
        ("delete_ticket_requires_confirmation",test_delete_ticket_requires_confirmation,),
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
