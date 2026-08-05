# 模块职责：企业支持问答的核心编排模块：接收用户问题，决定检索知识库、查询或创建工单的处理路径，并把执行过程汇总为统一的聊天响应。

import logging
import os
import re
from uuid import uuid4
from app.vector_store import VectorSearchResult
from app.knowledge_base import build_answer, SearchResult
from app.models import ChatResponse, Source,Ticket
from app.prompt_builder import build_prompt
from app.llm_client import generate_answer_result
from app.tool_registry import run_tool
from app.agent_state import AgentState
from app.config import is_llm_answer_enabled

logger = logging.getLogger(__name__)
TICKET_PATTERN = re.compile(r"TICKET-\d{8}-\d{4}", re.IGNORECASE)
VECTOR_FALLBACK_THRESHOLD = 0.4
CITATION_PAIR_PATTERN = re.compile(
    r"File:\s*([^\s,]+)\s*,\s*Chunk ID:\s*([^\s,]+)",
    re.IGNORECASE,
)
SUPPORT_INTENT_KEYWORDS = [
        "vpn", "720", "691", "远程办公", "内网", "虚拟网卡",
        "账号", "登录", "密码", "验证码", "mfa", "锁定",
        "报销", "发票", "差旅", "审批",
        "请假", "年假", "调休", "病假",
        "蓝屏", "黑屏", "显示器", "屏幕", "打印机", "电脑", "故障", "无法", "开不了",
    ]

def _is_support_related(message: str) -> bool:  # 函数：判断用户问题是否属于企业支持 Agent 的处理范围。
        normalized = message.lower()
        return any(keyword.lower() in normalized for keyword in SUPPORT_INTENT_KEYWORDS)


def _has_valid_llm_citations(answer: str, sources: list[Source]) -> bool:  # 函数：验证 LLM 回答中的 File 和 Chunk ID 是否全部来自当前检索来源。
    cited_source_pairs = CITATION_PAIR_PATTERN.findall(answer)
    valid_source_pairs = {
        (source.file, source.chunk_id)
        for source in sources
    }

    return bool(cited_source_pairs) and all(
        source_pair in valid_source_pairs
        for source_pair in cited_source_pairs
    )


def handle_message(message: str) -> ChatResponse:  # 函数：负责 处理 消息 相关逻辑。
    state = AgentState(
        request_id=str(uuid4()),
        message=message,
    )

    logger.info("request_id=%s message=%s", state.request_id, message)

    ticket_id = _extract_ticket_id(message)
    state.ticket_id = ticket_id
    state.add_step("extract_ticket_id")
    #找id，如果有id，返回值，如果没有就去找message去检索
    if ticket_id:
        state.add_step("query_ticket_status")
        tool_result = run_tool("query_ticket_status", ticket_id=ticket_id)

        if not tool_result.success:
            state.add_step("query_ticket_error")
            logger.info(
                "request_id=%s action=query_ticket_error ticket_id=%s error=%s",
                state.request_id,
                ticket_id,
                tool_result.error,
            )
            state.answer = "查询工单状态时发生错误，请稍后再试。"
            state.response_type = "ticket_status"
            log_workflow(state)
            return build_chat_response(state)

        ticket_data = tool_result.data or {}

        if ticket_data.get("found"):
            state.add_step("ticket_status")
            ticket = Ticket(**ticket_data["ticket"])
            state.ticket = ticket
            state.answer = f"工单 {ticket.ticket_id} 当前状态为 {ticket.status}，处理人为 {ticket.assignee}。"
            logger.info("request_id=%s action=query_ticket ticket_id=%s", state.request_id, ticket.ticket_id,)
            state.response_type = "ticket_status"
            log_workflow(state)
            return build_chat_response(state)


        state.add_step("ticket_not_found")
        logger.info(
            "request_id=%s action=query_ticket_not_found ticket_id=%s",
            state.request_id,
            ticket_id,
        )
        state.answer = f"没有找到工单 {ticket_id}，请确认工单号是否正确。"
        state.response_type = "ticket_status"
        log_workflow(state)
        return build_chat_response(state)

    if not _is_support_related(message):
        state.add_step("unsupported_question")
        state.answer = (
            "这个问题不属于企业 IT 支持范围。我可以帮你处理 VPN、账号登录、MFA、"
            "报销、请假、蓝屏、打印机或 IT 工单相关问题。"
        )
        state.response_type = "clarify"
        log_workflow(state)
        return build_chat_response(state)


    state.add_step("search_knowledge_base")
    tool_result = run_tool("search_knowledge_base", query=message)

    if not tool_result.success:
        logger.info(
            "request_id=%s action=knowledge_search_error error=%s",
            state.request_id,
            tool_result.error,
        )
        state.knowledge_results = []
    else:
        search_data = tool_result.data or {}
        state.knowledge_results = [
            SearchResult(
                file=item["file"],
                content=item["content"],
                score=item["score"],
                chunk_id=item["chunk_id"],
            )
            for item in search_data.get("results", [])
        ]

    results = state.knowledge_results
    if results and results[0].score >= 6:
        sources = [
            Source(
                file=result.file,
                snippet=_snippet(result.content),
                score=result.score,
                chunk_id=result.chunk_id,
            )
            for result in results
        ]
        state.sources = sources

        answer = build_answer(message, results)
        state.add_step("rule_answer")
        prompt = build_prompt(message, sources)
        logger.debug("request_id=%s prompt=%s", state.request_id, prompt)
        if is_llm_answer_enabled():
            llm_result = generate_answer_result(prompt)
            state.add_step("llm_answer")

            if llm_result.success:
                if _has_valid_llm_citations(llm_result.answer, sources):
                    answer = llm_result.answer
                else:
                    cited_source_pairs = CITATION_PAIR_PATTERN.findall(
                        llm_result.answer
                    )
                    valid_source_pairs = [
                        (source.file, source.chunk_id)
                        for source in sources
                    ]

                    logger.warning(
                        "request_id=%s action=llm_invalid_citation_fallback "
                        "cited_source_pairs=%s valid_source_pairs=%s",
                        state.request_id,
                        cited_source_pairs,
                        valid_source_pairs,
                    )
                    state.add_step("llm_invalid_citation_fallback")
            else:
                state.add_step("llm_fallback_to_rule_answer")

        state.answer = answer
        state.add_step("knowledge_answer")
        logger.info(
            "request_id=%s action=knowledge_answer sources=%s",
            state.request_id,
            summarize_sources(sources),
        )
        state.response_type = "answer"
        log_workflow(state)
        return build_chat_response(state)


