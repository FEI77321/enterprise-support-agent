# 模块职责：验证 Agent 返回的 sources 指向黄金集规定的上下文块。

import json
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.agent import handle_message


CASES_PATH = Path(__file__).resolve().with_name(
    "rag_eval_cases.json"
)


def evaluate_case(case: dict) -> tuple[bool, str]:
    """验证单个样本的 Agent 来源引用。"""
    response = handle_message(case["query"])
    expected_chunk_id = case["expected_context_chunk_id"]

    if response.type != "answer":
        return (
            False,
            f"期望 answer，实际为 {response.type}",
        )

    actual_chunk_ids = [
        source.chunk_id
        for source in response.sources
    ]

    if expected_chunk_id not in actual_chunk_ids:
        return (
            False,
            f"期望来源 {expected_chunk_id}，"
            f"实际为 {actual_chunk_ids}",
        )

    return True, ""


def main() -> None:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = [
        case
        for case in data["cases"]
        if case.get("expected_context_chunk_id")
    ]

    passed = 0

    for case in cases:
        ok, reason = evaluate_case(case)

        if ok:
            passed += 1
            print(
                f"PASS {case['id']}: "
                f"Agent sources 正确引用上下文块"
            )
        else:
            print(f"FAIL {case['id']}: {reason}")

    print()
    print(
        f"Parent chunk source eval: "
        f"Passed {passed}/{len(cases)}"
    )

    if passed != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()