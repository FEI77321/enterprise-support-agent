# 模块职责：FastAPI 应用入口：创建服务实例，挂载聊天、工单和工具调用接口，并提供健康检查与版本信息等基础服务能力。

from urllib import response
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from app.logger import configure_logging
from app.routers.tickets import router as tickets_router
from app.routers.chat import router as chat_router
from app.tool_call_routes import (
    ConversationMemoryClearRequest,
    ToolCallAutoRequest,
    ToolCallDemoRequest,
    handle_clear_conversation_memory_request,
    handle_tool_call_auto_request,
    handle_tool_call_demo_request,
)
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.database import initialize_database
from app.models import VersionInfo,VersionResponse
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
configure_logging()

@asynccontextmanager
async def lifespan(_app: FastAPI):  # 函数：在 FastAPI 服务启动时初始化数据库，并在服务关闭前保留扩展位置。
    initialize_database()

    yield

app = FastAPI(
    title="Enterprise Support Agent",
    description="企业知识库与工单处理智能体的最小规则版",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tickets_router)
app.include_router(chat_router)



@app.get("/health",tags=["system"])
def health_check() -> dict[str, str]:  # 函数：负责 健康检查 check 相关逻辑。
    return {"status": "ok"}


@app.get("/version",tags=["system"],response_model=VersionResponse)
def get_version() -> VersionResponse:  # 函数：负责 获取 版本 相关逻辑。
    return VersionResponse(
        code=0,
        message="success",
        data=VersionInfo(
            name="Enterprise Support Agent",
            version="0.1.0",
        ),
    )


@app.post("/tool-call/demo")
def tool_call_demo(request: ToolCallDemoRequest):  # 函数：负责 工具 调用 demo 相关逻辑。
    return handle_tool_call_demo_request(request)


@app.post("/tool-call/auto")
def tool_call_auto(request: ToolCallAutoRequest):  # 函数：负责 工具 调用 自动 相关逻辑。
    return handle_tool_call_auto_request(request)


@app.post("/conversation-memory/clear")
def clear_conversation_memory(
    request: ConversationMemoryClearRequest,
) -> dict[str, str | bool]:
    return handle_clear_conversation_memory_request(request)