# 模块职责：LangGraph 版 Agent 编排：用显式状态图替代 agent.py 的 if/else 路由，
# 节点为纯函数，条件边决定走向，最终构造与 agent.py 完全一致的 ChatResponse。
from app.agent import (
    TICKET_PATTERN,
    VECTOR_FALLBACK_THRESHOLD,
    _has_confident_rule_answer,
    _is_support_related,
    _has_valid_llm_citations,
    _snippet,
)
from app.knowledge_base import build_answer, SearchResult
from app.models import Source, Ticket, ChatResponseType
from app.prompt_builder import build_prompt
from app.llm_client import generate_answer_result
from app.tool_registry import run_tool
from app.tool_registry import ToolResult
from app.agent_harness import AgentHarness, HarnessSession, create_harness_session
from app.config import (
    get_agent_harness_max_steps,
    is_agent_harness_enabled,
    is_llm_answer_enabled,
)
import operator
from typing import Annotated, TypedDict
from app.vector_store import VectorSearchResult



class GraphState(TypedDict):  # 类：LangGraph 的共享状态，字段与 agent_state.AgentState 对齐。
    request_id: str
    message: str
    ticket_id: str | None
    in_support_scope: bool
    knowledge_results: list[SearchResult]
    vector_results: list[VectorSearchResult]
    sources: list[Source]
    ticket: Ticket | None
    answer: str | None
    response_type: ChatResponseType | None
    workflow_steps: Annotated[list[str], operator.add]  # reducer：节点返回的 step 自动追加
    harness_session: HarnessSession | None


def _run_graph_tool(
    state: GraphState,
    tool_name: str,
    **arguments: object,
) -> ToolResult:
    """Graph 保留业务节点，真实工具执行交给 Harness 统一治理。"""
    if not is_agent_harness_enabled():
        return run_tool(tool_name, **arguments)

    session = state.get("harness_session")
    if session is None:
        session = create_harness_session(
            request_id=state["request_id"],
            engine="langgraph",
            max_steps=get_agent_harness_max_steps(),
        )
        state["harness_session"] = session

    result = AgentHarness().execute_tool(
        session=session,
        tool_name=tool_name,
        arguments=arguments,
    )
    if result.tool_result is not None:
        return result.tool_result
    return ToolResult(
        tool_name=tool_name,
        success=False,
        error=result.reason or "Harness blocked tool execution",
        error_type=result.status,
    )


def extract_ticket_id(state: GraphState) -> dict:  # 节点：提取工单号。
    match = TICKET_PATTERN.search(state["message"])
    ticket_id = match.group(0).upper() if match else None
    return {"ticket_id": ticket_id, "workflow_steps": ["extract_ticket_id"]}


def query_ticket(state: GraphState) -> dict:  # 节点：按工单号查询状态。
    steps = ["query_ticket_status"]
    tool_result = _run_graph_tool(state, "query_ticket_status", ticket_id=state["ticket_id"])

    if not tool_result.success:
        steps.append("query_ticket_error")
        return {
            "answer": "查询工单状态时发生错误，请稍后再试。",
            "response_type": "ticket_status",
            "workflow_steps": steps,
        }

    ticket_data = tool_result.data or {}
    if ticket_data.get("found"):
        steps.append("ticket_status")
        ticket = Ticket(**ticket_data["ticket"])
        return {
            "ticket": ticket,
            "answer": f"工单 {ticket.ticket_id} 当前状态为 {ticket.status}，处理人为 {ticket.assignee}。",
            "response_type": "ticket_status",
            "workflow_steps": steps,
        }

    steps.append("ticket_not_found")
    return {
        "answer": f"没有找到工单 {state['ticket_id']}，请确认工单号是否正确。",
        "response_type": "ticket_status",
        "workflow_steps": steps,
    }


def check_support_scope(state: GraphState) -> dict:  # 节点：判断是否企业 IT 支持范围。
    return {
        "in_support_scope": _is_support_related(state["message"]),
        "workflow_steps": [],
    }

def unsupported_question(state: GraphState) -> dict:  # 节点：非 IT 范围拦截，输出标准提示。
    return {
        "answer": "这个问题不属于企业 IT 支持范围。我可以帮你处理 VPN、账号登录、MFA、报销、请假、蓝屏、打印机或 IT 工单相关问题。",
        "response_type": "clarify",
        "workflow_steps": ["unsupported_question"],
    }



def search_knowledge_base(state: GraphState) -> dict:  # 节点：关键词检索。
    tool_result = _run_graph_tool(state, "search_knowledge_base", query=state["message"])
    results: list[SearchResult] = []
    if tool_result.success:
        search_data = tool_result.data or {}
        results = [
            SearchResult(
                file=item["file"],
                content=item["content"],
                score=item["score"],
                chunk_id=item["chunk_id"],
                context_chunk_id=item.get("context_chunk_id"),
            )
            for item in search_data.get("results", [])
        ]
    return {"knowledge_results": results, "workflow_steps": ["search_knowledge_base"]}


