# 模块职责：验证普通 Agent 与 LangGraph 对高置信向量命中
# 都能直接回答，且返回同一条实际证据。

from eval_path import setup_backend_path

setup_backend_path()

from app.agent import handle_message as handle_agent_message
from app.graph_agent import (
    handle_message as handle_graph_message,
)


QUERY = "虚拟网卡驱动"
EXPECTED_CHUNK_ID = "vpn_guide.md::chunk-6"


def evaluate(name: str, response) -> tuple[bool, str]:
    """检查单条 Agent 响应。"""
    if response.type != "answer":
        return False, f"{name} 期望 answer，实际 {response.type}"

    actual_chunk_ids = [
        source.chunk_id
        for source in response.sources
    ]

    if actual_chunk_ids != [EXPECTED_CHUNK_ID]:
        return (
            False,
            f"{name} 期望唯一来源 [{EXPECTED_CHUNK_ID}]，"
            f"实际 {actual_chunk_ids}",
        )

    if EXPECTED_CHUNK_ID not in response.answer:
        return False, f"{name} 回答正文没有引用 {EXPECTED_CHUNK_ID}"

    if "重装虚拟网卡驱动" not in response.answer:
        return False, f"{name} 回答缺少虚拟网卡驱动处理建议"

    return True, ""


def main() -> None:
    responses = [
        ("普通 Agent", handle_agent_message(QUERY)),
        ("LangGraph", handle_graph_message(QUERY)),
    ]

    passed = 0

    for name, response in responses:
        ok, reason = evaluate(name, response)

        if ok:
            passed += 1
            print(f"PASS {name}: 高置信向量命中直接回答")
        else:
            print(f"FAIL {name}: {reason}")

    print()
    print(f"Vector answer parity eval: Passed {passed}/2")

    if passed != len(responses):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
