# 模块职责：聊天接口路由模块：定义接收 ChatRequest 并调用核心 Agent 的 HTTP 接口。
# 支持 rules（if/else 路由）与 langgraph（状态图路由）两种编排引擎，由 AGENT_ENGINE 环境变量切换。

from app.agent import ChatResponse, handle_message as handle_rules_message
from app.models import ChatRequest
from app.config import get_agent_engine
from fastapi import HTTPException, APIRouter

router = APIRouter(prefix="/chat", tags=["chat"])


def _resolve_handler():  # 函数：按 AGENT_ENGINE 选择规则版或 LangGraph 版消息处理器。
    if get_agent_engine() == "langgraph":
        from app.graph_agent import handle_message as handle_graph_message
        return handle_graph_message
    return handle_rules_message


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:  # 函数：负责 聊天 相关逻辑。
    try:
        return _resolve_handler()(request.message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
