# 模块职责：对 isolated synthetic Child Chunk 运行 lexical 检索基线，
# 使用动态 ground truth 计算 Recall@3、MRR@3、nDCG@3 和 FPR@3。
# 不调用主 Agent，不读写 Chroma，不替换现有线上检索链路。

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.knowledge_models import ChunkKind
from run_synthetic_ingestion_evidence_coverage_eval import (
    CORPUS_ROOT,
    ingest_synthetic_corpus,
    load_json,
)
from run_synthetic_retrieval_ready_contract import (
    ASSERTIONS_PATH,
    resolve_relevant_child_chunk_ids,
)
from synthetic_lexical_retriever import (
    search_synthetic_chunks,
    search_synthetic_chunks_document_aware,
)


MANIFEST_PATH = CORPUS_ROOT / "manifest.json"
GOLDEN_CASES_PATH = (
    CORPUS_ROOT
    / "synthetic_golden_cases_v1.json"
)

TOP_K = 3
MINIMUM_SCORE = 2.0
GLOBAL_CHILD_LEXICAL = "global_child_lexical"
DOCUMENT_AWARE_LEXICAL = "document_aware_lexical"
CANDIDATE_DOCUMENT_COUNT = 2


@dataclass(frozen=True)
class RetrievalMetrics:
    """一次 isolated synthetic 检索评估的汇总指标。"""

    strategy: str
    answer_case_count: int
    macro_recall_at_3: float
    macro_mrr_at_3: float
    macro_ndcg_at_3: float
    false_positive_rate_at_3: float
    ocr_candidate_pool_isolated: bool


def build_active_child_chunks(
    manifest: dict,
    ingested_documents: dict[str, dict],
) -> list:
    """返回未被新版本替代、且可用于检索的 Child Chunk。"""

    superseded_document_ids = {
        document["supersedes"]
        for document in manifest["documents"]
        if document.get("supersedes")
    }

    active_child_chunks = []

    for document_id, result in ingested_documents.items():
        if document_id in superseded_document_ids:
            continue

        for chunk in result["chunks"]:
            if chunk.kind == ChunkKind.CHILD:
                active_child_chunks.append(chunk)

    return active_child_chunks


def parse_args() -> argparse.Namespace:
    """读取本次评估要运行的隔离检索策略。"""

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate isolated synthetic lexical retrieval strategies."
        )
    )
    parser.add_argument(
        "--strategy",
        choices=[
            GLOBAL_CHILD_LEXICAL,
            DOCUMENT_AWARE_LEXICAL,
        ],
        default=GLOBAL_CHILD_LEXICAL,
        help=(
            "global_child_lexical: score every Child Chunk globally; "
            "document_aware_lexical: select candidate documents first."
        ),
    )

    return parser.parse_args()


def retrieve(
    query: str,
    active_child_chunks: list,
    strategy: str,
) -> list:
    """统一两个隔离策略的调用入口，保证评估逻辑完全一致。"""

    if strategy == GLOBAL_CHILD_LEXICAL:
        return search_synthetic_chunks(
            query=query,
            chunks=active_child_chunks,
            top_k=TOP_K,
            minimum_score=MINIMUM_SCORE,
        )

    if strategy == DOCUMENT_AWARE_LEXICAL:
        return search_synthetic_chunks_document_aware(
            query=query,
            chunks=active_child_chunks,
            top_k=TOP_K,
            minimum_score=MINIMUM_SCORE,
            candidate_document_count=CANDIDATE_DOCUMENT_COUNT,
        )

    raise ValueError(f"unsupported strategy: {strategy}")


def calculate_recall(
    retrieved_chunk_ids: list[str],
    relevant_chunk_ids: set[str],
) -> float:
    """计算单条正例的 Recall@K。"""

    hit_chunk_ids = (
        set(retrieved_chunk_ids)
        & relevant_chunk_ids
    )

    return len(hit_chunk_ids) / len(relevant_chunk_ids)


def calculate_mrr(
    retrieved_chunk_ids: list[str],
    relevant_chunk_ids: set[str],
) -> float:
    """计算单条正例的 MRR@K。"""

    for rank, chunk_id in enumerate(
        retrieved_chunk_ids,
        start=1,
    ):
        if chunk_id in relevant_chunk_ids:
            return 1 / rank

    return 0.0


def calculate_ndcg(
    retrieved_chunk_ids: list[str],
    relevant_chunk_ids: set[str],
) -> float:
    """计算单条正例的二元相关性 nDCG@K。"""

    dcg = 0.0

    for rank, chunk_id in enumerate(
        retrieved_chunk_ids,
        start=1,
    ):
        relevance = 3 if chunk_id in relevant_chunk_ids else 0
        dcg += (
            (2**relevance - 1)
            / math.log2(rank + 1)
        )

    ideal_relevances = [3] * min(
        len(relevant_chunk_ids),
        TOP_K,
    )
    ideal_dcg = sum(
        (2**relevance - 1)
        / math.log2(rank + 1)
        for rank, relevance in enumerate(
            ideal_relevances,
            start=1,
        )
    )

    return dcg / ideal_dcg if ideal_dcg else 0.0


