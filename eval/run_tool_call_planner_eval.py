# 模块职责：Mock Planner 评估：验证规则式 Planner 面对查工单、创建工单、检索知识库和普通闲聊时生成正确的 JSON 工具计划。

import json

from eval_path import setup_backend_path

setup_backend_path()

from app.tool_call_planner import plan_tool_call_with_mock_llm

def test_plan_delete_ticket() -> tuple[bool, str]:  # 测试函数：验证 Planner 能识别删除工单意图并生成 delete_ticket 调用。
    data = parse_plan("删除工单 TICKET-20260724-0001")

    if data.get("tool_name") != "delete_ticket":
        return False, f"期望 tool_name=delete_ticket，实际为 {data.get('tool_name')}"

    arguments = data.get("arguments") or {}

    if arguments.get("ticket_id") != "TICKET-20260724-0001":
        return False, f"期望解析删除目标工单号，实际为 {arguments}"

    return True, ""

def parse_plan(message: str) -> dict:  # 函数：负责 解析 plan 相关逻辑。
    llm_output = plan_tool_call_with_mock_llm(message)

    try:
        data = json.loads(llm_output)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"planner 返回的不是合法 JSON: {llm_output}") from exc

    if not isinstance(data, dict):
        raise AssertionError(f"planner 返回 JSON 后不是字典: {data}")

    return data


def test_plan_query_ticket() -> tuple[bool, str]:  # 测试函数：验证 plan 查询 工单 场景。
    data = parse_plan("帮我查询工单 TICKET-20260724-0001 的状态")

    if data.get("tool_name") != "query_ticket_status":
        return False, f"期望 tool_name=query_ticket_status，实际为 {data.get('tool_name')}"

    arguments = data.get("arguments")

    if not isinstance(arguments, dict):
        return False, f"期望 arguments 是字典，实际为 {arguments}"

    if arguments.get("ticket_id") != "TICKET-20260724-0001":
        return False, f"期望 ticket_id 正确，实际 arguments={arguments}"

    return True, ""


def test_plan_create_ticket() -> tuple[bool, str]:  # 测试函数：验证 plan 创建 工单 场景。
    message = "创建工单：VPN 登录失败，用户无法连接公司网络"
    data = parse_plan(message)

    if data.get("tool_name") != "create_ticket":
        return False, f"期望 tool_name=create_ticket，实际为 {data.get('tool_name')}"

    arguments = data.get("arguments")

    if not isinstance(arguments, dict):
        return False, f"期望 arguments 是字典，实际为 {arguments}"

    if arguments.get("message") != message:
        return False, f"期望 arguments.message={message}，实际为 {arguments.get('message')}"

    unexpected_keys = {"title", "description", "priority"} & set(arguments.keys())

    if unexpected_keys:
        return False, f"create_ticket 不应生成这些旧参数: {sorted(unexpected_keys)}"

    return True, ""


def test_plan_search_knowledge_base() -> tuple[bool, str]:  # 测试函数：验证 plan 检索 知识 库 场景。
    message = "VPN 720 错误怎么办"
    data = parse_plan(message)

    if data.get("tool_name") != "search_knowledge_base":
        return False, f"期望 tool_name=search_knowledge_base，实际为 {data.get('tool_name')}"

    arguments = data.get("arguments")

    if not isinstance(arguments, dict):
        return False, f"期望 arguments 是字典，实际为 {arguments}"

    if arguments.get("query") != message:
        return False, f"期望 query={message}，实际为 {arguments.get('query')}"

    if arguments.get("top_k") != 3:
        return False, f"期望 top_k=3，实际为 {arguments.get('top_k')}"

    return True, ""


def test_plan_no_tool() -> tuple[bool, str]:  # 测试函数：验证 plan 无 工具 场景。
    data = parse_plan("你好")

    if data.get("tool_name") is not None:
        return False, f"期望 tool_name=None，实际为 {data.get('tool_name')}"

    if data.get("arguments") != {}:
        return False, f"期望 arguments 为空字典，实际为 {data.get('arguments')}"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("plan_query_ticket", test_plan_query_ticket),
        ("plan_create_ticket", test_plan_create_ticket),
        ("plan_search_knowledge_base", test_plan_search_knowledge_base),
        ("plan_no_tool", test_plan_no_tool),
        (
            "plan_delete_ticket",
            test_plan_delete_ticket,
        ),
    ]

    passed = 0

    for name, test_func in tests:
        try:
            ok, reason = test_func()
        except Exception as exc:
            ok = False
            reason = str(exc)

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
