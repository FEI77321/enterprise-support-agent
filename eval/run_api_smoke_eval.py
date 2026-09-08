# 模块职责：API 冒烟评估：通过 FastAPI TestClient 覆盖健康检查、版本、聊天成功响应和参数校验错误，确认服务接口最基本的可用性。

import os
import logging
import warnings
from unittest.mock import AsyncMock, patch

from eval_path import setup_backend_path

warnings.filterwarnings("ignore", message=".*starlette.testclient.*")

setup_backend_path()

from fastapi.testclient import TestClient


from app.main import app
from app.rate_limiter import RateLimitDecision


logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("app.agent").setLevel(logging.WARNING)
logging.getLogger("app.tool_registry").setLevel(logging.WARNING)

client = TestClient(app)


def test_health() -> tuple[bool, str]:  # 测试函数：验证 健康检查 场景。
    response = client.get("/health")

    if response.status_code != 200:
        return False, f"期望 /health status_code=200，实际为 {response.status_code}"

    if response.json() != {"status": "ok"}:
        return False, f"期望 /health 返回 status=ok，实际为 {response.json()}"

    return True, ""


def test_redis_health_when_disabled() -> tuple[bool, str]:
    old_redis_enabled = os.environ.get("REDIS_ENABLED")
    os.environ["REDIS_ENABLED"] = "false"
    try:
        response = client.get("/health/redis")
    finally:
        if old_redis_enabled is None:
            os.environ.pop("REDIS_ENABLED", None)
        else:
            os.environ["REDIS_ENABLED"] = old_redis_enabled

    if response.status_code != 200:
        return False, f"期望 /health/redis status_code=200，实际为 {response.status_code}"

    if response.json() != {"status": "disabled"}:
        return False, f"期望 Redis 关闭状态，实际为 {response.json()}"

    return True, ""


def test_request_id_header() -> tuple[bool, str]:
    request_id = "p2-trace-health"
    response = client.get(
        "/health",
        headers={"X-Request-ID": request_id},
    )

    if response.headers.get("X-Request-ID") != request_id:
        return False, (
            "期望响应透传 X-Request-ID="
            f"{request_id}，实际为 "
            f"{response.headers.get('X-Request-ID')}"
        )

    return True, ""


def test_rate_limit_response() -> tuple[bool, str]:
    request_id = "p2-rate-limit"
    with patch(
        "app.main.check_rate_limit",
        new=AsyncMock(
            return_value=RateLimitDecision(
                allowed=False,
                retry_after_seconds=12,
                limit=60,
                remaining=0,
                reset_after_seconds=12,
            )
        ),
    ):
        response = client.post(
            "/chat",
            headers={"X-Request-ID": request_id},
            json={"message": "VPN 720 错误怎么办"},
        )

    if response.status_code != 429:
        return False, f"期望限流状态码 429，实际为 {response.status_code}"

    if response.headers.get("Retry-After") != "12":
        return False, f"期望 Retry-After=12，实际为 {response.headers.get('Retry-After')}"

    if response.headers.get("X-RateLimit-Remaining") != "0":
        return False, "限流响应未返回剩余额度"

    if response.headers.get("X-Request-ID") != request_id:
        return False, "限流响应未透传 X-Request-ID"

    if response.json().get("code") != "rate_limit_exceeded":
        return False, f"期望限流错误码，实际为 {response.json()}"

    return True, ""


def test_version() -> tuple[bool, str]:  # 测试函数：验证 版本 场景。
    response = client.get("/version")

    if response.status_code != 200:
        return False, f"期望 /version status_code=200，实际为 {response.status_code}"

    data = response.json()
    if data.get("code") != 0:
        return False, f"期望 /version code=0，实际为 {data}"

    version_data = data.get("data") or {}
    if version_data.get("name") != "Enterprise Support Agent":
        return False, f"期望 /version 返回项目名称，实际为 {data}"

    return True, ""


