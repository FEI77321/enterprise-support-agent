# 模块职责：SSE 接口评估：验证流式事件顺序、请求追踪 ID、回答分片重组和最终结构化结果。

import logging
import os
import warnings

from eval_path import setup_backend_path


warnings.filterwarnings("ignore", message=".*starlette.testclient.*")
setup_backend_path()

from fastapi.testclient import TestClient

from app.main import app


logging.getLogger("httpx").setLevel(logging.WARNING)
client = TestClient(app)


def parse_sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in body.strip().split("\n\n"):
        lines = frame.splitlines()
        event = next(line.removeprefix("event: ") for line in lines if line.startswith("event: "))
        data = next(line.removeprefix("data: ") for line in lines if line.startswith("data: "))
        import json
        events.append((event, json.loads(data)))
    return events


def test_chat_stream_contract() -> None:
    request_id = "p2-sse-stream"
    old_enable_llm = os.environ.get("ENABLE_LLM_ANSWER")
    os.environ["ENABLE_LLM_ANSWER"] = "false"
    try:
        response = client.post(
            "/chat/stream",
            headers={"X-Request-ID": request_id},
            json={"message": "VPN 720 错误怎么办"},
        )
    finally:
        if old_enable_llm is None:
            os.environ.pop("ENABLE_LLM_ANSWER", None)
        else:
            os.environ["ENABLE_LLM_ANSWER"] = old_enable_llm

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse_events(response.text)
    assert events[0] == ("meta", {"request_id": request_id})
    assert events[1][0] == "status"
    assert events[-1][0] == "complete"

    streamed_answer = "".join(
        payload["delta"] for event, payload in events if event == "message_delta"
    )
    complete_response = events[-1][1]
    assert streamed_answer == complete_response["answer"]
    assert complete_response["request_id"] == request_id
    assert "search_knowledge_base" in complete_response["workflow_steps"]


def main() -> None:
    test_chat_stream_contract()
    print("PASS chat_stream_contract")
    print("Passed: 1/1")


if __name__ == "__main__":
    main()
