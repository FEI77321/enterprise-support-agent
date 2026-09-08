from __future__ import annotations

import json
import sqlite3

from app.knowledge_models import (
    Document,
    KnowledgeChunk,
    ParsedDocument,
)


def initialize_knowledge_tables(
    connection: sqlite3.Connection,
) -> None:
    """创建 RAG 2.0 文档、版本与 Chunk 元数据表。"""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_documents (
            logical_document_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            active_document_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_document_versions (
            document_id TEXT PRIMARY KEY,
            logical_document_id TEXT NOT NULL,
            version TEXT NOT NULL,
            previous_document_id TEXT,
            content_hash TEXT NOT NULL,
            source_path TEXT NOT NULL,
            document_format TEXT NOT NULL,
            parse_status TEXT NOT NULL,
            ingestion_status TEXT NOT NULL,
            parser_name TEXT,
            parser_version TEXT,
            parsed_document_id TEXT,
            markdown_content TEXT,
            page_map_json TEXT NOT NULL,
            parse_warnings_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            indexed_at TEXT,
            UNIQUE (logical_document_id, version),
            UNIQUE (logical_document_id, content_hash),
            FOREIGN KEY (logical_document_id)
                REFERENCES knowledge_documents(logical_document_id)
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            parsed_document_id TEXT NOT NULL,
            document_version TEXT NOT NULL,
            kind TEXT NOT NULL,
            parent_chunk_id TEXT,
            heading_path_json TEXT NOT NULL,
            page_start INTEGER NOT NULL,
            page_end INTEGER NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            index_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (document_id)
                REFERENCES knowledge_document_versions(document_id)
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_knowledge_document_versions_logical_status
        ON knowledge_document_versions (
            logical_document_id,
            ingestion_status
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_knowledge_chunks_document_kind
        ON knowledge_chunks (
            document_id,
            kind
        )
        """
    )


def find_document_version_by_content_hash(
    connection: sqlite3.Connection,
    logical_document_id: str,
    content_hash: str,
) -> sqlite3.Row | None:
    """查找同一逻辑文档下内容完全相同的已持久化版本。"""

    return connection.execute(
        """
        SELECT *
        FROM knowledge_document_versions
        WHERE logical_document_id = ?
          AND content_hash = ?
        """,
        (logical_document_id, content_hash),
    ).fetchone()


def insert_logical_document(
    connection: sqlite3.Connection,
    logical_document_id: str,
    display_name: str,
    source_type: str,
    created_at: str,
) -> None:
    """插入逻辑文档；重复调用保持幂等并刷新更新时间。"""

    connection.execute(
        """
        INSERT INTO knowledge_documents (
            logical_document_id,
            display_name,
            source_type,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (logical_document_id)
        DO UPDATE SET
            display_name = excluded.display_name,
            source_type = excluded.source_type,
            updated_at = excluded.updated_at
        """,
        (
            logical_document_id,
            display_name,
            source_type,
            created_at,
            created_at,
        ),
    )


def insert_document_version(
    connection: sqlite3.Connection,
    logical_document_id: str,
    document: Document,
    parsed_document: ParsedDocument,
) -> None:
    """保存具体版本及其统一解析产物。"""

    if parsed_document.document_id != document.document_id:
        raise ValueError(
            "parsed_document.document_id must match document.document_id"
        )

    page_map_json = json.dumps(
        [
            page_map_entry.model_dump(mode="json")
            for page_map_entry in parsed_document.page_map
        ],
        ensure_ascii=False,
    )
    parse_warnings_json = json.dumps(
        parsed_document.parse_warnings,
        ensure_ascii=False,
    )

    connection.execute(
        """
        INSERT INTO knowledge_document_versions (
            document_id,
            logical_document_id,
            version,
            previous_document_id,
            content_hash,
            source_path,
            document_format,
            parse_status,
            ingestion_status,
            parser_name,
            parser_version,
            parsed_document_id,
            markdown_content,
            page_map_json,
            parse_warnings_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document.document_id,
            logical_document_id,
            document.version,
            document.previous_version_document_id,
            document.content_hash,
            document.source_object_key,
            document.document_format.value,
            parsed_document.parse_status.value,
            document.status.value,
            parsed_document.parser_name,
            parsed_document.parser_version,
            parsed_document.parsed_document_id,
            parsed_document.markdown_content,
            page_map_json,
            parse_warnings_json,
            document.created_at.isoformat(),
        ),
    )


def activate_document_version(
    connection: sqlite3.Connection,
    logical_document_id: str,
    document_id: str,
    updated_at: str,
) -> None:
    """将一个成功解析的版本设为当前生效版本，并废止先前生效版本。"""

    candidate = connection.execute(
        """
        SELECT document_id, logical_document_id, parse_status
        FROM knowledge_document_versions
        WHERE document_id = ?
        """,
        (document_id,),
    ).fetchone()

    if candidate is None:
        raise ValueError(f"document version does not exist: {document_id}")

    if candidate["logical_document_id"] != logical_document_id:
        raise ValueError(
            "document version does not belong to logical_document_id: "
            f"{logical_document_id}"
        )

    if candidate["parse_status"] == "failed":
        raise ValueError("a failed document version cannot become active")

    logical_document = connection.execute(
        """
        SELECT active_document_id
        FROM knowledge_documents
        WHERE logical_document_id = ?
        """,
        (logical_document_id,),
    ).fetchone()

    if logical_document is None:
        raise ValueError(
            "logical document does not exist: "
            f"{logical_document_id}"
        )

    previous_active_document_id = logical_document["active_document_id"]
    if (
        previous_active_document_id is not None
        and previous_active_document_id != document_id
    ):
        connection.execute(
            """
            UPDATE knowledge_document_versions
            SET ingestion_status = 'superseded'
            WHERE document_id = ?
            """,
            (previous_active_document_id,),
        )

    connection.execute(
        """
        UPDATE knowledge_documents
        SET active_document_id = ?, updated_at = ?
        WHERE logical_document_id = ?
        """,
        (document_id, updated_at, logical_document_id),
    )


def mark_active_document_chunks_indexed(
    connection: sqlite3.Connection,
    document_id: str,
    indexed_at: str,
) -> int:
    """将当前 active 文档的 Chunk 置为可被隔离检索入口读取。"""

    document_version = connection.execute(
        """
        SELECT versions.document_id, versions.parse_status
        FROM knowledge_document_versions AS versions
        JOIN knowledge_documents AS documents
          ON documents.active_document_id = versions.document_id
        WHERE versions.document_id = ?
        """,
        (document_id,),
    ).fetchone()

    if document_version is None:
        raise ValueError(
            "only the current active document version can be indexed: "
            f"{document_id}"
        )

    if document_version["parse_status"] == "failed":
        raise ValueError("a failed document version cannot be indexed")

    cursor = connection.execute(
        """
        UPDATE knowledge_chunks
        SET index_status = 'indexed'
        WHERE document_id = ?
          AND index_status = 'pending'
        """,
        (document_id,),
    )

    connection.execute(
        """
        UPDATE knowledge_document_versions
        SET ingestion_status = 'indexed', indexed_at = ?
        WHERE document_id = ?
        """,
        (indexed_at, document_id),
    )

    return cursor.rowcount


def replace_document_chunks(
    connection: sqlite3.Connection,
    document_id: str,
    chunks: list[KnowledgeChunk],
    created_at: str,
) -> None:
    """替换一个具体版本的全部 Chunk，避免旧解析结果残留。"""

    mismatched_chunk_ids = [
        chunk.chunk_id
        for chunk in chunks
        if chunk.document_id != document_id
    ]

    if mismatched_chunk_ids:
        raise ValueError(
            "all chunks must belong to document_id: "
            f"{mismatched_chunk_ids}"
        )

    connection.execute(
        "DELETE FROM knowledge_chunks WHERE document_id = ?",
        (document_id,),
    )

    connection.executemany(
        """
        INSERT INTO knowledge_chunks (
            chunk_id,
            document_id,
            parsed_document_id,
            document_version,
            kind,
            parent_chunk_id,
            heading_path_json,
            page_start,
            page_end,
            content,
            content_hash,
            index_status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                chunk.chunk_id,
                chunk.document_id,
                chunk.parsed_document_id,
                chunk.document_version,
                chunk.kind.value,
                chunk.parent_chunk_id,
                json.dumps(
                    chunk.heading_path,
                    ensure_ascii=False,
                ),
                chunk.page_start,
                chunk.page_end,
                chunk.content,
                chunk.content_hash,
                chunk.index_status.value,
                created_at,
            )
            for chunk in chunks
        ],
    )


def count_document_chunks(
    connection: sqlite3.Connection,
    document_id: str,
) -> int:
    """返回一个具体文档版本当前持久化的 Chunk 数量。"""

    row = connection.execute(
        """
        SELECT COUNT(*) AS chunk_count
        FROM knowledge_chunks
        WHERE document_id = ?
        """,
        (document_id,),
    ).fetchone()

    return int(row["chunk_count"])
