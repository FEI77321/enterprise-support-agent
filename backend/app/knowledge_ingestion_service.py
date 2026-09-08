"""RAG 2.0 文档导入服务。

本模块负责把一个本地文件走完“解析 -> 分块 -> SQLite 持久化”的最小链路。
当前阶段不会写入向量库，也不会接入主 Agent；Chunk 保持 PENDING，等待后续索引阶段处理。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from app.database import get_connection, initialize_database
from app.document_chunker import chunk_parsed_document
from app.document_parser import parse_document
from app.knowledge_models import (
    Document,
    DocumentFormat,
    DocumentStatus,
    KnowledgeChunk,
    ParseStatus,
    ParsedDocument,
    SourceType,
)
from app.knowledge_repository import (
    activate_document_version,
    count_document_chunks,
    find_document_version_by_content_hash,
    insert_document_version,
    insert_logical_document,
    replace_document_chunks,
)


@dataclass(frozen=True)
class IngestionResult:
    """一次导入的可观察结果，供 API 或评测脚本使用。"""

    document_id: str
    logical_document_id: str
    version: str
    parse_status: ParseStatus
    document_status: DocumentStatus
    chunk_count: int
    reused_existing_version: bool
    parse_warnings: tuple[str, ...]


def calculate_file_content_hash(source_path: Path) -> str:
    """计算原始文件字节的 SHA-256，用于幂等去重。"""

    return sha256(source_path.read_bytes()).hexdigest()


def build_document_id(
    logical_document_id: str,
    version: str,
    content_hash: str,
) -> str:
    """生成稳定的版本文档 ID，而不是把逻辑文档 ID 当作版本 ID。"""

    identity = f"{logical_document_id}:{version}:{content_hash}"
    token = sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"doc_{token}"


def _build_existing_result(
    connection,
    logical_document_id: str,
    existing_version,
) -> IngestionResult:
    """把仓储查询结果还原为统一的导入结果。"""

    warnings = tuple(json.loads(existing_version["parse_warnings_json"]))
    return IngestionResult(
        document_id=existing_version["document_id"],
        logical_document_id=logical_document_id,
        version=existing_version["version"],
        parse_status=ParseStatus(existing_version["parse_status"]),
        document_status=DocumentStatus(existing_version["ingestion_status"]),
        chunk_count=count_document_chunks(
            connection,
            existing_version["document_id"],
        ),
        reused_existing_version=True,
        parse_warnings=warnings,
    )


def _persist_document(
    database_path: Path,
    logical_document_id: str,
    document: Document,
    parsed_document: ParsedDocument,
    chunks: list[KnowledgeChunk],
) -> None:
    """在一个 SQLite 事务内写入文档版本、解析结果与 Chunk。"""

    connection = get_connection(database_path)
    try:
        with connection:
            insert_logical_document(
                connection=connection,
                logical_document_id=logical_document_id,
                display_name=document.original_filename,
                source_type=document.source_type.value,
                created_at=document.created_at.isoformat(),
            )
            insert_document_version(
                connection=connection,
                logical_document_id=logical_document_id,
                document=document,
                parsed_document=parsed_document,
            )
            if chunks:
                replace_document_chunks(
                    connection=connection,
                    document_id=document.document_id,
                    chunks=chunks,
                    created_at=document.created_at.isoformat(),
                )
            if document.status == DocumentStatus.PARSED:
                activate_document_version(
                    connection=connection,
                    logical_document_id=logical_document_id,
                    document_id=document.document_id,
                    updated_at=document.updated_at.isoformat(),
                )
    finally:
        connection.close()


def ingest_document(
    source_path: Path,
    logical_document_id: str,
    version: str,
    source_type: SourceType,
    document_format: DocumentFormat,
    database_path: Path | str,
    previous_version_document_id: str | None = None,
) -> IngestionResult:
    """导入一个 Markdown 或 PDF 文档，并保证同内容文件不会被重复写入。

    幂等判断使用文件原始字节的内容哈希：同一逻辑文档中，只要内容未变化，
    即使重复调用也会返回历史版本，而不会重复解析或重复写 Chunk。
    """

    resolved_source_path = source_path.resolve()
    resolved_database_path = Path(database_path).resolve()
    if not resolved_source_path.is_file():
        raise FileNotFoundError(f"source document does not exist: {resolved_source_path}")

    initialize_database(resolved_database_path)
    content_hash = calculate_file_content_hash(resolved_source_path)

    connection = get_connection(resolved_database_path)
    try:
        existing_version = find_document_version_by_content_hash(
            connection=connection,
            logical_document_id=logical_document_id,
            content_hash=content_hash,
        )
        if existing_version is not None:
            return _build_existing_result(
                connection=connection,
                logical_document_id=logical_document_id,
                existing_version=existing_version,
            )
    finally:
        connection.close()

    now = datetime.now(timezone.utc)
    processing_document = Document(
        document_id=build_document_id(
            logical_document_id=logical_document_id,
            version=version,
            content_hash=content_hash,
        ),
        version=version,
        previous_version_document_id=previous_version_document_id,
        source_type=source_type,
        original_filename=resolved_source_path.name,
        source_object_key=str(resolved_source_path),
        document_format=document_format,
        content_hash=content_hash,
        status=DocumentStatus.PARSING,
        created_at=now,
        updated_at=now,
    )
    parsed_document = parse_document(
        document=processing_document,
        source_path=resolved_source_path,
    )

    if parsed_document.parse_status == ParseStatus.FAILED:
        failed_document = processing_document.model_copy(
            update={
                "status": DocumentStatus.FAILED,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        _persist_document(
            database_path=resolved_database_path,
            logical_document_id=logical_document_id,
            document=failed_document,
            parsed_document=parsed_document,
            chunks=[],
        )
        return IngestionResult(
            document_id=failed_document.document_id,
            logical_document_id=logical_document_id,
            version=version,
            parse_status=parsed_document.parse_status,
            document_status=failed_document.status,
            chunk_count=0,
            reused_existing_version=False,
            parse_warnings=tuple(parsed_document.parse_warnings),
        )

    chunks = chunk_parsed_document(
        document=processing_document,
        parsed_document=parsed_document,
    )
    parsed_document_document = processing_document.model_copy(
        update={
            "status": DocumentStatus.PARSED,
            "updated_at": datetime.now(timezone.utc),
        }
    )
    _persist_document(
        database_path=resolved_database_path,
        logical_document_id=logical_document_id,
        document=parsed_document_document,
        parsed_document=parsed_document,
        chunks=chunks,
    )
    return IngestionResult(
        document_id=parsed_document_document.document_id,
        logical_document_id=logical_document_id,
        version=version,
        parse_status=parsed_document.parse_status,
        document_status=parsed_document_document.status,
        chunk_count=len(chunks),
        reused_existing_version=False,
        parse_warnings=tuple(parsed_document.parse_warnings),
    )
