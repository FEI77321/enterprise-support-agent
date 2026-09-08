# 模块职责：验证 RAG 2.0 SQLite repository 的表初始化、解析产物持久化与 Chunk 替换行为。
# 测试仅使用临时数据库，不读写运行中的 enterprise_support_agent.db。

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from eval_path import setup_backend_path

setup_backend_path()

from app.database import get_connection, initialize_database
from app.knowledge_models import (
    ChunkKind,
    Document,
    DocumentFormat,
    DocumentStatus,
    KnowledgeChunk,
    PageMapEntry,
    ParsedDocument,
    ParseStatus,
    SourceType,
)
from app.knowledge_repository import (
    find_document_version_by_content_hash,
    insert_document_version,
    insert_logical_document,
    replace_document_chunks,
)


LOGICAL_DOCUMENT_ID = "identity_access_policy"
DOCUMENT_ID = "doc_identity_access_v1"
PARSED_DOCUMENT_ID = "parsed_identity_access_v1"
CREATED_AT = datetime(2026, 9, 8, tzinfo=timezone.utc)


def content_hash(value: str) -> str:
    """生成测试数据需要的 SHA-256。"""

    return sha256(value.encode("utf-8")).hexdigest()


def build_document() -> Document:
    """构造一份已成功解析、尚未建立向量索引的 Markdown 文档。"""

    return Document(
        document_id=DOCUMENT_ID,
        source_type=SourceType.SYNTHETIC,
        original_filename="identity_access_policy.md",
        document_format=DocumentFormat.MARKDOWN,
        source_object_key="fixtures/identity_access_policy.md",
        content_hash=content_hash("identity access policy v1"),
        version="1.0",
        status=DocumentStatus.PARSED,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )


def build_parsed_document() -> ParsedDocument:
    """构造与测试文档匹配的解析产物。"""

    markdown_content = "# 身份与访问管理\n\n账号申请需要管理员审批。"

    return ParsedDocument(
        parsed_document_id=PARSED_DOCUMENT_ID,
        document_id=DOCUMENT_ID,
        parser_name="markdown",
        parser_version="1.0",
        parse_status=ParseStatus.SUCCESS,
        markdown_content=markdown_content,
        page_map=[
            PageMapEntry(
                page_number=1,
                char_start=0,
                char_end=len(markdown_content),
            )
        ],
        parse_warnings=[],
        created_at=CREATED_AT,
    )


def build_chunks(prefix: str) -> list[KnowledgeChunk]:
    """构造一组 Parent / Child Chunk，用于验证替换语义。"""

    parent_content = f"# 身份与访问管理\n\n{prefix}父块内容"
    child_content = f"{prefix}账号申请需要管理员审批。"
    parent_chunk_id = f"chunk_{prefix}_parent"

    return [
        KnowledgeChunk(
            chunk_id=parent_chunk_id,
            document_id=DOCUMENT_ID,
            parsed_document_id=PARSED_DOCUMENT_ID,
            document_version="1.0",
            kind=ChunkKind.PARENT,
            heading_path=["身份与访问管理"],
            page_start=1,
            page_end=1,
            content=parent_content,
            content_hash=content_hash(parent_content),
        ),
        KnowledgeChunk(
            chunk_id=f"{parent_chunk_id}:child:0001",
            document_id=DOCUMENT_ID,
            parsed_document_id=PARSED_DOCUMENT_ID,
            document_version="1.0",
            kind=ChunkKind.CHILD,
            parent_chunk_id=parent_chunk_id,
            heading_path=["身份与访问管理"],
            page_start=1,
            page_end=1,
            content=child_content,
            content_hash=content_hash(child_content),
        ),
    ]


