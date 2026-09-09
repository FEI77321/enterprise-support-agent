# 模块职责：共享数据模型模块：使用 Pydantic 和 Enum 定义请求体、响应体、工单、来源引用及状态枚举，作为 API 与业务层之间的结构化契约。

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):  # 类：定义聊天接口接收的用户消息请求体。
    message: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="用户输入的企业支持问题",
    )


class TicketStatus(str, Enum):  # 类：枚举工单允许使用的处理状态。
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"


class TicketPriority(str, Enum):  # 类：枚举工单允许使用的优先级。
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Source(BaseModel):  # 类：表示回答引用的一条知识库来源。
    file: str
    snippet: str
    score: int = Field(..., ge=0, description="知识库检索匹配分数")
    chunk_id: str | None = Field(default=None, description="知识库片段 ID")
    document_id: str | None = Field(
        default=None,
        description="RAG 2.0 文档版本 ID；旧链路不提供",
    )
    document_version: str | None = Field(
        default=None,
        description="RAG 2.0 文档版本号；旧链路不提供",
    )
    context_chunk_id: str | None = Field(
        default=None,
        description="用于回答上下文的父 Chunk ID；旧链路可为空",
    )
    heading_path: list[str] | None = Field(
        default=None,
        description="命中内容在原文中的 Markdown 标题路径",
    )
    page_start: int | None = Field(
        default=None,
        ge=1,
        description="来源 PDF 的起始页；Markdown 固定为第 1 页",
    )
    page_end: int | None = Field(
        default=None,
        ge=1,
        description="来源 PDF 的结束页；Markdown 固定为第 1 页",
    )

    @model_validator(mode="after")
    def validate_page_reference(self) -> "Source":
        """页码回链必须成对出现，且结束页不能早于起始页。"""

        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("page_start and page_end must be provided together")

        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be greater than or equal to page_start")

        return self


class Ticket(BaseModel):  # 类：表示系统中的一张工单及其业务字段。
    ticket_id: str
    title: str
    description: str
    category: str
    priority: TicketPriority
    status: TicketStatus
    assignee: str
    created_at: str

ChatResponseType = Literal["answer", "ticket_created", "ticket_status", "clarify"]
class ChatResponse(BaseModel):  # 类：定义聊天接口返回的回答、来源和工作流信息。
    request_id: str
    type: ChatResponseType
    answer: str | None = None
    sources: list[Source] = Field(default_factory=list)
    ticket: Ticket | None = None
    workflow_steps: list[str] = Field(default_factory=list)
    harness_trace: list[dict[str, object]] = Field(
        default_factory=list,
        description="Harness 开启时的请求级工具执行轨迹；关闭时为空",
    )


class TicketCreateRequest(BaseModel):  # 类：定义创建工单接口接收的请求字段。
    message: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="用户提交的工单问题描述，需包含足够的信息便于人工支持处理")


class TicketStatusUpdate(BaseModel):  # 类：定义更新工单状态接口接收的请求字段。
    status: TicketStatus


class VersionInfo(BaseModel):  # 类：保存应用版本号与构建信息。
    name: str
    version: str


class VersionResponse(BaseModel):  # 类：定义版本接口返回的结构。
    code: int
    message: str
    data: VersionInfo
