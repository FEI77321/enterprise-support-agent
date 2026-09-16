"""通过真实 stdio 会话验证 Enterprise Support Agent 的 MCP Server。

本文件不是直接 import 并调用 MCP 工具函数，而是模拟真正的 MCP Client：

1. 使用项目自己的 Python 解释器启动 ``mcp_server/server.py`` 子进程；
2. 通过 stdio 建立读写通道并完成 MCP 初始化握手；
3. 发送 ``tools/list`` 或 ``tools/call`` 协议请求；
4. 解析 Server 返回的 JSON 文本，并对工具白名单和业务结果做断言。

测试覆盖：三个只读工具的精确白名单、正常知识检索、两个检索工具的
非法 top_k、以及不存在工单的结构化返回。测试通过说明协议层和原项目
业务层的完整调用链可用。

运行方式（在项目根目录执行）：
    .\\backend\\.venv\\Scripts\\python.exe .\\eval\\run_mcp_server_eval.py
"""

import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# 从测试文件位置反推项目路径，避免依赖终端当前目录，也避免误用其他
# 项目副本或全局 Python 环境。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_EXE = PROJECT_ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
SERVER_FILE = PROJECT_ROOT / "mcp_server" / "server.py"

# 这是安全白名单。集合精确相等既能发现工具缺失，也能防止 create_ticket
# 或 delete_ticket 等写操作被意外暴露。
EXPECTED_TOOL_NAMES = {
    "search_knowledge_base",
    "query_ticket_status",
    "search_vector_store",
}


async def list_mcp_tools() -> set[str]:
    """启动真实 MCP Server，并通过 ``tools/list`` 获取工具名集合。

    Returns:
        Server 实际暴露的所有 MCP 工具名称集合。

    Notes:
        ``async with`` 退出时会自动关闭 stdio 通道和 Server 子进程，
        不会在测试结束后残留后台服务。
    """
    # StdioServerParameters 描述“用什么命令、参数和工作目录启动 Server”。
    server = StdioServerParameters(
        command=str(PYTHON_EXE),
        args=[str(SERVER_FILE)],
        cwd=str(PROJECT_ROOT),
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # initialize() 完成 MCP 协议握手，之后才能列出或调用工具。
            await session.initialize()
            result = await session.list_tools()
            return {tool.name for tool in result.tools}


async def call_mcp_tool(
    tool_name: str,
    arguments: dict[str, object],
) -> dict:
    """通过真实 stdio 会话调用任意指定的 MCP 工具。

    Args:
        tool_name: 要调用的 MCP 工具名称。
        arguments: 传给该工具的参数字典。

    Returns:
        将 MCP 响应 ``content[0].text`` 中的 JSON 文本解析得到的字典。

    Notes:
        当前 MCP SDK 2.x 在本项目中的实际返回形式是 TextContent，而
        ``structured_content`` 为 None，因此必须使用 ``json.loads``
        解析文本。这是本次实操通过打印真实响应确认的版本行为。
    """
    server = StdioServerParameters(
        command=str(PYTHON_EXE),
        args=[str(SERVER_FILE)],
        cwd=str(PROJECT_ROOT),
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            response = await session.call_tool(tool_name, arguments)
            # Python dict 被 Server 序列化为 JSON 文本后放在第一段内容中。
            return json.loads(response.content[0].text)


def test_mcp_exposes_three_read_only_tools() -> None:
    """断言 MCP Server 只暴露预期的三个只读工具。

    该测试同时验证工具发现链路和安全白名单，防止有副作用的写工具被
    外部 MCP Client 绕过原项目确认流程直接调用。
    """
    actual_tool_names = asyncio.run(list_mcp_tools())

    assert actual_tool_names == EXPECTED_TOOL_NAMES, (
        f"工具不符合预期：{actual_tool_names}"
    )


def test_mcp_can_call_knowledge_search() -> None:
    """验证知识库 MCP 工具能真实调用并返回一条检索结果。"""
    result = asyncio.run(
        call_mcp_tool(
            "search_knowledge_base",
            {
                "query": "VPN 720",
                "top_k": 1,
            },
        )
    )

    assert result["success"] is True
    assert result["tool_name"] == "search_knowledge_base"
    assert len(result["data"]["results"]) == 1


def test_mcp_rejects_non_positive_top_k() -> None:
    """验证关键词检索会以结构化参数错误拒绝 ``top_k=0``。"""
    result = asyncio.run(
        call_mcp_tool(
            "search_knowledge_base",
            {
                "query": "VPN 720",
                "top_k": 0,
            },
        )
    )

    assert result["success"] is False
    assert result["error_type"] == "invalid_args"


def test_mcp_vector_search_rejects_non_positive_top_k() -> None:
    """验证向量检索拒绝非法 top_k，且错误中的工具名准确。"""
    result = asyncio.run(
        call_mcp_tool(
            "search_vector_store",
            {
                "query": "VPN 720",
                "top_k": 0,
            },
        )
    )

    assert result["success"] is False
    assert result["error_type"] == "invalid_args"
    assert result["tool_name"] == "search_vector_store"


def test_mcp_returns_not_found_for_missing_ticket() -> None:
    """验证查询不存在工单时协议正常完成并返回 ``found=False``。

    ``success=True`` 表示查询工具执行成功，不代表数据库中找到了工单；
    是否找到由业务字段 ``data.found`` 表达。
    """
    result = asyncio.run(
        call_mcp_tool(
            "query_ticket_status",
            {
                "ticket_id": "TICKET-MCP-NOT-FOUND",
            },
        )
    )

    assert result["success"] is True
    assert result["tool_name"] == "query_ticket_status"
    assert result["data"]["found"] is False
    assert result["data"]["ticket_id"] == "TICKET-MCP-NOT-FOUND"


if __name__ == "__main__":
    # 直接运行文件时按固定顺序执行五项协议回归；任意 assert 失败都会
    # 立即以非零退出码终止，便于 run_all_eval.py 统一汇总。
    test_mcp_exposes_three_read_only_tools()
    test_mcp_can_call_knowledge_search()
    test_mcp_rejects_non_positive_top_k()
    test_mcp_vector_search_rejects_non_positive_top_k()
    test_mcp_returns_not_found_for_missing_ticket()
    print("MCP stdio protocol contract: Passed 5/5")
    print("PASS: MCP 工具发现、检索、参数校验和工单查询均正常")
