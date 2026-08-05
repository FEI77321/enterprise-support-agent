# 模块职责：工具注册表评估：验证工具 schema 导出、未知工具、参数错误、异常捕获、知识库检索、向量检索和工单工具等注册表行为。

from eval_path import setup_backend_path
setup_backend_path()
from app.tools import delete_ticket
from app.tool_registry import (
    TOOL_REGISTRY,
    ToolDefinition,
    ToolResult,
    list_openai_tools,
    list_tools,
    run_tool,
)

EXPECTED_TOOLS = {
    "query_ticket_status",
    "create_ticket",
    "search_knowledge_base",
    "search_vector_store",
}

def test_list_openai_tools_schema() -> tuple[bool, str]:  # 测试函数：验证 列表 OpenAI 工具 schema 场景。
    tools = list_openai_tools()

    if not tools:
        return False, "期望 OpenAI tools schema 非空"

    tools_by_name = {
        tool["name"]: tool
        for tool in tools
        if isinstance(tool.get("name"), str)
    }

    for tool_name in EXPECTED_TOOLS:
        if tool_name not in tools_by_name:
            return False, f"OpenAI tools schema 缺少工具: {tool_name}"

        tool_schema = tools_by_name[tool_name]

        if tool_schema.get("type") != "function":
            return False, f"工具 {tool_name} type 应为 function，实际为 {tool_schema}"

        parameters = tool_schema.get("parameters")
        if not isinstance(parameters, dict):
            return False, f"工具 {tool_name} 缺少 parameters schema"

        if parameters.get("type") != "object":
            return False, f"工具 {tool_name} parameters.type 应为 object"

        properties = parameters.get("properties")
        if not isinstance(properties, dict):
            return False, f"工具 {tool_name} 缺少 properties"

        if parameters.get("additionalProperties") is not False:
            return False, f"工具 {tool_name} 应禁止 additionalProperties"

    ticket_tool = tools_by_name["query_ticket_status"]
    ticket_parameters = ticket_tool.get("parameters")

    if not isinstance(ticket_parameters, dict):
        return False, "query_ticket_status 缺少 parameters schema"

    ticket_properties = ticket_parameters.get("properties")

    if not isinstance(ticket_properties, dict):
        return False, "query_ticket_status 缺少 properties"

    ticket_id_schema = ticket_properties.get("ticket_id")

    if not isinstance(ticket_id_schema, dict):
        return False, "query_ticket_status 缺少 ticket_id schema"

    if ticket_id_schema.get("type") != "string":
        return False, "ticket_id 类型应为 string"

    kb_tool = tools_by_name["search_knowledge_base"]
    kb_parameters = kb_tool.get("parameters")

    if not isinstance(kb_parameters, dict):
        return False, "search_knowledge_base 缺少 parameters schema"

    kb_properties = kb_parameters.get("properties")

    if not isinstance(kb_properties, dict):
        return False, "search_knowledge_base 缺少 properties"

    top_k_schema = kb_properties.get("top_k")

    if not isinstance(top_k_schema, dict):
        return False, "search_knowledge_base 缺少 top_k schema"

    if top_k_schema.get("type") != "integer":
        return False, "top_k 类型应为 integer"

    required = kb_parameters.get("required", [])

    if not isinstance(required, list):
        return False, "search_knowledge_base required 应为 list"

    if "top_k" in required:
        return False, "top_k 有默认值，不应作为 required 参数"

    return True, ""



