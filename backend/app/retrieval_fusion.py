# 模块职责：合并关键词检索与 BGE 向量检索的结果。
from app.reranker import rerank_results
from app.knowledge_base import SearchResult
from app.vector_store import VectorSearchResult
from app.knowledge_base import (
    SearchResult,
    search_knowledge_base,
)
from app.vector_store import (
    VectorSearchResult,
    search_bge_vector_store,
)

RRF_K = 60


def fuse_with_rrf(
    keyword_results: list[SearchResult],
    vector_results: list[VectorSearchResult],
) -> list[SearchResult]:
    """使用 Reciprocal Rank Fusion 合并两路检索结果。"""
    fused_scores: dict[str, float] = {}
    result_by_chunk_id: dict[str, SearchResult] = {}

    # 关键词检索结果：保留其父块上下文，供后续回答使用。
    for rank, result in enumerate(keyword_results, start=1):
        if not result.chunk_id:
            continue

        fused_scores[result.chunk_id] = (
            fused_scores.get(result.chunk_id, 0.0)
            + 1 / (RRF_K + rank)
        )
        result_by_chunk_id[result.chunk_id] = result

    # 向量检索结果：转换为统一的 SearchResult 结构。
    for rank, result in enumerate(vector_results, start=1):
        fused_scores[result.chunk_id] = (
            fused_scores.get(result.chunk_id, 0.0)
            + 1 / (RRF_K + rank)
        )

        if result.chunk_id not in result_by_chunk_id:
            result_by_chunk_id[result.chunk_id] = SearchResult(
                file=result.file,
                content=result.content,
                score=0,
                chunk_id=result.chunk_id,
                context_chunk_id=result.chunk_id,
            )

    fused_results = [
        SearchResult(
            file=result_by_chunk_id[chunk_id].file,
            content=result_by_chunk_id[chunk_id].content,
            score=round(score * 10000),
            chunk_id=chunk_id,
            context_chunk_id=(
                result_by_chunk_id[chunk_id].context_chunk_id
            ),
        )
        for chunk_id, score in fused_scores.items()
    ]

    fused_results.sort(
        key=lambda result: result.score,
        reverse=True,
    )

    return fused_results

CANDIDATE_K = 10


def search_hybrid(
    query: str,
    top_k: int = 3,
) -> list[SearchResult]:
    """关键词与 BGE 向量各召回 Top-10，再用 RRF 融合取 Top-k。"""
    keyword_results = search_knowledge_base(
        query,
        top_k=CANDIDATE_K,
    )
    vector_results = search_bge_vector_store(
        query,
        top_k=CANDIDATE_K,
    )

    fused_results = fuse_with_rrf(
        keyword_results,
        vector_results,
    )

    return fused_results[:top_k]

def search_hybrid_reranked(
    query: str,
    top_k: int = 3,
) -> list[SearchResult]:
    """关键词与 BGE 召回后，经 RRF 融合并由 reranker 重排。"""
    keyword_results = search_knowledge_base(
        query,
        top_k=CANDIDATE_K,
    )
    vector_results = search_bge_vector_store(
        query,
        top_k=CANDIDATE_K,
    )

    fused_results = fuse_with_rrf(
        keyword_results,
        vector_results,
    )

    return rerank_results(
        query,
        fused_results,
        top_k=top_k,
    )