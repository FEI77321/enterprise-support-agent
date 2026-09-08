"""将 RAG 2.0 检索证据适配为现有聊天接口的 Source。"""

from __future__ import annotations

from app.knowledge_models import RetrievalResult
from app.models import Source


DEFAULT_SNIPPET_LENGTH = 240


def _build_snippet(content: str, max_length: int) -> str:
    """生成来源摘要，避免把完整 Chunk 直接放进 API 响应。"""

    normalized_content = " ".join(content.split())
    if len(normalized_content) <= max_length:
        return normalized_content

    return f"{normalized_content[:max_length - 3]}..."


def _to_source_score(retrieval_score: float) -> int:
    """把 RAG 2.0 的 0~1 归一化分数转为旧 Source 使用的百分制整数。"""

    return max(0, min(100, round(retrieval_score * 100)))


def retrieval_result_to_source(
    result: RetrievalResult,
    snippet_length: int = DEFAULT_SNIPPET_LENGTH,
) -> Source:
    """保留 RAG 2.0 回链元数据，同时兼容旧 Agent 所需的基础字段。"""

    if snippet_length < 4:
        raise ValueError("snippet_length must be at least 4")

    return Source(
        file=result.source_filename,
        snippet=_build_snippet(result.content, max_length=snippet_length),
        score=_to_source_score(result.score),
        chunk_id=result.chunk_id,
        document_id=result.document_id,
        document_version=result.document_version,
        context_chunk_id=result.context_chunk_id,
        heading_path=list(result.heading_path),
        page_start=result.page_start,
        page_end=result.page_end,
    )