def test_list_tools() -> tuple[bool, str]:  # 测试函数：验证 列表 工具 场景。
    tools = list_tools()
    tool_names = {tool["name"] for tool in tools}

    missing_tools = EXPECTED_TOOLS - tool_names
    if missing_tools:
        return False, f"缺少工具: {sorted(missing_tools)}"

    tools_by_name = {
        tool["name"]: tool
        for tool in tools
        if isinstance(tool.get("name"), str)
    }
    expected_parameters = {
        "query_ticket_status": {"ticket_id"},
        "create_ticket": {"message"},
        "search_knowledge_base": {"query", "top_k"},
        "search_vector_store": {"query", "top_k"},
    }
    for tool_name, parameter_names in expected_parameters.items():
        parameters = tools_by_name[tool_name].get("parameters")

        if not isinstance(parameters, dict):
            return False, f"工具 {tool_name} 缺少 parameters 字典"

        missing_parameters = parameter_names - set(parameters.keys())

        if missing_parameters:
            return False, (
                f"工具 {tool_name} 缺少参数说明: {sorted(missing_parameters)}"
            )



    return True, ""


def test_unknown_tool() -> tuple[bool, str]:  # 测试函数：验证 未知 工具 场景。
    result = run_tool("not_exists")

    if result.success:
        return False, "期望未知工具调用失败，但实际 success=True"

    if result.error is None:
        return False, "期望未知工具返回错误信息，但实际 error=None"

    if result.error_type != "unknown_tool":
        return False, f"期望 error_type=unknown_tool，实际为 {result.error_type}"

    return True, ""


def test_tool_exception_error_type() -> tuple[bool, str]:  # 测试函数：验证 工具 异常 错误 type 场景。
    def broken_handler() -> ToolResult:  # 函数：负责 broken handler 相关逻辑。
        raise RuntimeError("mock tool error")

    old_tool = TOOL_REGISTRY.get("broken_tool")

    TOOL_REGISTRY["broken_tool"] = ToolDefinition(
        name="broken_tool",
        description="用于测试工具异常处理",
        parameters={},
        handler=broken_handler,
    )

    try:
        result = run_tool("broken_tool")
    finally:
        if old_tool is None:
            TOOL_REGISTRY.pop("broken_tool", None)
        else:
            TOOL_REGISTRY["broken_tool"] = old_tool

    if result.success:
        return False, "期望工具异常时 success=False"

    if result.error_type != "tool_exception":
        return False, f"期望 error_type=tool_exception，实际为 {result.error_type}"

    if "mock tool error" not in (result.error or ""):
        return False, f"期望 error 包含 mock tool error，实际为 {result.error}"

    return True, ""


def test_invalid_tool_args() -> tuple[bool, str]:  # 测试函数：验证 非法 工具 args 场景。
    result = run_tool("query_ticket_status")

    if result.success:
        return False, "期望缺少参数时 success=False"

    if result.error_type != "invalid_args":
        return False, f"期望 error_type=invalid_args，实际为 {result.error_type}"

    if "ticket_id" not in (result.error or ""):
        return False, f"期望 error 包含 ticket_id，实际为 {result.error}"

    return True, ""



def test_search_knowledge_base() -> tuple[bool, str]:  # 测试函数：验证 检索 知识 库 场景。
    result = run_tool("search_knowledge_base", query="VPN 720 错误怎么办")

    if not result.success:
        return False, f"期望工具调用成功，但失败了: {result.error}"

    if result.data is None:
        return False, "期望返回 data，但实际 data=None"

    results = result.data.get("results", [])

    if not results:
        return False, "期望至少命中一个知识库片段，但 results 为空"

    source_files = {item["file"] for item in results}

    if "vpn_guide.md" not in source_files:
        return False, f"期望命中 vpn_guide.md，实际命中 {sorted(source_files)}"

    return True, ""


def test_query_ticket_status_not_found() -> tuple[bool, str]:  # 测试函数：验证 查询 工单 状态 不 存在 场景。
    result = run_tool("query_ticket_status", ticket_id="TICKET-20990101-9999")

    if not result.success:
        return False, f"期望工具调用成功，但失败了: {result.error}"

    if result.data is None:
        return False, "期望返回 data，但实际 data=None"

    if result.data.get("found") is not False:
        return False, f"期望 found=False，实际 data={result.data}"

    if result.data.get("ticket_id") != "TICKET-20990101-9999":
        return False, f"期望返回原 ticket_id，实际 data={result.data}"

    return True, ""


