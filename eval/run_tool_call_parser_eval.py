# 模块职责：工具调用解析器评估：覆盖合法调用、无需工具、非法 JSON、错误工具名、错误参数与缺失参数，验证输出校验边界。

from eval_path import setup_backend_path


setup_backend_path()

from app.tool_call_parser import (
    parse_and_validate_tool_call,
    parse_tool_call,
    validate_tool_call,
)


def test_validate_missing_arguments() -> tuple[bool, str]:  # 测试函数：验证 校验 缺少 参数 场景。
    result = parse_and_validate_tool_call(
        '{"tool_name": "query_ticket_status", "arguments": {}}'
    )

    if result.success:
        return False, "期望缺少必需参数时校验失败"

    if result.error_type != "missing_arguments":
        return False, f"期望 error_type=missing_arguments，实际为 {result.error_type}"

    if "ticket_id" not in (result.error or ""):
        return False, f"期望 error 包含 ticket_id，实际为 {result.error}"

    return True, ""


def test_validate_optional_top_k() -> tuple[bool, str]:  # 测试函数：验证 校验 可选 top k 场景。
    result = parse_and_validate_tool_call(
        '{"tool_name": "search_knowledge_base", "arguments": {"query": "VPN 720 错误怎么办"}}'
    )

    if not result.success:
        return False, f"期望 top_k 缺失时仍校验成功，实际 error={result.error}"

    if result.tool_name != "search_knowledge_base":
        return False, f"期望 tool_name=search_knowledge_base，实际为 {result.tool_name}"

    if result.arguments.get("query") != "VPN 720 错误怎么办":
        return False, f"期望保留 query 参数，实际为 {result.arguments}"

    return True, ""




def test_validate_unknown_tool() -> tuple[bool, str]:  # 测试函数：验证 校验 未知 工具 场景。
    result = parse_and_validate_tool_call(
        '{"tool_name": "delete_company_database", "arguments": {}}'
    )

    if result.success:
        return False, "期望未知工具校验失败"

    if result.error_type != "unknown_tool":
        return False, f"期望 error_type=unknown_tool，实际为 {result.error_type}"

    if result.tool_name != "delete_company_database":
        return False, f"期望保留原始 tool_name，实际为 {result.tool_name}"

    return True, ""


def test_validate_known_tool() -> tuple[bool, str]:  # 测试函数：验证 校验 已知 工具 场景。
    result = parse_and_validate_tool_call(
        '{"tool_name": "query_ticket_status", "arguments": {"ticket_id": "TICKET-20260724-0001"}}'
    )

    if not result.success:
        return False, f"期望已注册工具校验成功，实际 error={result.error}"

    if result.tool_name != "query_ticket_status":
        return False, f"期望 tool_name=query_ticket_status，实际为 {result.tool_name}"

    return True, ""


def test_parse_valid_tool_call() -> tuple[bool, str]:  # 测试函数：验证 解析 合法 工具 调用 场景。
    result = parse_tool_call(
        '{"tool_name": "query_ticket_status", "arguments": {"ticket_id": "TICKET-20260724-0001"}}'
    )

    if not result.success:
        return False, f"期望解析成功，实际 error={result.error}"

    if result.tool_name != "query_ticket_status":
        return False, f"期望 tool_name=query_ticket_status，实际为 {result.tool_name}"

    if result.arguments.get("ticket_id") != "TICKET-20260724-0001":
        return False, f"期望解析 ticket_id，实际 arguments={result.arguments}"

    return True, ""


def test_parse_no_tool_call() -> tuple[bool, str]:  # 测试函数：验证 解析 无 工具 调用 场景。
    result = parse_tool_call('{"tool_name": null, "arguments": {}}')

    if not result.success:
        return False, f"期望解析成功，实际 error={result.error}"

    if result.tool_name is not None:
        return False, f"期望 tool_name=None，实际为 {result.tool_name}"

    if result.arguments != {}:
        return False, f"期望 arguments 为空字典，实际为 {result.arguments}"

    return True, ""


def test_parse_invalid_json() -> tuple[bool, str]:  # 测试函数：验证 解析 非法 json 场景。
    result = parse_tool_call("not json")

    if result.success:
        return False, "期望 invalid json 解析失败"

    if result.error_type != "invalid_json":
        return False, f"期望 error_type=invalid_json，实际为 {result.error_type}"

    return True, ""


def test_parse_invalid_tool_name() -> tuple[bool, str]:  # 测试函数：验证 解析 非法 工具 name 场景。
    result = parse_tool_call('{"tool_name": 123, "arguments": {}}')

    if result.success:
        return False, "期望 tool_name 类型错误时解析失败"

    if result.error_type != "invalid_tool_name":
        return False, f"期望 error_type=invalid_tool_name，实际为 {result.error_type}"

    return True, ""


def test_parse_invalid_arguments() -> tuple[bool, str]:  # 测试函数：验证 解析 非法 参数 场景。
    result = parse_tool_call('{"tool_name": "query_ticket_status", "arguments": "bad"}')

    if result.success:
        return False, "期望 arguments 类型错误时解析失败"

    if result.error_type != "invalid_arguments":
        return False, f"期望 error_type=invalid_arguments，实际为 {result.error_type}"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("parse_valid_tool_call", test_parse_valid_tool_call),
        ("parse_no_tool_call", test_parse_no_tool_call),
        ("parse_invalid_json", test_parse_invalid_json),
        ("parse_invalid_tool_name", test_parse_invalid_tool_name),
        ("parse_invalid_arguments", test_parse_invalid_arguments),
        ("validate_unknown_tool", test_validate_unknown_tool),
        ("validate_known_tool", test_validate_known_tool),
        ("validate_missing_arguments", test_validate_missing_arguments),
        ("validate_optional_top_k", test_validate_optional_top_k),
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
