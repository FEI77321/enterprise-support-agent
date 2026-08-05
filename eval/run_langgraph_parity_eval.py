# 模块职责：双引擎一致性评估：对同一组场景，分别用规则版（agent.py）与 LangGraph 版
# （graph_agent.py）处理，断言 response_type 与 workflow_steps 完全一致，防止重构引入行为回归。

import os

from eval_path import setup_backend_path

setup_backend_path()

# 关闭真实 LLM：双引擎都走规则答案，对比聚焦路由行为，排除模型输出不确定性
os.environ["ENABLE_LLM_ANSWER"] = "false"

import app.agent as agent_module
import app.graph_agent as graph_module
from app.tool_registry import ToolResult

MOCK_TICKET = {
    "ticket_id": "TICKET-20990101-0001",
    "title": "测试工单",
    "description": "双引擎一致性测试",
    "category": "IT_SUPPORT",
    "priority": "MEDIUM",
    "status": "OPEN",
    "assignee": "IT Support Team",
    "created_at": "2099-01-01T00:00:00",
}


class _MockCase:  # 类：一个双引擎对比场景：消息 + 检索工具返回配置。
    def __init__(self, name, message, knowledge=None, vector=None, found_ticket=None):
        self.name = name
        self.message = message
        self.knowledge = knowledge or []
        self.vector = vector or []
        self.found_ticket = found_ticket


def run_case_with_mocks(case, handler):  # 函数：替换两个模块的检索工具并执行一次消息处理。
    old_rules = agent_module.run_tool
    old_graph = graph_module.run_tool

    def fake_run_tool(tool_name: str, **kwargs) -> ToolResult:  # 函数：按场景返回固定的工具结果。
        if tool_name == "query_ticket_status":
            if case.found_ticket is not None:
                return ToolResult(tool_name=tool_name, success=True,
                                  data={"found": True, "ticket": case.found_ticket})
            return ToolResult(tool_name=tool_name, success=True, data={"found": False})
        if tool_name == "search_knowledge_base":
            return ToolResult(tool_name=tool_name, success=True, data={"results": case.knowledge})
        if tool_name == "search_vector_store":
            return ToolResult(tool_name=tool_name, success=True, data={"results": case.vector})
        if tool_name == "create_ticket":
            return ToolResult(tool_name=tool_name, success=True, data={"ticket": MOCK_TICKET})
        return ToolResult(tool_name=tool_name, success=False, error=f"不应调用工具：{tool_name}")

    agent_module.run_tool = fake_run_tool
    graph_module.run_tool = fake_run_tool
    try:
        return handler(case.message)
    finally:
        agent_module.run_tool = old_rules
        graph_module.run_tool = old_graph


CASES = [
    _MockCase(
        "answer_high_confidence",
        "VPN 720 错误怎么办",
        knowledge=[{"file": "vpn_guide.md", "content": "如果错误码为 720，请重装虚拟网卡驱动。",
                    "score": 6, "chunk_id": "vpn_guide.md::chunk-6"}],
    ),
    _MockCase("ticket_status_query", "查一下 TICKET-20990101-0001 的状态",
              found_ticket=MOCK_TICKET),
    _MockCase(
        "clarify_low_confidence",
        "VPN 无法连接",
        knowledge=[{"file": "vpn_guide.md", "content": "请检查 VPN 客户端配置。",
                    "score": 5, "chunk_id": "vpn_guide.md::chunk-2"}],
    ),
    _MockCase(
        "vector_clarify",
        "笔记本电脑无法开机",
        vector=[{"file": "account_login_faq.md", "content": "如果企业账号无法登录，请按以下步骤处理：",
                 "score": 0.4, "chunk_id": "account_login_faq.md::chunk-2"}],
    ),
    _MockCase("create_ticket", "打印机驱动安装失败报错0x800f081f"),
    _MockCase("unsupported_question", "工位键盘进水失灵了"),
]


def test_parity(case) -> tuple[bool, str]:  # 测试函数：同一场景下双引擎响应类型与执行路径必须一致。
    rules_response = run_case_with_mocks(case, agent_module.handle_message)
    graph_response = run_case_with_mocks(case, graph_module.handle_message)

    if rules_response.type != graph_response.type:
        return False, f"response_type 不一致：rules={rules_response.type}, langgraph={graph_response.type}"

    if list(rules_response.workflow_steps) != list(graph_response.workflow_steps):
        return False, (f"workflow_steps 不一致：\n"
                       f"  rules={rules_response.workflow_steps}\n"
                       f"  langgraph={graph_response.workflow_steps}")

    return True, ""


def main() -> None:  # 函数：运行全部双引擎一致性场景。
    passed = 0
    for case in CASES:
        ok, reason = test_parity(case)
        print(f"{'PASS' if ok else 'FAIL'} parity::{case.name}")

        if ok:
            passed += 1
        else:
            print(f"  Reason: {reason}")

    print()
    print(f"LangGraph parity eval: Passed {passed}/{len(CASES)}")

    if passed != len(CASES):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
