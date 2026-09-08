# 模块职责：汇总回答质量人工标注的覆盖率与三项平均分。

import json
from pathlib import Path


CASES_PATH = Path(__file__).resolve().with_name(
    "answer_quality_cases.json"
)


def main() -> None:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = data["cases"]

    scored_cases = [
        case
        for case in cases
        if all(
            score is not None
            for score in case["manual_scores"].values()
        )
    ]

    print(f"回答质量样本总数: {len(cases)}")
    print(f"已完成人工标注: {len(scored_cases)}")
    print(f"待人工复核: {len(cases) - len(scored_cases)}")

    if not scored_cases:
        print("\n暂无完整人工标注，无法计算人工质量指标。")
        return

    metric_names = [
        "faithfulness",
        "answer_relevance",
        "citation_correctness",
    ]

    print()
    print("人工质量指标:")

    for metric_name in metric_names:
        total = sum(
            case["manual_scores"][metric_name]
            for case in scored_cases
        )
        score = total / len(scored_cases)

        print(
            f"- {metric_name}: "
            f"{total}/{len(scored_cases)} = {score:.4f}"
        )


if __name__ == "__main__":
    main()
