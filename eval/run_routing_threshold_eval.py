# 模块职责：检索路由阈值评估：模拟不同关键词与向量检索分数，验证 Agent 在阈值边界的回答、澄清和建单决策。

from eval_path import setup_backend_path

setup_backend_path()

import app.agent as agent_module
from app.agent import handle_message
from app.tool_registry import ToolResult


def run_with_mocked_search(
    knowledge_results: list[dict],
    vector_results: list[dict],
):  # 函数：临时替换检索工具返回值，并执行一次 Agent 消息处理。
    old_run_tool = agent_module.run_tool
    called_tools: list[str] = []

    def fake_run_tool(tool_name: str, **kwargs) -> ToolResult:  # 函数：模拟知识库、向量检索和建单工具的执行结果。
        called_tools.append(tool_name)

        if tool_name == "search_knowledge_base":
            return ToolResult(
                tool_name=tool_name,
                success=True,
                data={"results": knowledge_results},
            )

        if tool_name == "search_vector_store":
            return ToolResult(
                tool_name=tool_name,
                success=True,
                data={"results": vector_results},
            )

        if tool_name == "create_ticket":
            return ToolResult(
                tool_name=tool_name,
                success=True,
                data={
                    "ticket": {
                        "ticket_id": "TICKET-20990101-0001",
                        "title": "测试工单",
                        "description": "阈值边界测试",
                        "category": "IT_SUPPORT",
                        "priority": "MEDIUM",
                        "status": "OPEN",
                        "assignee": "IT Support Team",
                        "created_at": "2099-01-01T00:00:00",
                    }
                },
            )

        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=f"不应调用工具：{tool_name}",
        )

    agent_module.run_tool = fake_run_tool

    try:
        response = handle_message("VPN 连接异常")
        return response, called_tools
    finally:
        agent_module.run_tool = old_run_tool


def test_single_clear_keyword_result_answers() -> tuple[bool, str]:  # 测试函数：验证单条明确关键词证据达到新阈值后直接回答。
    response, called_tools = run_with_mocked_search(
        knowledge_results=[
            {
                "file": "vpn_guide.md",
                "content": "请检查 VPN 客户端配置。",
                "score": 3,
                "chunk_id": "vpn_guide.md::chunk-6",
            }
        ],
        vector_results=[],
    )

    if response.type != "answer":
        return False, f"单条明确证据分数为 3 时应返回 answer，实际为 {response.type}"

    if "search_vector_store" in called_tools:
        return False, "关键词证据已足够明确，不应继续调用向量检索"

    return True, ""


def test_ambiguous_keyword_results_clarify() -> tuple[bool, str]:  # 测试函数：验证多条并列候选且问题不明确时返回澄清。
    response, called_tools = run_with_mocked_search(
        knowledge_results=[
            {
                "file": "vpn_guide.md",
                "content": "请检查 VPN 客户端配置。",
                "score": 3,
                "chunk_id": "vpn_guide.md::chunk-6",
            },
            {
                "file": "vpn_guide.md",
                "content": "请检查 VPN 网络状态。",
                "score": 3,
                "chunk_id": "vpn_guide.md::chunk-7",
            },
        ],
        vector_results=[],
    )

    if response.type != "clarify":
        return False, f"并列候选且问题不明确时应返回 clarify，实际为 {response.type}"

    if "search_vector_store" in called_tools:
        return False, "已有待澄清关键词结果时，不应继续调用向量检索"

    return True, ""


def test_vector_score_at_fallback_threshold() -> tuple[bool, str]:  # 测试函数：验证向量分数等于 0.4 时进入向量澄清。
    response, _ = run_with_mocked_search(
        knowledge_results=[],
        vector_results=[
            {
                "file": "vpn_guide.md",
                "content": "请检查虚拟网卡驱动。",
                "score": 0.4,
                "chunk_id": "vpn_guide.md::chunk-6",
            }
        ],
    )

    if response.type != "clarify":
        return False, f"向量分数为 0.4 时应返回 clarify，实际为 {response.type}"

    if "vector_clarify" not in response.workflow_steps:
        return False, f"期望进入 vector_clarify，实际为 {response.workflow_steps}"

    return True, ""


def test_vector_score_below_fallback_threshold_creates_ticket() -> tuple[bool, str]:  # 测试函数：验证向量分数低于 0.4 时为支持问题创建工单。
    response, called_tools = run_with_mocked_search(
        knowledge_results=[],
        vector_results=[
            {
                "file": "vpn_guide.md",
                "content": "请检查虚拟网卡驱动。",
                "score": 0.39,
                "chunk_id": "vpn_guide.md::chunk-6",
            }
        ],
    )

    if response.type != "ticket_created":
        return False, f"向量分数为 0.39 时应创建工单，实际为 {response.type}"

    if "create_ticket" not in called_tools:
        return False, f"期望调用 create_ticket，实际调用为 {called_tools}"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的全部检索路由阈值评估。
    tests = [
        ("single_clear_keyword_result_answers", test_single_clear_keyword_result_answers),
        ("ambiguous_keyword_results_clarify", test_ambiguous_keyword_results_clarify),
        ("vector_score_at_fallback_threshold", test_vector_score_at_fallback_threshold),
        ("vector_score_below_fallback_threshold_creates_ticket", test_vector_score_below_fallback_threshold_creates_ticket),
    ]

    passed = 0

    for name, test_func in tests:
        ok, reason = test_func()
        print(f"{'PASS' if ok else 'FAIL'} {name}")

        if ok:
            passed += 1
        else:
            print(f"  Reason: {reason}")

    print()
    print(f"Routing threshold eval: Passed {passed}/{len(tests)}")

    if passed != len(tests):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
