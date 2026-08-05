# 模块职责：验证工具风险策略能正确识别需要人工确认和可直接执行的工具。

from eval_path import setup_backend_path


setup_backend_path()

from app.tool_action_policy import get_tool_action_policy


def test_delete_ticket_requires_confirmation() -> tuple[bool, str]:  # 测试函数：验证删除工单前必须要求用户确认。
    policy = get_tool_action_policy("delete_ticket")

    if not policy.requires_confirmation:
        return False, "期望 delete_ticket 需要用户确认"

    if not policy.reason:
        return False, "期望 delete_ticket 返回需要确认的原因"

    return True, ""


def test_query_ticket_status_does_not_require_confirmation() -> tuple[bool, str]:  # 测试函数：验证查询工单状态可以直接执行。
    policy = get_tool_action_policy("query_ticket_status")

    if policy.requires_confirmation:
        return False, "期望 query_ticket_status 不需要用户确认"

    if policy.reason is not None:
        return False, f"期望无需确认时 reason=None，实际为 {policy.reason}"

    return True, ""


def main() -> None:  # 函数：运行本文件中的全部工具风险策略评估。
    tests = [
        (
            "delete_ticket_requires_confirmation",
            test_delete_ticket_requires_confirmation,
        ),
        (
            "query_ticket_status_does_not_require_confirmation",
            test_query_ticket_status_does_not_require_confirmation,
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