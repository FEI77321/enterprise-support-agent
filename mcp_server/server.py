"""Enterprise Support Agent 的只读 MCP Server 协议适配层。

本文件使用 MCP Python SDK 2.x 创建一个基于 stdio 的 MCP Server，
把项目原有 Tool Registry 中的三个只读能力转换为标准 MCP 工具：

1. ``search_knowledge_base``：检索本地 Markdown 企业知识库；
2. ``search_vector_store``：检索 ChromaDB 向量知识库；
3. ``query_ticket_status``：查询指定工单的当前状态。

本层只负责 MCP 工具注册、协议参数边界校验和结果序列化，真正的业务
逻辑仍由 ``backend/app/tool_registry.py`` 中的 ``run_tool`` 执行。
创建和删除工单属于有副作用的写操作，当前不通过 MCP 暴露，避免外部
Client 绕过主 Agent 的用户确认和权限控制流程。

运行方式（在项目根目录执行）：
    .\\backend\\.venv\\Scripts\\python.exe .\\mcp_server\\server.py

通常不直接手动运行，而是由 MCP Inspector 或自动化 ClientSession
将此文件作为子进程启动，并通过标准输入/输出完成协议通信。
"""

import sys
from pathlib import Path

from mcp.server import MCPServer

# server.py 位于独立的 mcp_server 目录。把 backend 加入模块搜索路径后，
# 才能复用原项目的 app.tool_registry，而不复制任何业务实现。
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.tool_registry import run_tool

# Server 名称会在 MCP 初始化握手和 Inspector 页面中显示。
mcp = MCPServer("enterprise-support-agent")


def invalid_top_k_result(tool_name: str) -> dict:
    """生成检索数量参数不合法时的统一结构化错误。

    ``top_k < 1`` 没有业务意义，因此在 MCP 协议边界立即拒绝，避免
    无效参数继续进入原项目的关键词检索或向量检索实现。

    Args:
        tool_name: 收到非法参数的 MCP 工具名称，用于准确标识错误来源。

    Returns:
        与项目 ``ToolResult`` 字段一致的错误字典。其中 ``success`` 为
        False，``error_type`` 为 ``invalid_args``。
    """
    return {
        "tool_name": tool_name,
        "success": False,
        "data": None,
        "error": "top_k 必须大于 0",
        "error_type": "invalid_args",
    }


@mcp.tool()
def search_knowledge_base(query: str, top_k: int = 3) -> dict:
    """通过 Tool Registry 检索 Markdown 企业 IT 支持知识库。

    ``@mcp.tool()`` 会根据函数名、类型标注、默认值和本文档字符串，
    自动生成 MCP 工具描述和参数 schema。

    Args:
        query: 用户问题或知识库检索关键词，例如 ``VPN 720``。
        top_k: 最多返回的知识片段数量，默认 3，必须大于 0。

    Returns:
        ``run_tool`` 返回的 ``ToolResult`` 转换后的字典，包含工具名、
        是否成功以及命中的文件、内容、分数和 chunk_id 等数据。
    """

    # 在协议入口验证参数，防止非法 top_k 进入底层检索模块。
    if top_k < 1:
        return invalid_top_k_result("search_knowledge_base")

    # MCP 层只转发调用；真实检索逻辑仍由原项目统一注册表执行。
    result = run_tool(
        "search_knowledge_base",
        query=query,
        top_k=top_k,
    )
    return result.model_dump()


@mcp.tool()
def query_ticket_status(ticket_id: str) -> dict:
    """通过 Tool Registry 查询指定工单的状态。

    Args:
        ticket_id: 要查询的工单编号，例如 ``TICKET-20260724-0001``。

    Returns:
        结构化工具结果。查询动作成功但工单不存在时，``success`` 仍为
        True，业务结果通过 ``data.found=False`` 表示。

    Notes:
        这是只读操作，不会创建、修改或删除任何工单。
    """
    result = run_tool(
        "query_ticket_status",
        ticket_id=ticket_id,
    )
    return result.model_dump()


@mcp.tool()
def search_vector_store(query: str, top_k: int = 3) -> dict:
    """通过 Tool Registry 检索 ChromaDB 向量知识库。

    Args:
        query: 用户的自然语言问题或语义检索文本。
        top_k: 最多返回的向量检索结果数量，默认 3，必须大于 0。

    Returns:
        向量检索的结构化工具结果字典；非法 top_k 返回统一的
        ``invalid_args`` 错误。
    """

    # 与关键词检索保持相同的协议参数安全规则。
    if top_k < 1:
        return invalid_top_k_result("search_vector_store")

    result = run_tool(
        "search_vector_store",
        query=query,
        top_k=top_k,
    )
    return result.model_dump()


if __name__ == "__main__":
    # stdio 模式由 Client 启动本进程，并通过 stdin/stdout 交换 MCP 消息。
    # 不要在 stdout 中随意 print 调试文本，否则可能污染协议数据流。
    mcp.run(transport="stdio")
