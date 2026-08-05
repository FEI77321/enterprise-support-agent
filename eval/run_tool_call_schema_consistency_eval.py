# 模块职责：Planner 与工具 schema 一致性评估：比较 Planner 输出参数和注册工具参数，防止两处定义漂移导致运行时缺参或多传参数。

import json

from eval_path import setup_backend_path


setup_backend_path()

from app.tool_call_planner import plan_tool_call_with_mock_llm
from app.tool_registry import TOOL_REGISTRY

def test_delete_ticket_schema_consistency() -> tuple[bool, str]:  # 测试函数：验证删除工单 Planner 输出的参数与 delete_ticket 工具 schema 一致。
    return check_planner_matches_tool_schema(
        "删除工单 TICKET-20260724-0001"
    )


def load_planner_output(message: str) -> tuple[bool, str, dict]:  # 函数：负责 加载 规划器 输出 相关逻辑。
    llm_output = plan_tool_call_with_mock_llm(message)

    try:
        data = json.loads(llm_output)
    except json.JSONDecodeError:
        return False, f"planner 返回非法 JSON: {llm_output}", {}

    if not isinstance(data, dict):
        return False, f"planner 返回结果不是字典: {data}", {}

    arguments = data.get("arguments")

    if not isinstance(arguments, dict):
        return False, f"planner arguments 不是字典: {arguments}", {}

    return True, "", data


def check_planner_matches_tool_schema(message: str) -> tuple[bool, str]:  # 函数：负责 check 规划器 匹配 工具 schema 相关逻辑。
    ok, reason, data = load_planner_output(message)

    if not ok:
        return ok, reason

    tool_name = data.get("tool_name")

    if tool_name is None:
        return True, ""

    if not isinstance(tool_name, str):
        return False, f"tool_name 必须是字符串或 None，实际为 {tool_name}"

    tool = TOOL_REGISTRY.get(tool_name)

    if tool is None:
        return False, f"planner 生成了不存在的工具: {tool_name}"

    arguments = data["arguments"]
    allowed_parameters = set(tool.parameters.keys())
    actual_parameters = set(arguments.keys())

    unknown_parameters = actual_parameters - allowed_parameters

    if unknown_parameters:
        return False, (
            f"工具 {tool_name} 出现未声明参数: {sorted(unknown_parameters)}，"
            f"允许参数: {sorted(allowed_parameters)}"
        )

    missing_parameters = allowed_parameters - actual_parameters

    if missing_parameters:
        return False, (
            f"工具 {tool_name} 缺少参数: {sorted(missing_parameters)}，"
            f"实际参数: {sorted(actual_parameters)}"
        )

    return True, ""


def test_create_ticket_schema_consistency() -> tuple[bool, str]:  # 测试函数：验证 创建 工单 schema 一致性 场景。
    return check_planner_matches_tool_schema(
        "创建工单：VPN 登录失败，用户无法连接公司网络"
    )


def test_query_ticket_schema_consistency() -> tuple[bool, str]:  # 测试函数：验证 查询 工单 schema 一致性 场景。
    return check_planner_matches_tool_schema(
        "帮我查询工单 TICKET-20260724-0001 的状态"
    )


def test_search_knowledge_base_schema_consistency() -> tuple[bool, str]:  # 测试函数：验证 检索 知识 库 schema 一致性 场景。
    return check_planner_matches_tool_schema("VPN 720 错误怎么办")


def test_no_tool_schema_consistency() -> tuple[bool, str]:  # 测试函数：验证 无 工具 schema 一致性 场景。
    return check_planner_matches_tool_schema("你好")


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("create_ticket_schema_consistency", test_create_ticket_schema_consistency),
        ("query_ticket_schema_consistency", test_query_ticket_schema_consistency),
        ("search_knowledge_base_schema_consistency", test_search_knowledge_base_schema_consistency),
        ("no_tool_schema_consistency", test_no_tool_schema_consistency),
        (
            "delete_ticket_schema_consistency",
            test_delete_ticket_schema_consistency,
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
