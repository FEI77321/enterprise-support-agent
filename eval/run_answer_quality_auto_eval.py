# 模块职责：自动检查知识库回答的基本质量与引用一致性。
# 注意：它不能完全替代人工判断 Faithfulness，
# 但能筛出回答为空、缺来源、引用不一致、流程步骤缺失等问题。

import json
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.agent import handle_message


CASES_PATH = Path(__file__).resolve().with_name(
    "answer_quality_cases.json"
)


def evaluate_case(case: dict) -> tuple[bool, list[str]]:
    """执行 Agent，并返回自动可检查的问题列表。"""
    response = handle_message(case["query"])
    problems: list[str] = []

    if response.type != "answer":
        problems.append(
            f"回答类型异常：期望 answer，实际 {response.type}"
        )

    if not response.answer or not response.answer.strip():
        problems.append("最终回答为空")

    if not response.sources:
        problems.append("没有返回 sources")

    source_chunk_ids = {
        source.chunk_id
        for source in response.sources
        if source.chunk_id
    }

    # 回答正文的引用必须来自 API sources。
    answer_references = [
        source.chunk_id
        for source in response.sources
        if (
            source.chunk_id
            and source.chunk_id in response.answer
        )
    ]

    if response.sources and not answer_references:
        problems.append(
            "回答正文没有引用任何 API source"
        )

    # 父块样本必须返回黄金集指定的父块。
    expected_context_chunk_id = case.get(
        "expected_context_chunk_id"
    )

    if (
        expected_context_chunk_id
        and expected_context_chunk_id not in source_chunk_ids
    ):
        problems.append(
            "未引用预期上下文块："
            f"{expected_context_chunk_id}"
        )

    # 流程/规则摘要题必须保留预先定义的关键内容。
    for expected_text in case.get(
        "expected_answer_contains",
        [],
    ):
        if expected_text not in response.answer:
            problems.append(
                f"回答缺少关键内容：{expected_text}"
            )

    return not problems, problems


def main() -> None:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = data["cases"]

    passed = 0

    for case in cases:
        ok, problems = evaluate_case(case)

        if ok:
            passed += 1
            print(f"PASS {case['id']}: 自动质量检查通过")
        else:
            print(f"FAIL {case['id']}:")
            for problem in problems:
                print(f"  - {problem}")

    print()
    print(
        f"Answer quality auto eval: "
        f"Passed {passed}/{len(cases)}"
    )

    if passed != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
