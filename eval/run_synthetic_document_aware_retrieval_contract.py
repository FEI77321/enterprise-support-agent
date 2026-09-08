# 模块职责：为 document-aware synthetic lexical 检索策略提供回归契约。
# 仅运行 isolated synthetic 评估，不调用主 Agent、不读写 Chroma。

from __future__ import annotations

from run_synthetic_lexical_retrieval_eval import (
    DOCUMENT_AWARE_LEXICAL,
    main as evaluate_strategy,
)


EXPECTED_ANSWER_CASE_COUNT = 16
MINIMUM_RECALL_AT_3 = 1.0
MINIMUM_MRR_AT_3 = 0.9270
MINIMUM_NDCG_AT_3 = 0.9450
MAXIMUM_FALSE_POSITIVE_RATE_AT_3 = 0.0


def assert_at_least(
    metric_name: str,
    actual: float,
    expected_minimum: float,
) -> None:
    """断言指标不低于可接受下限。"""

    if actual < expected_minimum:
        raise AssertionError(
            f"{metric_name} regressed: "
            f"actual={actual:.4f}, "
            f"minimum={expected_minimum:.4f}"
        )

    print(
        f"PASS {metric_name}: "
        f"{actual:.4f} >= {expected_minimum:.4f}"
    )


def assert_at_most(
    metric_name: str,
    actual: float,
    expected_maximum: float,
) -> None:
    """断言风险指标不高于可接受上限。"""

    if actual > expected_maximum:
        raise AssertionError(
            f"{metric_name} regressed: "
            f"actual={actual:.4f}, "
            f"maximum={expected_maximum:.4f}"
        )

    print(
        f"PASS {metric_name}: "
        f"{actual:.4f} <= {expected_maximum:.4f}"
    )


def main() -> None:
    metrics = evaluate_strategy(
        strategy=DOCUMENT_AWARE_LEXICAL,
    )

    if metrics.answer_case_count != EXPECTED_ANSWER_CASE_COUNT:
        raise AssertionError(
            "answer case count changed: "
            f"actual={metrics.answer_case_count}, "
            f"expected={EXPECTED_ANSWER_CASE_COUNT}"
        )

    print(
        "PASS answer_case_count: "
        f"{metrics.answer_case_count}"
    )

    assert_at_least(
        metric_name="Macro Recall@3",
        actual=metrics.macro_recall_at_3,
        expected_minimum=MINIMUM_RECALL_AT_3,
    )
    assert_at_least(
        metric_name="Macro MRR@3",
        actual=metrics.macro_mrr_at_3,
        expected_minimum=MINIMUM_MRR_AT_3,
    )
    assert_at_least(
        metric_name="Macro nDCG@3",
        actual=metrics.macro_ndcg_at_3,
        expected_minimum=MINIMUM_NDCG_AT_3,
    )
    assert_at_most(
        metric_name="False Positive Rate@3",
        actual=metrics.false_positive_rate_at_3,
        expected_maximum=MAXIMUM_FALSE_POSITIVE_RATE_AT_3,
    )

    if not metrics.ocr_candidate_pool_isolated:
        raise AssertionError(
            "OCR-only documents appeared in the candidate pool"
        )

    print("PASS OCR candidate-pool isolation")
    print()
    print(
        "Document-aware lexical retrieval contract: Passed"
    )


if __name__ == "__main__":
    main()
