# 模块职责：共享数据模型模块：使用 Pydantic 和 Enum 定义请求体、响应体、工单、来源引用及状态枚举，作为 API 与业务层之间的结构化契约。

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


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
