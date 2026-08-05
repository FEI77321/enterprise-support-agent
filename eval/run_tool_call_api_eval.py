# 模块职责：工具调用演示 API 评估：通过 HTTP 请求验证手动提供的工具调用 JSON 能被接口正常执行，并返回结构化错误。

from eval_path import setup_backend_path


setup_backend_path()

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_tool_call_demo_query_ticket() -> tuple[bool, str]:  # 测试函数：验证 工具 调用 demo 查询 工单 场景。
    response = client.post(
        "/tool-call/demo",
        json={
            "message": "帮我查询工单状态",
            "llm_output": (
                '{"tool_name": "query_ticket_status", '
                '"arguments": {"ticket_id": "NOT-EXISTS"}}'
            ),
        },
    )

    if response.status_code != 200:
        return False, f"期望状态码 200，实际为 {response.status_code}"

    data = response.json()

    if not data.get("success"):
        return False, f"期望 success=True，实际为 {data}"

    if data.get("tool_name") != "query_ticket_status":
        return False, f"期望调用 query_ticket_status，实际为 {data.get('tool_name')}"

    if "没有找到工单" not in (data.get("answer") or ""):
        return False, f"期望返回未找到工单提示，实际 answer={data.get('answer')}"

    return True, ""


def test_tool_call_demo_invalid_tool_call() -> tuple[bool, str]:  # 测试函数：验证 工具 调用 demo 非法 工具 调用 场景。
    response = client.post(
        "/tool-call/demo",
        json={
            "message": "帮我查询工单状态",
            "llm_output": (
                '{"tool_name": "query_ticket_status", '
                '"arguments": {}}'
            ),
        },
    )

    if response.status_code != 200:
        return False, f"期望状态码 200，实际为 {response.status_code}"

    data = response.json()

    if data.get("success"):
        return False, f"期望 success=False，实际为 {data}"

    if data.get("error_type") != "missing_arguments":
        return False, f"期望 error_type=missing_arguments，实际为 {data.get('error_type')}"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("tool_call_demo_query_ticket", test_tool_call_demo_query_ticket),
        ("tool_call_demo_invalid_tool_call", test_tool_call_demo_invalid_tool_call),
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
