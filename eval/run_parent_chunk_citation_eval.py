# 模块职责：验证流程题回答引用的是完整父块，而不是单个命中的子块。

import json
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.knowledge_base import build_answer, search_knowledge_base


CASES_PATH = Path(__file__).resolve().with_name(
    "rag_eval_cases.json"
)


def main() -> None:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    case = next(
        item
        for item in data["cases"]
        if item["id"] == "rag_007"
    )

    results = search_knowledge_base(case["query"])
    answer = build_answer(case["query"], results)

    expected_context_chunk_id = (
        "reimbursement_policy.md::parent-chunk-3"
    )

    if expected_context_chunk_id not in answer:
        print("FAIL rag_007: 引用没有指向完整流程父块")
        print(f"实际回答：{answer}")
        raise SystemExit(1)

    print("PASS rag_007: 引用正确指向完整流程父块")


if __name__ == "__main__":
    main()