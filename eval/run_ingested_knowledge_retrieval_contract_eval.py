"""验证隔离 SQLite 检索只返回 active 且 INDEXED 的 Chunk。"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import get_connection
from app.ingested_knowledge_retriever import search_ingested_knowledge
from app.knowledge_ingestion_service import ingest_document
from app.knowledge_models import DocumentFormat, SourceType
from app.knowledge_repository import mark_active_document_chunks_indexed


FIXTURES_ROOT = PROJECT_ROOT / "eval" / "fixtures" / "synthetic_corpus_v1"
MARKDOWN_FIXTURE = FIXTURES_ROOT / "markdown" / "asset_lifecycle_sop.md"
SCAN_PDF_FIXTURE = FIXTURES_ROOT / "pdf" / "visitor_access_registration_scan.pdf"
VERSION_ONE_PDF_FIXTURE = (
    FIXTURES_ROOT / "pdf" / "remote_access_security_policy_v1.pdf"
)
VERSION_TWO_PDF_FIXTURE = (
    FIXTURES_ROOT / "pdf" / "remote_access_security_policy_v2.pdf"
)


def mark_indexed(database_path: str, document_id: str) -> int:
    connection = get_connection(Path(database_path))
    try:
        with connection:
            return mark_active_document_chunks_indexed(
                connection=connection,
                document_id=document_id,
                indexed_at=datetime.now(timezone.utc).isoformat(),
            )
    finally:
        connection.close()


def test_pending_chunks_are_not_retrievable(database_path: str) -> None:
    ingestion = ingest_document(
        source_path=MARKDOWN_FIXTURE,
        logical_document_id="asset_lifecycle_sop",
        version="1.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.MARKDOWN,
        database_path=database_path,
    )

    assert search_ingested_knowledge(
        query="离职归还设备",
        database_path=database_path,
    ) == []

    indexed_chunk_count = mark_indexed(database_path, ingestion.document_id)
    results = search_ingested_knowledge(
        query="离职归还设备",
        database_path=database_path,
    )

    assert indexed_chunk_count > 0
    assert results
    assert {result.document_id for result in results} == {ingestion.document_id}
    assert all(result.retrieval_strategy == "isolated_sqlite_lexical" for result in results)


def test_superseded_and_failed_documents_are_not_retrievable(
    database_path: str,
) -> None:
    first = ingest_document(
        source_path=VERSION_ONE_PDF_FIXTURE,
        logical_document_id="remote_access_security_policy",
        version="1.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.PDF_TEXT,
        database_path=database_path,
    )
    assert mark_indexed(database_path, first.document_id) > 0

    second = ingest_document(
        source_path=VERSION_TWO_PDF_FIXTURE,
        logical_document_id="remote_access_security_policy",
        version="2.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.PDF_TEXT,
        database_path=database_path,
        previous_version_document_id=first.document_id,
    )
    assert mark_indexed(database_path, second.document_id) > 0

    failed = ingest_document(
        source_path=SCAN_PDF_FIXTURE,
        logical_document_id="visitor_access_registration",
        version="1.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.PDF_IMAGE_ONLY,
        database_path=database_path,
    )

    results = search_ingested_knowledge(
        query="MFA 远程会话",
        database_path=database_path,
    )

    assert results
    assert {result.document_id for result in results} == {second.document_id}
    assert all(result.document_id != first.document_id for result in results)
    assert all(result.document_id != failed.document_id for result in results)


def test_empty_query_and_unmatched_query_return_no_results(database_path: str) -> None:
    ingestion = ingest_document(
        source_path=MARKDOWN_FIXTURE,
        logical_document_id="asset_lifecycle_sop",
        version="1.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.MARKDOWN,
        database_path=database_path,
    )
    assert mark_indexed(database_path, ingestion.document_id) > 0

    assert search_ingested_knowledge("   ", database_path) == []
    assert search_ingested_knowledge("火星基地种土豆", database_path) == []


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ingested-retrieval-contract-") as temp_dir:
        temp_root = Path(temp_dir)
        test_pending_chunks_are_not_retrievable(
            str(temp_root / "pending_gate.db")
        )
        print("PASS test_pending_chunks_are_not_retrievable")
        test_superseded_and_failed_documents_are_not_retrievable(
            str(temp_root / "lifecycle_filter.db")
        )
        print("PASS test_superseded_and_failed_documents_are_not_retrievable")
        test_empty_query_and_unmatched_query_return_no_results(
            str(temp_root / "empty_query.db")
        )
        print("PASS test_empty_query_and_unmatched_query_return_no_results")

    print("\nIngested knowledge retrieval contract: Passed 3/3")


if __name__ == "__main__":
    main()