def test_chat_answer() -> tuple[bool, str]:  # 测试函数：验证 聊天 回答 场景。
    old_enable_llm = os.environ.get("ENABLE_LLM_ANSWER")
    os.environ["ENABLE_LLM_ANSWER"] = "false"

    try:
        response = client.post("/chat", json={"message": "VPN 720 错误怎么办"})
    finally:
        if old_enable_llm is None:
            os.environ.pop("ENABLE_LLM_ANSWER", None)
        else:
            os.environ["ENABLE_LLM_ANSWER"] = old_enable_llm

    if response.status_code != 200:
        return False, f"期望 /chat status_code=200，实际为 {response.status_code}, body={response.text}"

    data = response.json()
    if data.get("type") != "answer":
        return False, f"期望 /chat type=answer，实际为 {data}"

    source_files = {source.get("file") for source in data.get("sources", [])}
    if "vpn_guide.md" not in source_files:
        return False, f"期望 /chat sources 包含 vpn_guide.md，实际为 {data.get('sources')}"

    workflow_steps = data.get("workflow_steps", [])
    if "search_knowledge_base" not in workflow_steps:
        return False, f"期望 /chat workflow_steps 包含 search_knowledge_base，实际为 {workflow_steps}"

    return True, ""


def test_chat_request_id_matches_trace() -> tuple[bool, str]:
    request_id = "p2-trace-chat"
    old_enable_llm = os.environ.get("ENABLE_LLM_ANSWER")
    os.environ["ENABLE_LLM_ANSWER"] = "false"

    try:
        response = client.post(
            "/chat",
            headers={"X-Request-ID": request_id},
            json={"message": "VPN 720 错误怎么办"},
        )
    finally:
        if old_enable_llm is None:
            os.environ.pop("ENABLE_LLM_ANSWER", None)
        else:
            os.environ["ENABLE_LLM_ANSWER"] = old_enable_llm

    if response.status_code != 200:
        return False, f"/chat 请求失败：{response.status_code}"

    actual_request_id = response.json().get("request_id")
    if actual_request_id != request_id:
        return False, (
            f"期望 ChatResponse.request_id={request_id}，"
            f"实际为 {actual_request_id}"
        )

    return True, ""


def test_langgraph_request_id_matches_trace() -> tuple[bool, str]:
    request_id = "p2-trace-langgraph"
    old_enable_llm = os.environ.get("ENABLE_LLM_ANSWER")
    old_agent_engine = os.environ.get("AGENT_ENGINE")
    os.environ["ENABLE_LLM_ANSWER"] = "false"
    os.environ["AGENT_ENGINE"] = "langgraph"

    try:
        response = client.post(
            "/chat",
            headers={"X-Request-ID": request_id},
            json={"message": "VPN 720 错误怎么办"},
        )
    finally:
        if old_enable_llm is None:
            os.environ.pop("ENABLE_LLM_ANSWER", None)
        else:
            os.environ["ENABLE_LLM_ANSWER"] = old_enable_llm

        if old_agent_engine is None:
            os.environ.pop("AGENT_ENGINE", None)
        else:
            os.environ["AGENT_ENGINE"] = old_agent_engine

    if response.status_code != 200:
        return False, f"LangGraph /chat 请求失败：{response.status_code}"

    actual_request_id = response.json().get("request_id")
    if actual_request_id != request_id:
        return False, (
            f"期望 LangGraph ChatResponse.request_id={request_id}，"
            f"实际为 {actual_request_id}"
        )

    return True, ""


def test_chat_validation_error() -> tuple[bool, str]:  # 测试函数：验证 聊天 validation 错误 场景。
    response = client.post("/chat", json={"message": "V"})

    if response.status_code != 422:
        return False, f"期望 /chat 参数校验失败 status_code=422，实际为 {response.status_code}"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("health", test_health),
        ("redis_health_when_disabled", test_redis_health_when_disabled),
        ("request_id_header", test_request_id_header),
        ("rate_limit_response", test_rate_limit_response),
        ("version", test_version),
        ("chat_answer", test_chat_answer),
        ("chat_request_id_matches_trace", test_chat_request_id_matches_trace),
        ("langgraph_request_id_matches_trace", test_langgraph_request_id_matches_trace),
        ("chat_validation_error", test_chat_validation_error),
    ]

    passed = 0

    for name, test_func in tests:
        ok, reason = test_func()
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}")

        if ok:
            passed += 1
        else:
            print(f"  Reason: {reason}")

    print()
    print(f"Passed: {passed}/{len(tests)}")

    if passed != len(tests):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
