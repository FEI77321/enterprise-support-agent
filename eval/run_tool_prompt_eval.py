# 模块职责：工具提示词评估：检查工具选择提示词是否完整包含工具名称、描述和参数说明，保证模型具备选择工具所需的信息。

from eval_path import setup_backend_path


setup_backend_path()

from app.tool_prompt_builder import build_tool_selection_prompt
from app.tool_registry import list_openai_tools


def test_tool_selection_prompt_contains_tools() -> tuple[bool, str]:  # 测试函数：验证 工具 选择 提示词 包含 工具 场景。
    tools = list_openai_tools()
    prompt = build_tool_selection_prompt(
        user_message="帮我查一下 TICKET-20260724-0001",
        tools=tools,
    )

    required_texts = [
        "工具选择器",
        "query_ticket_status",
        "create_ticket",
        "search_knowledge_base",
        "search_vector_store",
        "tool_name",
        "arguments",
        "TICKET-20260724-0001",
        "请只输出 JSON",
    ]

    for text in required_texts:
        if text not in prompt:
            return False, f"tool selection prompt 缺少必要文本: {text}"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("tool_selection_prompt_contains_tools", test_tool_selection_prompt_contains_tools),
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
