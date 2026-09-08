# 模块职责：为 synthetic 摄入链路提供隔离的轻量 lexical 检索基线。
# 仅处理当前内存中的 Child Chunk；不调用主 Agent、不读写 Chroma。

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from app.knowledge_models import KnowledgeChunk


CJK_RUN_PATTERN = re.compile(r"[\u4e00-\u9fff]+")
ASCII_TOKEN_PATTERN = re.compile(
    r"[A-Za-z][A-Za-z0-9._:-]*|\d+(?::\d+)?"
)


@dataclass(frozen=True)
class RankedChunk:
    """一条按 lexical 分数排序的 Child Chunk 结果。"""

    chunk_id: str
    document_id: str
    score: float
    chunk: KnowledgeChunk


def normalize_text(value: str) -> str:
    """统一大小写并移除空白，降低 PDF/表格换行对匹配的影响。"""

    return re.sub(r"\s+", "", value).casefold()


def build_query_features(query: str) -> dict[str, float]:
    """将查询转换为中文 bigram、数字和英文术语特征。"""

    normalized_query = normalize_text(query)
    features: dict[str, float] = {}

    for cjk_run in CJK_RUN_PATTERN.findall(normalized_query):
        if len(cjk_run) == 1:
            features[cjk_run] = max(
                features.get(cjk_run, 0.0),
                0.5,
            )
            continue

        for index in range(len(cjk_run) - 1):
            bigram = cjk_run[index : index + 2]
            features[bigram] = max(
                features.get(bigram, 0.0),
                1.0,
            )

    for token in ASCII_TOKEN_PATTERN.findall(normalized_query):
        weight = 3.0 if any(char.isdigit() for char in token) else 2.0

        features[token] = max(
            features.get(token, 0.0),
            weight,
        )

    return features


def score_chunk(
    query_features: dict[str, float],
    chunk: KnowledgeChunk,
) -> float:
    """计算查询特征在单个 Child Chunk 中出现的加权分数。"""

    normalized_content = normalize_text(chunk.content)

    return sum(
        weight
        for feature, weight in query_features.items()
        if feature in normalized_content
    )


def search_synthetic_chunks(
    query: str,
    chunks: Iterable[KnowledgeChunk],
    top_k: int = 3,
    minimum_score: float = 2.0,
) -> list[RankedChunk]:
    """返回得分达到阈值的前 K 个 Child Chunk。"""

    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")

    if minimum_score < 0:
        raise ValueError(
            "minimum_score must be greater than or equal to 0"
        )

    query_features = build_query_features(query)

    if not query_features:
        return []

    ranked_results: list[RankedChunk] = []

    for chunk in chunks:
        score = score_chunk(
            query_features=query_features,
            chunk=chunk,
        )

        if score < minimum_score:
            continue

        ranked_results.append(
            RankedChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                score=score,
                chunk=chunk,
            )
        )

    ranked_results.sort(
        key=lambda result: (
            -result.score,
            result.chunk_id,
        )
    )

    return ranked_results[:top_k]

def search_synthetic_chunks_document_aware(
    query: str,
    chunks: Iterable[KnowledgeChunk],
    top_k: int = 3,
    minimum_score: float = 2.0,
    candidate_document_count: int = 2,
) -> list[RankedChunk]:
    """先聚合 Child Chunk 证据选择候选文档，再在候选文档内排序。"""

    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")

    if minimum_score < 0:
        raise ValueError(
            "minimum_score must be greater than or equal to 0"
        )

    if candidate_document_count <= 0:
        raise ValueError(
            "candidate_document_count must be greater than 0"
        )

    query_features = build_query_features(query)

    if not query_features:
        return []

    scored_chunks: list[tuple[KnowledgeChunk, float]] = []
    document_scores: dict[str, list[float]] = {}

    for chunk in chunks:
        score = score_chunk(
            query_features=query_features,
            chunk=chunk,
        )

        scored_chunks.append((chunk, score))

        if score > 0:
            document_scores.setdefault(
                chunk.document_id,
                [],
            ).append(score)

    if not document_scores:
        return []

    document_ranking = sorted(
        (
            (
                document_id,
                sum(
                    sorted(
                        scores,
                        reverse=True,
                    )[:2]
                ),
            )
            for document_id, scores in document_scores.items()
        ),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    )

    candidate_document_ids = {
        document_id
        for document_id, _ in document_ranking[
            :candidate_document_count
        ]
    }

    ranked_results: list[RankedChunk] = []

    for chunk, score in scored_chunks:
        if chunk.document_id not in candidate_document_ids:
            continue

        if score < minimum_score:
            continue

        ranked_results.append(
            RankedChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                score=score,
                chunk=chunk,
            )
        )

    ranked_results.sort(
        key=lambda result: (
            -result.score,
            result.chunk_id,
        )
    )

    return ranked_results[:top_k]