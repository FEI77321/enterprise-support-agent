# 模块职责：工具调用路由服务模块：承接 API 请求，调用自动或手动工具调用 Agent，并在携带 session_id 时把本轮用户消息和回答写入会话记忆。

from pydantic import BaseModel

from app.conversation_memory import add_turn, clear_memory
from app.tool_call_agent import (
    ToolCallAgentResponse,
    handle_tool_call_demo,
    handle_tool_call_demo_auto,
)


class ToolCallAutoRequest(BaseModel):  # 类：定义自动工具调用接口接收的消息和可选会话 ID。
    message: str
    session_id: str | None = None

class ConversationMemoryClearRequest(BaseModel):
    session_id: str


def handle_clear_conversation_memory_request(
    request: ConversationMemoryClearRequest,
) -> dict[str, str | bool]:
    clear_memory(request.session_id)

    return {
        "success": True,
        "session_id": request.session_id,
    }


def handle_tool_call_auto_request(
    request: ToolCallAutoRequest,
) -> ToolCallAgentResponse:  # 函数：负责 处理 工具 调用 自动 请求 相关逻辑。
    response = handle_tool_call_demo_auto(
        message=request.message,
        session_id=request.session_id,
    )

    if request.session_id:
        add_turn(
            session_id=request.session_id,
            role="user",
            content=request.message,
        )

        assistant_content = response.answer or response.error or ""

        add_turn(
            session_id=request.session_id,
            role="assistant",
            content=assistant_content,
        )

    return response


class ToolCallDemoRequest(BaseModel):  # 类：定义手动工具调用演示接口接收的原始模型输出。
    message: str
    llm_output: str####模拟大模型输出的 JSON


def handle_tool_call_demo_request(
    request: ToolCallDemoRequest,
) -> ToolCallAgentResponse:  # 函数：负责 处理 工具 调用 demo 请求 相关逻辑。
    return handle_tool_call_demo(
        message=request.message,
        llm_output=request.llm_output,
    )
