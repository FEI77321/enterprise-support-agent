# 模块职责：定义问答工作流的中间状态容器，集中保存用户输入、检索结果、工具结果、最终回答和每一步执行记录，方便编排和排查问题。

from dataclasses import dataclass, field
from typing import Any

from app.knowledge_base import SearchResult
from app.models import ChatResponseType,Source, Ticket
from app.vector_store import VectorSearchResult


@dataclass
class AgentState:  # 类：保存一次聊天 Agent 运行时的全部中间数据和工作流步骤。
    request_id: str
    message: str
    session_id: str | None = None
    workflow_steps: list[str] = field(default_factory=list)

    ticket_id: str | None = None
    knowledge_results: list[SearchResult] = field(default_factory=list)
    vector_results: list[VectorSearchResult] = field(default_factory=list)

    sources: list[Source] = field(default_factory=list)
    ticket: Ticket | None = None
    answer: str | None = None
    response_type: ChatResponseType | None = None
    harness_session: Any | None = None

    def add_step(self, step: str) -> None:  # 函数：负责 add step 相关逻辑。
        self.workflow_steps.append(step)