def persist_document(
    database_path: Path,
) -> tuple[Document, ParsedDocument]:
    """向临时数据库写入一份逻辑文档和它的具体版本。"""

    initialize_database(database_path)

    document = build_document()
    parsed_document = build_parsed_document()

    connection = get_connection(database_path)
    try:
        with connection:
            insert_logical_document(
                connection=connection,
                logical_document_id=LOGICAL_DOCUMENT_ID,
                display_name="身份与访问管理制度",
                source_type=document.source_type.value,
                created_at=document.created_at.isoformat(),
            )
            insert_document_version(
                connection=connection,
                logical_document_id=LOGICAL_DOCUMENT_ID,
                document=document,
                parsed_document=parsed_document,
            )
    finally:
        connection.close()

    return document, parsed_document


def test_initialize_knowledge_tables_is_idempotent(
    database_path: Path,
) -> None:
    """重复初始化不会报错，且三张表均存在。"""

    initialize_database(database_path)
    initialize_database(database_path)

    connection = get_connection(database_path)
    try:
        table_names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()

    expected_table_names = {
        "knowledge_documents",
        "knowledge_document_versions",
        "knowledge_chunks",
    }

    if not expected_table_names <= table_names:
        raise AssertionError(
            f"missing knowledge tables: {expected_table_names - table_names}"
        )


def test_insert_document_version_persists_parsed_document(
    database_path: Path,
) -> None:
    """版本、解析文本、页码映射和告警均能从 SQLite 读回。"""

    document, parsed_document = persist_document(database_path)

    connection = get_connection(database_path)
    try:
        row = connection.execute(
            """
            SELECT *
            FROM knowledge_document_versions
            WHERE document_id = ?
            """,
            (document.document_id,),
        ).fetchone()

        duplicate_row = find_document_version_by_content_hash(
            connection=connection,
            logical_document_id=LOGICAL_DOCUMENT_ID,
            content_hash=document.content_hash,
        )
    finally:
        connection.close()

    if row is None:
        raise AssertionError("document version was not persisted")

    if duplicate_row is None:
        raise AssertionError("content-hash lookup returned no persisted version")

    if row["markdown_content"] != parsed_document.markdown_content:
        raise AssertionError("markdown_content was not persisted exactly")

    page_map = json.loads(row["page_map_json"])
    if page_map != [
        page_map_entry.model_dump(mode="json")
        for page_map_entry in parsed_document.page_map
    ]:
        raise AssertionError("page_map_json does not match ParsedDocument")

    if json.loads(row["parse_warnings_json"]) != []:
        raise AssertionError("parse_warnings_json should be an empty list")


def test_replace_document_chunks_replaces_old_chunks(
    database_path: Path,
) -> None:
    """重复切块只保留最新的一组 Chunk，不产生残留。"""

    document, _ = persist_document(database_path)

    connection = get_connection(database_path)
    try:
        with connection:
            replace_document_chunks(
                connection=connection,
                document_id=document.document_id,
                chunks=build_chunks("old"),
                created_at=CREATED_AT.isoformat(),
            )
            replace_document_chunks(
                connection=connection,
                document_id=document.document_id,
                chunks=build_chunks("new"),
                created_at=CREATED_AT.isoformat(),
            )

        chunk_ids = {
            row["chunk_id"]
            for row in connection.execute(
                """
                SELECT chunk_id
                FROM knowledge_chunks
                WHERE document_id = ?
                """,
                (document.document_id,),
            )
        }
    finally:
        connection.close()

    expected_chunk_ids = {
        "chunk_new_parent",
        "chunk_new_parent:child:0001",
    }

    if chunk_ids != expected_chunk_ids:
        raise AssertionError(
            f"unexpected persisted chunks: {sorted(chunk_ids)}"
        )


def main() -> None:
    with TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)

        test_initialize_knowledge_tables_is_idempotent(
            temporary_root / "initialize.db"
        )
        print("PASS test_initialize_knowledge_tables_is_idempotent")

        test_insert_document_version_persists_parsed_document(
            temporary_root / "persist_version.db"
        )
        print("PASS test_insert_document_version_persists_parsed_document")

        test_replace_document_chunks_replaces_old_chunks(
            temporary_root / "replace_chunks.db"
        )
        print("PASS test_replace_document_chunks_replaces_old_chunks")

    print()
    print("Knowledge repository contract: Passed 3/3")


if __name__ == "__main__":
    main()
