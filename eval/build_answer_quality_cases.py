# 模块职责：从 RAG 黄金集生成回答质量人工标注样本。

import json
from pathlib import Path


EVAL_DIR = Path(__file__).resolve().parent
GOLDEN_CASES_PATH = EVAL_DIR / "rag_eval_cases.json"
OUTPUT_PATH = EVAL_DIR / "answer_quality_cases.json"


def main() -> None:
    """抽取所有应当回答的知识库问题，生成待人工评分清单。"""
    golden_data = json.loads(
        GOLDEN_CASES_PATH.read_text(encoding="utf-8")
    )

    quality_cases = []

    for case in golden_data["cases"]:
        if not case["expect_retrieval"]:
            continue

        quality_cases.append(
            {
                "id": case["id"],
                "query": case["query"],
                "expected_file": case["expected_file"],
                "expected_context_chunk_id": case.get(
                    "expected_context_chunk_id"
                ),
                "expected_answer_contains": case.get(
                    "expected_answer_contains",
                    [],
                ),
                "manual_scores": {
                    "faithfulness": None,
                    "answer_relevance": None,
                    "citation_correctness": None,
                },
                "notes": "",
            }
        )

    OUTPUT_PATH.write_text(
        json.dumps(
            {"cases": quality_cases},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"已生成 {len(quality_cases)} 条回答质量样本："
        f"{OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
