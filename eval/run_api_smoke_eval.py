# 模块职责：API 冒烟评估：通过 FastAPI TestClient 覆盖健康检查、版本、聊天成功响应和参数校验错误，确认服务接口最基本的可用性。

import os
import logging
import warnings

from eval_path import setup_backend_path

warnings.filterwarnings("ignore", message=".*starlette.testclient.*")

setup_backend_path()

from fastapi.testclient import TestClient


from app.main import app


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


def test_chat_validation_error() -> tuple[bool, str]:  # 测试函数：验证 聊天 validation 错误 场景。
    response = client.post("/chat", json={"message": "V"})

    if response.status_code != 422:
        return False, f"期望 /chat 参数校验失败 status_code=422，实际为 {response.status_code}"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("health", test_health),
        ("version", test_version),
        ("chat_answer", test_chat_answer),
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