def answer_high_confidence(state: GraphState) -> dict:  # 节点：高置信命中后组装回答（含 LLM 校验）。
    results = state["knowledge_results"]
    sources = [
        Source(
            file=r.file,
            snippet=_snippet(r.content),
            score=r.score,
            chunk_id=r.context_chunk_id or r.chunk_id,
        )
        for r in results[:1]
    ]
    answer = build_answer(state["message"], results)
    steps = ["rule_answer"]

    prompt = build_prompt(state["message"], sources)
    if is_llm_answer_enabled():
        llm_result = generate_answer_result(prompt)
        steps.append("llm_answer")
        if llm_result.success:
            if _has_valid_llm_citations(llm_result.answer, sources):
                answer = llm_result.answer
            else:
                steps.append("llm_invalid_citation_fallback")
        else:
            steps.append("llm_fallback_to_rule_answer")

    steps.append("knowledge_answer")
    return {
        "sources": sources,
        "answer": answer,
        "response_type": "answer",
        "workflow_steps": steps,
    }


def clarify(state: GraphState) -> dict:  # 节点：低置信澄清追问。
    results = state["knowledge_results"]
    sources = [
        Source(
            file=r.file,
            snippet=_snippet(r.content),
            score=r.score,
            chunk_id=r.context_chunk_id or r.chunk_id,
        )
        for r in results
    ]
    return {
        "sources": sources,
        "answer": "我找到了一些可能相关的信息，但还不太确定。你可以补充一下具体场景吗？例如是 VPN、账号登录、报销、请假，还是其他问题？",
        "response_type": "clarify",
        "workflow_steps": ["clarify"],
    }


def search_vector_store(state: GraphState) -> dict:  # 节点：向量检索 fallback。
    tool_result = _run_graph_tool(state, "search_vector_store", query=state["message"])
    results: list[VectorSearchResult] = []
    if tool_result.success:
        vector_data = tool_result.data or {}
        results = [
            VectorSearchResult(
                file=item["file"],
                content=item["content"],
                score=item["score"],
                chunk_id=item["chunk_id"],
            )
            for item in vector_data.get("results", [])
        ]
    return {"vector_results": results, "workflow_steps": ["search_vector_store"]}


def vector_answer(state: GraphState) -> dict:
    """高置信向量命中时，直接依据首条证据回答。"""
    best = state["vector_results"][0]

    source = Source(
        file=best.file,
        snippet=_snippet(best.content),
        score=int(best.score * 100),
        chunk_id=best.chunk_id,
    )

    answer = (
        f"根据《{best.file}》中的相关内容，可以参考以下处理方式：\n\n"
        f"{best.content}\n\n"
        "参考来源：\n"
        f"- File: {best.file}, Chunk ID: {best.chunk_id}"
    )

    return {
        "sources": [source],
        "answer": answer,
        "response_type": "answer",
        "workflow_steps": ["vector_answer"],
    }


def vector_clarify(state: GraphState) -> dict:  # 节点：向量命中后的澄清追问。
    results = state["vector_results"]
    sources = [
        Source(file=r.file, snippet=_snippet(r.content), score=int(r.score * 100), chunk_id=r.chunk_id)
        for r in results
    ]
    return {
        "sources": sources,
        "answer": "我找到了一些可能相关的知识片段，但还不太确定。你可以补充一下具体场景或错误信息吗？",
        "response_type": "clarify",
        "workflow_steps": ["vector_clarify"],
    }


def create_ticket(state: GraphState) -> dict:  # 节点：无解时创建工单。
    steps = ["create_ticket"]
    tool_result = _run_graph_tool(state, "create_ticket", message=state["message"])

    if not tool_result.success:
        steps.append("create_ticket_error")
        return {
            "answer": "创建工单时发生错误，请稍后再试。",
            "response_type": "ticket_created",
            "workflow_steps": steps,
        }

    ticket_data = tool_result.data or {}
    ticket = Ticket(**ticket_data["ticket"])
    steps.append("ticket_created")
    return {
        "ticket": ticket,
        "answer": "我没有在知识库中找到足够明确的解决方案，已为你创建 IT 支持工单。",
        "response_type": "ticket_created",
        "workflow_steps": steps,
    }

from langgraph.graph import StateGraph, START, END


# ---- 条件边路由函数：读 state 里的数据，返回下一个节点名 ----

def route_after_extract(state: GraphState) -> str:  # 函数：有工单号 → 查单，否则查范围。
    return "query_ticket" if state["ticket_id"] else "check_support_scope"


