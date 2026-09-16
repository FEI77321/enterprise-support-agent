# 模块职责：共享数据模型模块：使用 Pydantic 和 Enum 定义请求体、响应体、工单、来源引用及状态枚举，作为 API 与业务层之间的结构化契约。

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):  # 类：定义聊天接口接收的用户消息请求体。
    message: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="用户输入的企业支持问题",
    )
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="可选会话 ID；提供后启用滚动摘要与上下文预算管理",
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
    trace_id: str | None = Field(default=None, description="完整执行轨迹 ID")
    safety: dict[str, Any] = Field(
        default_factory=dict,
        description="输入安全判定；不暴露内部规则正文",
    )
    query_rewrite: dict[str, Any] = Field(
        default_factory=dict,
        description="受控 Query Rewrite 的决策记录",
    )
    memory: dict[str, Any] = Field(
        default_factory=dict,
        description="长期记忆的写入门控与本次召回摘要",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="本次上下文预算、滚动摘要和证据裁剪决策，不返回原始被裁剪内容",
    )
    prompt: dict[str, Any] = Field(
        default_factory=dict,
        description="本次实际使用的 Prompt Registry 版本、哈希和灰度通道，不返回 Prompt 正文",
    )
    timing: dict[str, float] = Field(
        default_factory=dict,
        description="请求关键阶段耗时毫秒，用于 Trace 和 AgentOps 聚合",
    )


class TicketCreateRequest(BaseModel):  # 类：定义创建工单接口接收的请求字段。
    message: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="用户提交的工单问题描述，需包含足够的信息便于人工支持处理")


class TicketStatusUpdate(BaseModel):  # 类：定义更新工单状态接口接收的请求字段。
    status: TicketStatus


BadCaseCategory = Literal["retrieval", "rewrite", "safety", "tool", "authorization", "memory", "response", "context", "prompt", "performance"]
BadCaseSeverity = Literal["low", "medium", "high", "critical"]
BadCaseStatus = Literal["open", "triaged", "regression_added", "resolved"]


class BadCaseCreateRequest(BaseModel):
    """将一次可复盘的 Trace 标记为可治理的 Bad Case。"""

    request_id: str = Field(..., min_length=1, max_length=128)
    category: BadCaseCategory
    severity: BadCaseSeverity = "medium"
    expected_behavior: str = Field(..., min_length=5, max_length=2000)
    actual_behavior: str = Field(..., min_length=5, max_length=2000)
    root_cause: str | None = Field(default=None, max_length=2000)
    fix_version: str | None = Field(default=None, max_length=128)
    fixture_kind: Literal["observed", "controlled_fixture"] = "observed"


class BadCaseStatusUpdate(BaseModel):
    """Bad Case 生命周期只允许按治理阶段向前流转。"""

    status: BadCaseStatus


class VersionInfo(BaseModel):  # 类：保存应用版本号与构建信息。
    name: str
    version: str


class VersionResponse(BaseModel):  # 类：定义版本接口返回的结构。
    code: int
    message: str
    data: VersionInfo
