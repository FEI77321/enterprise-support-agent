# 模块职责：验证 LangGraph Agent 的完整回答与来源引用，
# 是否符合黄金集规定的父上下文块。

import json
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.graph_agent import handle_message


CASES_PATH = Path(__file__).resolve().with_name(
    "rag_eval_cases.json"
)


def evaluate_case(case: dict) -> tuple[bool, str]:
    """验证单个父块样本的 LangGraph 最终回答。"""
    response = handle_message(case["query"])
    expected_chunk_id = case["expected_context_chunk_id"]

    if response.type != "answer":
        return False, f"期望 answer，实际为 {response.type}"

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

    missing_items = [
        item
        for item in case["expected_answer_contains"]
        if item not in response.answer
    ]

    if missing_items:
        return False, f"最终回答缺少：{missing_items}"

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
                f"LangGraph 回答完整且正确引用上下文块"
            )
        else:
            print(f"FAIL {case['id']}: {reason}")

    print()
    print(
        f"Parent chunk LangGraph eval: "
        f"Passed {passed}/{len(cases)}"
    )

    if passed != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()