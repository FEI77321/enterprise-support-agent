# 模块职责：评估纯向量检索的 Recall@3、MRR@3、nDCG@3。
# 用作更换 embedding 前后的可对比基线。

import json
import math
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.retrieval_fusion import search_hybrid

CASES_PATH = Path(__file__).resolve().with_name(
    "rag_eval_cases.json"
)
TOP_K = 3


def evaluate_vector_metrics(
    cases: list[dict],
    top_k: int,
) -> tuple[float, float, float]:
    """计算正例的 Macro Recall、MRR 与 nDCG。"""
    positive_cases = [
        case
        for case in cases
        if case["expect_retrieval"]
    ]

    recall_scores: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcg_scores: list[float] = []

    for case in positive_cases:
        results = search_hybrid(
            case["query"],
            top_k=top_k,
        )

        relevant_chunks = {
            item["chunk_id"]: item["relevance"]
            for item in case["relevant_chunks"]
        }

        retrieved_chunk_ids = [
            result.chunk_id
            for result in results
        ]

        hit_count = sum(
            chunk_id in relevant_chunks
            for chunk_id in retrieved_chunk_ids
        )
        recall_scores.append(
            hit_count / len(relevant_chunks)
        )

        reciprocal_rank = 0.0
        for rank, chunk_id in enumerate(
            retrieved_chunk_ids,
            start=1,
        ):
            if chunk_id in relevant_chunks:
                reciprocal_rank = 1 / rank
                break

        reciprocal_ranks.append(reciprocal_rank)

        dcg = 0.0
        for rank, chunk_id in enumerate(
            retrieved_chunk_ids,
            start=1,
        ):
            relevance = relevant_chunks.get(chunk_id, 0)
            dcg += (
                (2 ** relevance - 1)
                / math.log2(rank + 1)
            )

        ideal_relevances = sorted(
            relevant_chunks.values(),
            reverse=True,
        )[:top_k]

        idcg = sum(
            (2 ** relevance - 1)
            / math.log2(rank + 1)
            for rank, relevance in enumerate(
                ideal_relevances,
                start=1,
            )
        )

        ndcg_scores.append(dcg / idcg if idcg else 0.0)

        print(
            f"{case['id']}: "
            f"chunks={retrieved_chunk_ids} | "
            f"Recall@{top_k}={recall_scores[-1]:.2f} | "
            f"MRR@{top_k}={reciprocal_rank:.4f} | "
            f"nDCG@{top_k}={ndcg_scores[-1]:.4f}"
        )

    return (
        sum(recall_scores) / len(recall_scores),
        sum(reciprocal_ranks) / len(reciprocal_ranks),
        sum(ndcg_scores) / len(ndcg_scores),
    )


def main() -> None:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    recall, mrr, ndcg = evaluate_vector_metrics(
        data["cases"],
        TOP_K,
    )

    print()
    print(f"Hybrid Macro Recall@{TOP_K}: {recall:.4f}")
    print(f"Hybrid MRR@{TOP_K}: {mrr:.4f}")
    print(f"Hybrid nDCG@{TOP_K}: {ndcg:.4f}")


if __name__ == "__main__":
    main()