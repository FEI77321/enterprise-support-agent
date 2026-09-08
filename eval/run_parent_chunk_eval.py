# 模块职责：验证需要完整流程的 RAG 回答，是否包含黄金集规定的关键步骤。

import json
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.knowledge_base import build_answer, search_knowledge_base


CASES_PATH = Path(__file__).resolve().with_name("rag_eval_cases.json")


def evaluate_case(case: dict) -> tuple[bool, str]:
    """检索并生成回答，检查回答是否包含所有必需信息。"""
    results = search_knowledge_base(case["query"])
    answer = build_answer(case["query"], results)

    missing_items = [
        item
        for item in case["expected_answer_contains"]
        if item not in answer
    ]

    if missing_items:
        return (
            False,
            f"回答缺少：{missing_items}；实际回答：{answer}",
        )

    return True, ""


def main() -> None:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = [
        case
        for case in data["cases"]
        if case.get("expected_answer_contains")
    ]

    if not cases:
        raise ValueError("没有配置 expected_answer_contains 的流程题")

    passed = 0

    for case in cases:
        ok, reason = evaluate_case(case)

        if ok:
            passed += 1
            print(f"PASS {case['id']}: 回答包含全部关键步骤")
        else:
            print(f"FAIL {case['id']}: {reason}")

    print()
    print(f"Parent chunk eval: Passed {passed}/{len(cases)}")

    if passed != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()