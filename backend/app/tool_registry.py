# 模块职责：工具注册表模块：集中维护工具名称、用途、参数 schema 和执行函数，提供 OpenAI 格式 schema 导出、统一参数校验与安全执行能力。

import logging
from typing import Any, Callable

from pydantic import BaseModel

from app.knowledge_base import search_knowledge_base
from app.tools import query_ticket_status, create_ticket, delete_ticket
from app.vector_store import search_vector_store


logger = logging.getLogger(__name__)


class ToolResult(BaseModel):  # 类：封装单个注册工具的成功数据或结构化错误。
    tool_name: str
    success: bool
    data: Any | None = None
    error: str | None = None
    error_type: str | None = None


class ToolDefinition(BaseModel):  # 类：描述一个可注册工具的名称、用途、参数 schema 和处理函数。
    name: str
    description: str#工具描述
    parameters: dict[str, str]
    handler: Callable[..., ToolResult]#真正执行工具的函数



def _infer_parameter_type(parameter_name: str) -> str:  # 函数：负责 infer parameter type 相关逻辑。
    if parameter_name == "top_k":
        return "integer"

    return "string"

def list_openai_tools() -> list[dict[str, object]]:  # 函数：负责 列表 OpenAI 工具 相关逻辑。
    tools: list[dict[str, object]] = []

    for tool in TOOL_REGISTRY.values():
        properties = {
            parameter_name: {
                "type": _infer_parameter_type(parameter_name),
                "description": description,
            }
            for parameter_name, description in tool.parameters.items()
        }
        required = [
            parameter_name
            for parameter_name in tool.parameters.keys()
            if parameter_name != "top_k"
        ]

        tools.append(
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            }
        )

    return tools



def query_ticket_status_tool(ticket_id: str) -> ToolResult:  # 函数：负责 查询 工单 状态 工具 相关逻辑。
    ticket = query_ticket_status(ticket_id)

    if ticket is None:
        return ToolResult(
            tool_name="query_ticket_status",
            success=True,
            data={
                "found": False,
                "ticket_id": ticket_id,
            },
        )

    return ToolResult(
        tool_name="query_ticket_status",
        success=True,
        data={
            "found": True,
            "ticket": ticket.model_dump(),
        },
    )

def create_ticket_tool(message: str) -> ToolResult:  # 函数：负责 创建 工单 工具 相关逻辑。
    ticket = create_ticket(message)

    return ToolResult(
        tool_name="create_ticket",
        success=True,
        data={
            "ticket": ticket.model_dump(),
        },
    )


def delete_ticket_tool(ticket_id: str) -> ToolResult:  # 函数：将删除工单操作封装为注册工具，并返回是否删除成功。
    deleted = delete_ticket(ticket_id)

    return ToolResult(
        tool_name="delete_ticket",
        success=True,
        data={
            "ticket_id": ticket_id,
            "deleted": deleted,
        },
    )



def search_knowledge_base_tool(query: str, top_k: int = 3) -> ToolResult:  # 函数：负责 检索 知识 库 工具 相关逻辑。
    results = search_knowledge_base(query, top_k=top_k)

    return ToolResult(
        tool_name="search_knowledge_base",
        success=True,
        data={
            "results": [
                {
                    "file": result.file,
                    "content": result.content,
                    "score": result.score,
                    "chunk_id": result.chunk_id,
                    "context_chunk_id": result.context_chunk_id,
                }
                for result in results
            ],
        },
    )

def search_vector_store_tool(query: str, top_k: int = 3) -> ToolResult:  # 函数：负责 检索 向量 存储 工具 相关逻辑。
    results = search_vector_store(query, top_k=top_k)

    return ToolResult(
        tool_name="search_vector_store",
        success=True,
        data={
            "results": [
                {
                    "file": result.file,
                    "content": result.content,
                    "score": result.score,
                    "chunk_id": result.chunk_id,
                }
                for result in results
            ],
        },
    )


def run_tool(tool_name: str, **kwargs: Any) -> ToolResult:  # 函数：负责 运行 工具 相关逻辑。
    logger.info("tool_call_start tool_name=%s", tool_name)

    tool = TOOL_REGISTRY.get(tool_name)

    if tool is None:
        logger.info("tool_call_unknown tool_name=%s", tool_name)
        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=f"Unknown tool: {tool_name}",
            error_type="unknown_tool",
        )

    try:
        result= tool.handler(**kwargs)
        logger.info(
            "tool_call_end tool_name=%s success=%s",
            tool_name,
            result.success,
        )
        return result

    except TypeError as exc:
        logger.info(
            "tool_call_invalid_args tool_name=%s error=%s",
            tool_name,
            str(exc),
        )
        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=str(exc),
            error_type="invalid_args",
        )


    except Exception as exc:
        logger.info(
            "tool_call_error tool_name=%s error=%s",
            tool_name,
            str(exc),
        )
        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=str(exc),
            error_type="tool_exception",
        )


TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "query_ticket_status": ToolDefinition(
        name="query_ticket_status",
        description="根据工单号查询工单状态",
        parameters={
            "ticket_id": "工单号，例如 TICKET-20260724-0001",
        },

        handler=query_ticket_status_tool,
    ),
    "create_ticket": ToolDefinition(
        name="create_ticket",
        description="根据用户问题创建 IT 支持工单",
        parameters={
            "message": "用户提交的问题描述，例如 我的电脑蓝屏了，无法正常办公",
        },
        handler=create_ticket_tool,
    ),
    "search_knowledge_base": ToolDefinition(
        name="search_knowledge_base",
        description="从本地 Markdown 企业知识库中检索相关知识片段",
        parameters={
            "query": "用户问题或检索关键词",
            "top_k": "返回结果数量，默认 3",
        },
        handler=search_knowledge_base_tool,
    ),
    "search_vector_store": ToolDefinition(
        name="search_vector_store",
        description="从 ChromaDB 向量索引中检索相关知识片段，作为关键词检索的 fallback",
        parameters={
            "query": "用户问题或检索关键词",
            "top_k": "返回结果数量，默认 3",
        },
        handler=search_vector_store_tool,
    ),
    "delete_ticket": ToolDefinition(
        name="delete_ticket",
        description="根据工单号永久删除工单，需要用户确认后才能执行",
        parameters={
            "ticket_id": "需要删除的工单号，例如 TICKET-20260724-0001",
        },
        handler=delete_ticket_tool,
    ),
    }

def list_tools() -> list[dict[str,object]]:  # 函数：负责 列表 工具 相关逻辑。
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,

        }
        for tool in TOOL_REGISTRY.values()
    ]
