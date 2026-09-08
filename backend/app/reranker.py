# 模块职责：使用 CrossEncoder 对候选检索结果进行语义重排。

from sentence_transformers import CrossEncoder

from app.knowledge_base import SearchResult


RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"
RERANKER_CACHE_DIR = r"D:\AI-Model-Cache\huggingface"

_reranker: CrossEncoder | None = None


def get_reranker() -> CrossEncoder:
    """延迟加载重排模型，避免每次导入模块都重复加载。"""
    global _reranker

    if _reranker is None:
        _reranker = CrossEncoder(
            RERANKER_MODEL_NAME,
            cache_folder=RERANKER_CACHE_DIR,
        )

    return _reranker


def rerank_results(
    query: str,
    candidates: list[SearchResult],
    top_k: int = 3,
) -> list[SearchResult]:
    """根据“问题-候选内容”语义相关性，对候选结果重新排序。"""
    if not candidates:
        return []

    reranker = get_reranker()

    pairs = [
        (query, candidate.content)
        for candidate in candidates
    ]

    scores = reranker.predict(
        pairs,
        show_progress_bar=False,
    )

    reranked_pairs = sorted(
        zip(candidates, scores),
        key=lambda item: float(item[1]),
        reverse=True,
    )

    return [
        SearchResult(
            file=candidate.file,
            content=candidate.content,
            score=round(float(score) * 10000),
            # 保留：真实命中的子块，供检索评估使用。
            chunk_id=candidate.chunk_id,
            # 保留：实际回答使用的父块上下文 ID。
            context_chunk_id=candidate.context_chunk_id,
        )
        for candidate, score in reranked_pairs[:top_k]
    ]