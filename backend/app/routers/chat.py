# 模块职责：聊天接口路由模块：定义接收 ChatRequest 并调用核心 Agent 的 HTTP 接口。
# 支持 rules（if/else 路由）与 langgraph（状态图路由）两种编排引擎，由 AGENT_ENGINE 环境变量切换。

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from time import perf_counter

from app.agent import ChatResponse, handle_message as handle_rules_message
from app.models import ChatRequest
from app.config import get_agent_engine
from app.observability import get_request_id
from fastapi import HTTPException, APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def _resolve_handler():  # 函数：按 AGENT_ENGINE 选择规则版或 LangGraph 版消息处理器。
    if get_agent_engine() == "langgraph":
        from app.graph_agent import handle_message as handle_graph_message
        return handle_graph_message
    return handle_rules_message


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:  # 函数：负责 聊天 相关逻辑。
    try:
        return _resolve_handler()(
            request.message,
            request_id=get_request_id(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _sse_event(event: str, payload: dict) -> str:
    """按 SSE 协议将事件名和 JSON 数据编码为一个消息帧。"""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _answer_chunks(answer: str, chunk_size: int = 24) -> list[str]:
    """按字符切分完整回答，供当前同步 Agent 以稳定的 SSE 分片输出。"""
    return [answer[index : index + chunk_size] for index in range(0, len(answer), chunk_size)]


@router.post("/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """以 SSE 推送聊天执行状态、回答分片及完整结构化结果。"""
    request_id = get_request_id()

    async def event_stream() -> AsyncIterator[str]:
        stream_started_at = perf_counter()
        yield _sse_event("meta", {"request_id": request_id})
        yield _sse_event("status", {"message": "正在检索知识库并规划处理路径..."})

        try:
            response = await asyncio.to_thread(
                _resolve_handler(),
                request.message,
                request_id=request_id,
            )
        except asyncio.CancelledError:
            logger.info("chat_stream_cancelled")
            raise
        except Exception:
            logger.exception("chat_stream_failed")
            yield _sse_event(
                "error",
                {"code": "chat_stream_failed", "detail": "处理请求时发生错误，请稍后重试。"},
            )
            return

        answer = response.answer or "当前请求已处理，但没有可展示的文本回答。"
        yield _sse_event("status", {"message": "回答已生成，正在传输..."})
        for chunk in _answer_chunks(answer):
            yield _sse_event("message_delta", {"delta": chunk})
            await asyncio.sleep(0)

        yield _sse_event("workflow", {"steps": response.workflow_steps})
        yield _sse_event("complete", response.model_dump(mode="json"))
        logger.info(
            "chat_stream_completed request_id=%s duration_ms=%s",
            request_id,
            round((perf_counter() - stream_started_at) * 1000, 2),
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