##上面分数大于6，就去.md里面找了
    if results and results[0].score > 0:
        sources = [
            Source(
                file=result.file,
                snippet=_snippet(result.content),
                score=result.score,
                chunk_id=result.chunk_id,
            )
            for result in results
        ]
        state.sources = sources
        prompt = build_prompt(message, sources)
        logger.debug("request_id=%s prompt=%s", state.request_id, prompt)
        state.add_step("clarify")
        logger.info(
            "request_id=%s action=clarify sources=%s",
            state.request_id,
            summarize_sources(sources),
        )
        state.answer = "我找到了一些可能相关的信息，但还不太确定。你可以补充一下具体场景吗？例如是 VPN、账号登录、报销、请假，还是其他问题？"
        state.response_type = "clarify"
        log_workflow(state)
        return build_chat_response(state)


##分数小于六但是大于0，就是clarify
    state.add_step("search_vector_store")
    tool_result = run_tool("search_vector_store", query=message)

    if not tool_result.success:
        logger.info(
            "request_id=%s action=vector_search_error error=%s",
            state.request_id,
            tool_result.error,
        )
        state.vector_results = []
    else:
        vector_data = tool_result.data or {}
        state.vector_results = [
            VectorSearchResult(
                file=item["file"],
                content=item["content"],
                score=item["score"],
                chunk_id=item["chunk_id"],
            )
            for item in vector_data.get("results", [])
        ]
    vector_results = state.vector_results
    if vector_results and vector_results[0].score >= VECTOR_FALLBACK_THRESHOLD:
        sources = [
            Source(
                file=result.file,
                snippet=_snippet(result.content),
                score=int(result.score * 100),
                chunk_id=result.chunk_id,
            )
            for result in vector_results
        ]
        state.sources = sources
        state.add_step("vector_clarify")
        logger.info(
            "request_id=%s action=vector_clarify sources=%s",
            state.request_id,
            summarize_sources(sources),
        )
        state.answer = "我找到了一些可能相关的知识片段，但还不太确定。你可以补充一下具体场景或错误信息吗？"
        state.response_type = "clarify"
        log_workflow(state)
        return build_chat_response(state)

##这上面是，找chunk

    state.add_step("create_ticket")
    tool_result = run_tool("create_ticket", message=message)

    if not tool_result.success:

        state.add_step("create_ticket_error")
        logger.info(
            "request_id=%s action=create_ticket_error error=%s",
            state.request_id,
            tool_result.error,
        )
        state.answer = "创建工单时发生错误，请稍后再试。"
        state.response_type = "ticket_created"
        log_workflow(state)
        return build_chat_response(state)

    ticket_data = tool_result.data or {}
    ticket = Ticket(**ticket_data["ticket"])
    state.ticket = ticket
    state.answer = "我没有在知识库中找到足够明确的解决方案，已为你创建 IT 支持工单。"
    state.add_step("ticket_created")
    logger.info("request_id=%s action=create_ticket ticket_id=%s", state.request_id, ticket.ticket_id)
    state.response_type = "ticket_created"
    log_workflow(state)
    return build_chat_response(state)

##这是自己建了
def _extract_ticket_id(message: str) -> str | None:  # 函数：负责 extract 工单 id 相关逻辑。
    match = TICKET_PATTERN.search(message)
    return match.group(0).upper() if match else None

def summarize_sources(sources: list[Source]) -> list[dict]:  # 函数：负责 汇总 sources 相关逻辑。
    return [
        {
            "file": source.file,
            "score": source.score,
            "chunk_id": source.chunk_id,
        }
        for source in sources
    ]

def build_chat_response(state: AgentState) -> ChatResponse:  # 函数：负责 构建 聊天 响应 相关逻辑。
    if state.response_type is None:
        raise ValueError("response_type is required before building ChatResponse")

    return ChatResponse(
        request_id=state.request_id,
        type=state.response_type,
        answer=state.answer,
        sources=state.sources,
        ticket=state.ticket,
        workflow_steps=state.workflow_steps,
    )


def log_workflow(state: AgentState) -> None:  # 函数：负责 log workflow 相关逻辑。
    logger.info(
        "request_id=%s response_type=%s workflow_steps=%s",
        state.request_id,
        state.response_type,
        state.workflow_steps,
    )



def _snippet(content: str, max_length: int = 120) -> str:  # 函数：负责 片段 相关逻辑。
    clean = " ".join(line.strip() for line in content.splitlines() if line.strip())
    return clean[:max_length]