def main(strategy: str) -> RetrievalMetrics:
    manifest = load_json(MANIFEST_PATH)
    golden_suite = load_json(GOLDEN_CASES_PATH)
    assertions = load_json(ASSERTIONS_PATH)

    if golden_suite["corpus_id"] != manifest["corpus_id"]:
        raise ValueError("golden suite and manifest corpus_id do not match")

    if assertions["corpus_id"] != manifest["corpus_id"]:
        raise ValueError("assertions and manifest corpus_id do not match")

    ingested_documents = ingest_synthetic_corpus(manifest)

    active_child_chunks = build_active_child_chunks(
        manifest=manifest,
        ingested_documents=ingested_documents,
    )

    answer_term_overrides = assertions[
        "answer_term_overrides"
    ]

    answer_cases = [
        case
        for case in golden_suite["cases"]
        if case["expected_action"] == "answer"
    ]
    refuse_cases = [
        case
        for case in golden_suite["cases"]
        if case["expected_action"] == "refuse"
    ]
    needs_ocr_cases = [
        case
        for case in golden_suite["cases"]
        if case["expected_action"] == "needs_ocr"
    ]

    recall_scores: list[float] = []
    mrr_scores: list[float] = []
    ndcg_scores: list[float] = []

    print(
        "Synthetic lexical retrieval evaluation "
        f"strategy={strategy}, top_k={TOP_K}, "
        f"minimum_score={MINIMUM_SCORE}"
    )
    if strategy == DOCUMENT_AWARE_LEXICAL:
        print(
            "Candidate documents per query: "
            f"{CANDIDATE_DOCUMENT_COUNT}"
        )
    print(
        f"Active Child Chunks: {len(active_child_chunks)}"
    )
    print()

    for case in answer_cases:
        relevant_chunk_ids = set(
            resolve_relevant_child_chunk_ids(
                case=case,
                ingested_documents=ingested_documents,
                answer_term_overrides=answer_term_overrides,
            )
        )

        results = retrieve(
            query=case["query"],
            active_child_chunks=active_child_chunks,
            strategy=strategy,
        )

        retrieved_chunk_ids = [
            result.chunk_id
            for result in results
        ]

        recall = calculate_recall(
            retrieved_chunk_ids=retrieved_chunk_ids,
            relevant_chunk_ids=relevant_chunk_ids,
        )
        mrr = calculate_mrr(
            retrieved_chunk_ids=retrieved_chunk_ids,
            relevant_chunk_ids=relevant_chunk_ids,
        )
        ndcg = calculate_ndcg(
            retrieved_chunk_ids=retrieved_chunk_ids,
            relevant_chunk_ids=relevant_chunk_ids,
        )

        recall_scores.append(recall)
        mrr_scores.append(mrr)
        ndcg_scores.append(ndcg)

        status = "PASS" if recall == 1.0 else "FAIL"
        result_summary = [
            f"{result.chunk_id}@{result.score:.1f}"
            for result in results
        ]

        print(
            f"{status} {case['id']} | "
            f"Recall@{TOP_K}={recall:.2f} | "
            f"MRR@{TOP_K}={mrr:.4f} | "
            f"nDCG@{TOP_K}={ndcg:.4f}"
        )
        print(
            f"  relevant={sorted(relevant_chunk_ids)}"
        )
        print(
            f"  retrieved={result_summary}"
        )

    false_positive_count = 0

    for case in refuse_cases:
        results = retrieve(
            query=case["query"],
            active_child_chunks=active_child_chunks,
            strategy=strategy,
        )

        if results:
            false_positive_count += 1

            result_summary = [
                f"{result.chunk_id}@{result.score:.1f}"
                for result in results
            ]

            print(
                f"FAIL {case['id']} | "
                f"false_positive={result_summary}"
            )
        else:
            print(
                f"PASS {case['id']} | "
                "correctly returned no lexical result"
            )

    ocr_document_ids = {
        case["expected_document_id"]
        for case in needs_ocr_cases
    }
    searchable_ocr_document_ids = (
        ocr_document_ids
        & {
            chunk.document_id
            for chunk in active_child_chunks
        }
    )

    if searchable_ocr_document_ids:
        raise AssertionError(
            "image-only OCR documents must not appear in "
            f"the lexical candidate pool: "
            f"{sorted(searchable_ocr_document_ids)}"
        )

    macro_recall = sum(recall_scores) / len(recall_scores)
    macro_mrr = sum(mrr_scores) / len(mrr_scores)
    macro_ndcg = sum(ndcg_scores) / len(ndcg_scores)
    false_positive_rate = (
        false_positive_count / len(refuse_cases)
    )

    print()
    print(
        f"Macro Recall@{TOP_K}: {macro_recall:.4f}"
    )
    print(
        f"Macro MRR@{TOP_K}: {macro_mrr:.4f}"
    )
    print(
        f"Macro nDCG@{TOP_K}: {macro_ndcg:.4f}"
    )
    print(
        f"False Positive Rate@{TOP_K}: "
        f"{false_positive_rate:.4f}"
    )
    print(
        f"OCR candidate-pool isolation: "
        f"Passed {len(needs_ocr_cases)}/{len(needs_ocr_cases)}"
    )
    print(
        "Status: isolated synthetic lexical baseline only; "
        "the main Agent retrieval path was not changed."
    )

    return RetrievalMetrics(
        strategy=strategy,
        answer_case_count=len(answer_cases),
        macro_recall_at_3=macro_recall,
        macro_mrr_at_3=macro_mrr,
        macro_ndcg_at_3=macro_ndcg,
        false_positive_rate_at_3=false_positive_rate,
        ocr_candidate_pool_isolated=(
            not searchable_ocr_document_ids
        ),
    )


if __name__ == "__main__":
    args = parse_args()
    main(strategy=args.strategy)
