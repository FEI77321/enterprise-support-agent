# 模块职责：验证 Agent 对流程类问题的最终回答是否完整。

import json
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.agent import handle_message


CASES_PATH = Path(__file__).resolve().with_name(
    "rag_eval_cases.json"
)


def evaluate_case(case: dict) -> tuple[bool, str]:
    """调用 Agent，检查最终回答类型与关键步骤。"""
    response = handle_message(case["query"])

    if response.type != "answer":
        return (
            False,
            f"期望 answer，实际为 {response.type}",
        )

    missing_items = [
        item
        for item in case["expected_answer_contains"]
        if item not in response.answer
    ]

    if missing_items:
        return (
            False,
            f"最终回答缺少：{missing_items}",
        )

    return True, ""


def main() -> None:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = [
        case
        for case in data["cases"]
        if case.get("expected_answer_contains")
    ]

    passed = 0

    for case in cases:
        ok, reason = evaluate_case(case)

        if ok:
            passed += 1
            print(f"PASS {case['id']}: Agent 回答完整")
        else:
            print(f"FAIL {case['id']}: {reason}")

    print()
    print(f"RAG answer completeness eval: Passed {passed}/{len(cases)}")

    if passed != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()