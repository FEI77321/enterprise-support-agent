"""隔离的 SQLite 词面检索入口，不接入现有主 Agent。"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from uuid import uuid4

from app.database import get_connection, initialize_database
from app.knowledge_models import RetrievalResult


CJK_RUN_PATTERN = re.compile(r"[\u4e00-\u9fff]+")
ASCII_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9._:-]*|\d+(?::\d+)?")
RETRIEVAL_STRATEGY = "isolated_sqlite_lexical"


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _build_query_features(query: str) -> dict[str, float]:
    """复用 synthetic 实验的中文 bigram、英文术语和数字特征思路。"""

    normalized_query = _normalize_text(query)
    features: dict[str, float] = {}

    for cjk_run in CJK_RUN_PATTERN.findall(normalized_query):
        if len(cjk_run) == 1:
            features[cjk_run] = max(features.get(cjk_run, 0.0), 0.5)
            continue

        for index in range(len(cjk_run) - 1):
            bigram = cjk_run[index : index + 2]
            features[bigram] = max(features.get(bigram, 0.0), 1.0)

    for token in ASCII_TOKEN_PATTERN.findall(normalized_query):
        weight = 3.0 if any(char.isdigit() for char in token) else 2.0
        features[token] = max(features.get(token, 0.0), weight)

    return features


def _score_content(query_features: dict[str, float], content: str) -> float:
    """返回 0~1 的特征覆盖分数，便于转换为统一 RetrievalResult。"""

    if not query_features:
        return 0.0

    normalized_content = _normalize_text(content)
    matched_weight = sum(
        weight
        for feature, weight in query_features.items()
        if feature in normalized_content
    )
    total_weight = sum(query_features.values())
    return matched_weight / total_weight if total_weight else 0.0


def _load_indexed_active_child_chunks(
    database_path: Path,
) -> list[sqlite3.Row]:
    """只加载当前 active 版本且完成索引状态流转的 Child Chunk。"""

    connection = get_connection(database_path)
    try:
        return connection.execute(
            """
            SELECT chunks.chunk_id,
                   chunks.parent_chunk_id,
                   chunks.document_id,
                   chunks.document_version,
                   chunks.heading_path_json,
                   chunks.page_start,
                   chunks.page_end,
                   chunks.content,
                   versions.source_path
            FROM knowledge_chunks AS chunks
            JOIN knowledge_document_versions AS versions
              ON versions.document_id = chunks.document_id
            JOIN knowledge_documents AS documents
              ON documents.active_document_id = chunks.document_id
            WHERE chunks.kind = 'child'
              AND chunks.index_status = 'indexed'
              AND versions.ingestion_status = 'indexed'
            """
        ).fetchall()
    finally:
        connection.close()


def search_ingested_knowledge(
    query: str,
    database_path: Path | str,
    top_k: int = 3,
    minimum_score: float = 0.25,
    request_id: str | None = None,
) -> list[RetrievalResult]:
    """在隔离 SQLite 语料中检索 active 且 INDEXED 的 Child Chunk。

    此函数当前是可关闭的实验入口：不注册到工具表，不调用 Chroma，
    也不替换现有的 ``search_knowledge_base()``。
    """

    if not query.strip():
        return []

    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")

    if not 0 <= minimum_score <= 1:
        raise ValueError("minimum_score must be between 0 and 1")

    resolved_database_path = Path(database_path).resolve()
    initialize_database(resolved_database_path)
    query_features = _build_query_features(query)
    if not query_features:
        return []

    scored_rows: list[tuple[sqlite3.Row, float]] = []
    for row in _load_indexed_active_child_chunks(resolved_database_path):
        score = _score_content(query_features, row["content"])
        if score >= minimum_score:
            scored_rows.append((row, score))

    scored_rows.sort(key=lambda item: (-item[1], item[0]["chunk_id"]))
    effective_request_id = request_id or f"request_{uuid4().hex}"

    return [
        RetrievalResult(
            request_id=effective_request_id,
            rank=rank,
            chunk_id=row["chunk_id"],
            context_chunk_id=row["parent_chunk_id"],
            document_id=row["document_id"],
            document_version=row["document_version"],
            source_filename=Path(row["source_path"]).name,
            heading_path=json.loads(row["heading_path_json"]),
            page_start=row["page_start"],
            page_end=row["page_end"],
            content=row["content"],
            score=score,
            retrieval_strategy=RETRIEVAL_STRATEGY,
        )
        for rank, (row, score) in enumerate(scored_rows[:top_k], start=1)
    ]
