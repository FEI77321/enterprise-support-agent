# 模块职责：计算 RAG 检索侧的 Recall@k。
# 当前只做 Recall@3；后续会在此脚本继续加入 MRR、nDCG 和误召回率。
import math
import json
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.knowledge_base import search_knowledge_base
from app.vector_store import search_vector_store


CASES_PATH = Path(__file__).resolve().with_name("rag_eval_cases.json")
TOP_K = 3


def retrieve(case: dict, top_k: int):
    """按用例指定的检索模式，返回前 top_k 条结果。"""
    query = case["query"]
    retrieval_mode = case.get("retrieval_mode", "keyword")

    if retrieval_mode == "keyword":
        return search_knowledge_base(query, top_k=top_k)

    if retrieval_mode == "vector":
        return search_vector_store(query, top_k=top_k)

    raise ValueError(f"不支持的 retrieval_mode: {retrieval_mode}")


def evaluate_recall_at_k(cases: list[dict], top_k: int) -> float:
    """计算所有正例的宏平均 Recall@k。"""
    positive_cases = [
        case for case in cases if case["expect_retrieval"]
    ]

    recall_scores: list[float] = []

    for case in positive_cases:
        results = retrieve(case, top_k)

        retrieved_chunk_ids = {
            result.chunk_id for result in results
        }
        relevant_chunk_ids = {
            item["chunk_id"] for item in case["relevant_chunks"]
        }

        hit_chunk_ids = retrieved_chunk_ids & relevant_chunk_ids
        recall = len(hit_chunk_ids) / len(relevant_chunk_ids)
        recall_scores.append(recall)

        status = "PASS" if recall == 1.0 else "PARTIAL"
        print(
            f"{status} {case['id']}: "
            f"Recall@{top_k}={recall:.2f} | "
            f"命中={sorted(hit_chunk_ids)} | "
            f"应命中={sorted(relevant_chunk_ids)}"
        )

    if not recall_scores:
        raise ValueError("没有可计算 Recall 的正例")

    return sum(recall_scores) / len(recall_scores)


def evaluate_false_positive_rate(
    cases: list[dict],
    top_k: int,
) -> float:
    """计算负例被错误检索到内容的比例。"""
    negative_cases = [
        case for case in cases
        if not case["expect_retrieval"]
    ]

    false_positive_count = 0

    for case in negative_cases:
        results = retrieve(case, top_k)

        if results:
            false_positive_count += 1
            retrieved_chunk_ids = [
                result.chunk_id for result in results
            ]
            print(
                f"FAIL {case['id']}: 发生误召回 | "
                f"错误返回={retrieved_chunk_ids}"
            )
        else:
            print(
                f"PASS {case['id']}: "
                f"正确拒绝检索"
            )

    if not negative_cases:
        raise ValueError("没有可计算误召回率的负例")

    return false_positive_count / len(negative_cases)


def evaluate_mrr_at_k(
    cases: list[dict],
    top_k: int,
) -> float:
    """计算所有正例的 Macro MRR@k。"""
    positive_cases = [
        case for case in cases
        if case["expect_retrieval"]
    ]

    reciprocal_ranks: list[float] = []

    for case in positive_cases:
        results = retrieve(case, top_k)

        relevant_chunk_ids = {
            item["chunk_id"]
            for item in case["relevant_chunks"]
        }

        reciprocal_rank = 0.0

        # enumerate(..., start=1) 表示排名从 1 开始，而不是 0。
        for rank, result in enumerate(results, start=1):
            if result.chunk_id in relevant_chunk_ids:
                reciprocal_rank = 1 / rank
                break  # 只关心第一个正确证据排第几。

        reciprocal_ranks.append(reciprocal_rank)

        print(
            f"{'PASS' if reciprocal_rank else 'FAIL'} "
            f"{case['id']}: "
            f"MRR@{top_k}={reciprocal_rank:.4f}"
        )

    if not reciprocal_ranks:
        raise ValueError("没有可计算 MRR 的正例")

    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def evaluate_ndcg_at_k(
    cases: list[dict],
    top_k: int,
) -> float:
    """计算所有正例的 Macro nDCG@k。"""
    positive_cases = [
        case for case in cases
        if case["expect_retrieval"]
    ]

    ndcg_scores: list[float] = []

    for case in positive_cases:
        results = retrieve(case, top_k)

        relevance_by_chunk_id = {
            item["chunk_id"]: item["relevance"]
            for item in case["relevant_chunks"]
        }

        dcg = 0.0

        for rank, result in enumerate(results, start=1):
            relevance = relevance_by_chunk_id.get(
                result.chunk_id,
                0,
            )
            dcg += (2 ** relevance - 1) / math.log2(rank + 1)

        ideal_relevances = sorted(
            relevance_by_chunk_id.values(),
            reverse=True,
        )[:top_k]

        ideal_dcg = sum(
            (2 ** relevance - 1) / math.log2(rank + 1)
            for rank, relevance in enumerate(
                ideal_relevances,
                start=1,
            )
        )

        ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
        ndcg_scores.append(ndcg)

        print(
            f"{'PASS' if ndcg == 1.0 else 'PARTIAL'} "
            f"{case['id']}: "
            f"nDCG@{top_k}={ndcg:.4f}"
        )

    if not ndcg_scores:
        raise ValueError("没有可计算 nDCG 的正例")

    return sum(ndcg_scores) / len(ndcg_scores)



def main() -> None:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = data["cases"]

    recall_at_3 = evaluate_recall_at_k(cases, TOP_K)
    false_positive_rate = evaluate_false_positive_rate(
        cases,
        TOP_K,
    )
    mrr_at_3 = evaluate_mrr_at_k(cases, TOP_K)
    ndcg_at_3 = evaluate_ndcg_at_k(cases, TOP_K)


    print()
    print(f"Macro Recall@{TOP_K}: {recall_at_3:.4f}")
    print(
        f"False Positive Rate@{TOP_K}: "
        f"{false_positive_rate:.4f}"
    )
    print(f"MRR@{TOP_K}: {mrr_at_3:.4f}")
    print(f"nDCG@{TOP_K}: {ndcg_at_3:.4f}")

if __name__ == "__main__":
    main()