def route_after_scope(state: GraphState) -> str:  # 函数：范围内 → 检索知识库，否则 → 拦截节点。
    return "search_knowledge_base" if state["in_support_scope"] else "unsupported_question"


def route_after_kb(state: GraphState) -> str:  # 函数：按关键词检索分数分流：高置信/澄清/向量。
    results = state["knowledge_results"]
    if _has_confident_rule_answer(state["message"], results):
        return "answer_high_confidence"
    if results and results[0].score > 0:
        return "clarify"
    return "search_vector_store"


def route_after_vector(state: GraphState) -> str:  # 函数：向量命中达阈值 → 澄清，否则建单。
    results = state["vector_results"]

    if (
        results
        and results[0].score >= VECTOR_FALLBACK_THRESHOLD
        and results[0].score >= 1.0
    ):
        return "vector_answer"

    if results and results[0].score >= VECTOR_FALLBACK_THRESHOLD:
        return "vector_clarify"
    return "create_ticket"


# ---- 组装图 ----

builder = StateGraph(GraphState)
builder.add_node("extract_ticket_id", extract_ticket_id)
builder.add_node("query_ticket", query_ticket)
builder.add_node("check_support_scope", check_support_scope)
builder.add_node("search_knowledge_base", search_knowledge_base)
builder.add_node("search_vector_store", search_vector_store)
builder.add_node("answer_high_confidence", answer_high_confidence)
builder.add_node("clarify", clarify)
builder.add_node("vector_answer", vector_answer)
builder.add_node("vector_clarify", vector_clarify)
builder.add_node("create_ticket", create_ticket)
builder.add_node("unsupported_question", unsupported_question)
builder.add_edge(START, "extract_ticket_id")

builder.add_conditional_edges(
    "extract_ticket_id",
    route_after_extract,
    {"query_ticket": "query_ticket", "check_support_scope": "check_support_scope"},
)

builder.add_edge("query_ticket", END)

builder.add_conditional_edges(
    "check_support_scope",
    route_after_scope,
    {"search_knowledge_base": "search_knowledge_base", "unsupported_question": "unsupported_question"},
)

builder.add_edge("unsupported_question", END)

builder.add_conditional_edges(
    "search_knowledge_base",
    route_after_kb,
    {
        "answer_high_confidence": "answer_high_confidence",
        "clarify": "clarify",
        "search_vector_store": "search_vector_store",
    },
)

builder.add_edge("unsupported_question", END)

builder.add_conditional_edges(
    "search_vector_store",
    route_after_vector,
    {
        "vector_answer": "vector_answer",
        "vector_clarify": "vector_clarify",
        "create_ticket": "create_ticket",
    },
)
builder.add_edge("answer_high_confidence", END)
builder.add_edge("clarify", END)
builder.add_edge("vector_answer", END)
builder.add_edge("vector_clarify", END)
builder.add_edge("create_ticket", END)

graph = builder.compile()


from uuid import uuid4
from app.models import ChatResponse


def build_chat_response(state: GraphState) -> ChatResponse:  # 函数：从图结果构造统一响应，字段与 agent.py 完全一致。
    if not state.get("response_type"):
        raise ValueError("response_type is required before building ChatResponse")

    return ChatResponse(
        request_id=state.get("request_id") or str(uuid4()),
        type=state["response_type"],
        answer=state["answer"],
        sources=state["sources"],
        ticket=state["ticket"],
        workflow_steps=state["workflow_steps"],
        harness_trace=(
            [step.model_dump() for step in state["harness_session"].trace_steps]
            if state.get("harness_session") is not None
            else []
        ),
    )


def _handle_message_core(
    message: str,
    request_id: str | None = None,
) -> ChatResponse:  # 函数：LangGraph 版入口：初始化状态、运行图、构造响应。
    initial: GraphState = {
        "request_id": request_id or str(uuid4()),
        "message": message,
        "ticket_id": None,
        "in_support_scope": True,
        "knowledge_results": [],
        "vector_results": [],
        "sources": [],
        "ticket": None,
        "answer": None,
        "response_type": None,
        "workflow_steps": [],
        "harness_session": (
            create_harness_session(
                request_id=request_id,
                engine="langgraph",
                max_steps=get_agent_harness_max_steps(),
            )
            if is_agent_harness_enabled()
            else None
        ),
    }
    result = graph.invoke(initial)
    return build_chat_response(result)


def handle_message(
    message: str,
    request_id: str | None = None,
) -> ChatResponse:
    """LangGraph 编排入口：复用与规则引擎一致的运行时治理。"""
    from app.agent_runtime import execute_agent_request

    return execute_agent_request(
        message,
        request_id,
        "langgraph",
        _handle_message_core,
    )