def test_search_vector_store() -> tuple[bool, str]:  # 测试函数：验证 检索 向量 存储 场景。
    result = run_tool("search_vector_store", query="VPN 720 错误怎么办")

    if not result.success:
        return False, f"期望工具调用成功，但失败了: {result.error}"

    if result.data is None:
        return False, "期望返回 data，但实际 data=None"

    results = result.data.get("results", [])

    if not results:
        return False, "期望至少命中一个向量检索结果，但 results 为空"

    source_files = {item["file"] for item in results}

    if "vpn_guide.md" not in source_files:
        return False, f"期望命中 vpn_guide.md，实际命中 {sorted(source_files)}"

    return True, ""


def test_create_ticket() -> tuple[bool, str]:  # 测试函数：验证通过工具创建工单后能返回正确的工单信息。
    created_ticket_id: str | None = None

    try:
        result = run_tool(
            "create_ticket",
            message="我的电脑蓝屏，无法正常工作",
        )

        if not result.success:
            return False, f"期望工具调用成功，但失败了: {result.error}"

        ticket = (result.data or {}).get("ticket")

        if not isinstance(ticket, dict):
            return False, f"期望返回 ticket，实际 data={result.data}"

        created_ticket_id = ticket.get("ticket_id")

        if not isinstance(created_ticket_id, str):
            return False, f"期望 ticket_id 为字符串，实际 ticket={ticket}"

        if not created_ticket_id.startswith("TICKET-"):
            return False, f"期望生成 TICKET- 开头的工单号，实际为 {created_ticket_id}"

        if ticket.get("status") != "OPEN":
            return False, f"期望 status=OPEN，实际 ticket={ticket}"

        if ticket.get("priority") != "HIGH":
            return False, f"期望 priority=HIGH，实际 ticket={ticket}"

        return True, ""
    finally:
        if created_ticket_id is not None:
            delete_ticket(created_ticket_id)


def test_create_and_query_ticket() -> tuple[bool, str]:  # 测试函数：验证创建工单后可通过工具查询到同一张 SQLite 工单。
    created_ticket_id: str | None = None

    try:
        create_result = run_tool(
            "create_ticket",
            message="我的 VPN 无法连接，需要 IT 支持",
        )

        if not create_result.success:
            return False, f"创建工单失败: {create_result.error}"

        ticket = (create_result.data or {}).get("ticket")

        if not isinstance(ticket, dict):
            return False, f"期望创建结果包含 ticket，实际 data={create_result.data}"

        created_ticket_id = ticket.get("ticket_id")

        if not isinstance(created_ticket_id, str):
            return False, f"期望 ticket_id 为字符串，实际 ticket={ticket}"

        query_result = run_tool(
            "query_ticket_status",
            ticket_id=created_ticket_id,
        )

        if not query_result.success:
            return False, f"查询工单失败: {query_result.error}"

        query_data = query_result.data or {}

        if query_data.get("found") is not True:
            return False, f"期望 found=True，实际 data={query_data}"

        queried_ticket = query_data.get("ticket")

        if not isinstance(queried_ticket, dict):
            return False, f"期望查询结果包含 ticket，实际 data={query_data}"

        if queried_ticket.get("ticket_id") != created_ticket_id:
            return False, f"期望查询到同一 ticket_id，实际 data={query_data}"

        return True, ""
    finally:
        if created_ticket_id is not None:
            delete_ticket(created_ticket_id)

def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("list_tools", test_list_tools),
        ("unknown_tool", test_unknown_tool),
        ("tool_exception_error_type", test_tool_exception_error_type),
        ("search_knowledge_base", test_search_knowledge_base),
        ("invalid_tool_args", test_invalid_tool_args),
        ("query_ticket_status_not_found", test_query_ticket_status_not_found),
        ("search_vector_store", test_search_vector_store),
        ("create_ticket", test_create_ticket),
        ("create_and_query_ticket", test_create_and_query_ticket),
        ("list_openai_tools_schema", test_list_openai_tools_schema),
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


if __name__ == "__main__":
    main()
