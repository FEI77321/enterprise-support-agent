# 模块职责：FastAPI 应用入口：创建服务实例，挂载聊天、工单和工具调用接口，并提供健康检查与版本信息等基础服务能力。

import logging
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from app.logger import configure_logging
from app.observability import (
    reset_request_id,
    resolve_request_id,
    set_request_id,
)
from app.routers.tickets import router as tickets_router
from app.routers.chat import router as chat_router
from app.routers.traces import router as traces_router
from app.routers.bad_cases import router as bad_cases_router
from app.routers.prompts import router as prompts_router
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
from app.redis_client import (
    close_redis_connection,
    get_redis_health_status,
    initialize_redis_connection,
)
from app.rate_limiter import check_rate_limit, requires_rate_limit
from app.access_control import reset_current_actor, resolve_actor, set_current_actor
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
configure_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_app: FastAPI):  # 函数：在 FastAPI 服务启动时初始化数据库，并在服务关闭前保留扩展位置。
    initialize_database()
    await initialize_redis_connection()

    try:
        yield
    finally:
        await close_redis_connection()

app = FastAPI(
    title="Enterprise Support Agent",
    description="企业知识库与工单处理智能体的最小规则版",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def trace_request(request: Request, call_next):
    request_id = resolve_request_id(request.headers.get("X-Request-ID"))
    token = set_request_id(request_id)
    started_at = perf_counter()
    decision = None

    try:
        if requires_rate_limit(request.url.path):
            decision = await check_rate_limit(request)
            if decision.allowed:
                response = await call_next(request)
            else:
                logger.warning(
                    "rate_limit_exceeded path=%s retry_after_seconds=%s",
                    request.url.path,
                    decision.retry_after_seconds,
                )
                response = JSONResponse(
                    status_code=429,
                    content={
                        "code": "rate_limit_exceeded",
                        "detail": "请求过于频繁，请稍后重试。",
                    },
                    headers={"Retry-After": str(decision.retry_after_seconds)},
                )
        else:
            response = await call_next(request)
    except Exception:
        logger.exception(
            "http_request_failed method=%s path=%s",
            request.method,
            request.url.path,
        )
        raise
    else:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        if decision and decision.limit is not None:
            response.headers["X-RateLimit-Limit"] = str(decision.limit)
            response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
            response.headers["X-RateLimit-Reset"] = str(
                decision.reset_after_seconds,
            )
        logger.info(
            "http_request_completed method=%s path=%s status_code=%s duration_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
    finally:
        reset_request_id(token)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Retry-After",
        "X-Request-ID",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ],
)

app.include_router(tickets_router)
app.include_router(chat_router)
app.include_router(traces_router)
app.include_router(bad_cases_router)
app.include_router(prompts_router)



@app.get("/health",tags=["system"])
def health_check() -> dict[str, str]:  # 函数：负责 健康检查 check 相关逻辑。
    return {"status": "ok"}


@app.get("/health/redis", tags=["system"])
async def redis_health_check() -> dict[str, str]:
    status = await get_redis_health_status()
    if status["status"] == "unavailable":
        raise HTTPException(status_code=503, detail=status)
    return status


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
def tool_call_auto(
    request: ToolCallAutoRequest,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):  # 函数：负责 工具 调用 自动 相关逻辑。
    # 独立 Tool Calling demo 未接入真实 SSO 时保留本地管理员沙箱；生产调用必须由网关注入身份头。
    token = set_current_actor(resolve_actor(x_actor_id or "system-admin", x_actor_role or "admin"))
    try:
        return handle_tool_call_auto_request(request)
    finally:
        reset_current_actor(token)


@app.post("/conversation-memory/clear")
def clear_conversation_memory(
    request: ConversationMemoryClearRequest,
) -> dict[str, str | bool]:
    return handle_clear_conversation_memory_request(request)
