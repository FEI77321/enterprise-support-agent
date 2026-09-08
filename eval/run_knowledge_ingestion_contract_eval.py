"""RAG 2.0 最小文档导入链路的契约验证。"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import get_connection
from app.knowledge_ingestion_service import ingest_document
from app.knowledge_models import (
    DocumentFormat,
    DocumentStatus,
    ParseStatus,
    SourceType,
)


FIXTURES_ROOT = PROJECT_ROOT / "eval" / "fixtures" / "synthetic_corpus_v1"
MARKDOWN_FIXTURE = FIXTURES_ROOT / "markdown" / "asset_lifecycle_sop.md"
TEXT_PDF_FIXTURE = FIXTURES_ROOT / "pdf" / "incident_response_handbook.pdf"
SCAN_PDF_FIXTURE = FIXTURES_ROOT / "pdf" / "visitor_access_registration_scan.pdf"
VERSION_ONE_PDF_FIXTURE = (
    FIXTURES_ROOT / "pdf" / "remote_access_security_policy_v1.pdf"
)
VERSION_TWO_PDF_FIXTURE = (
    FIXTURES_ROOT / "pdf" / "remote_access_security_policy_v2.pdf"
)


def count_rows(database_path: str, table_name: str) -> int:
    connection = sqlite3.connect(database_path)
    try:
        return connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    finally:
        connection.close()


def test_markdown_ingestion_persists_parsed_document_and_chunks(
    database_path: str,
) -> None:
    result = ingest_document(
        source_path=MARKDOWN_FIXTURE,
        logical_document_id="asset_lifecycle_sop",
        version="1.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.MARKDOWN,
        database_path=database_path,
    )

    assert result.parse_status == ParseStatus.SUCCESS
    assert result.document_status == DocumentStatus.PARSED
    assert result.chunk_count > 0
    assert not result.reused_existing_version

    connection = get_connection(Path(database_path))
    try:
        version_row = connection.execute(
            """
            SELECT markdown_content, parse_status, ingestion_status
            FROM knowledge_document_versions
            WHERE document_id = ?
            """,
            (result.document_id,),
        ).fetchone()
        assert version_row is not None
        assert "资产" in version_row["markdown_content"]
        assert version_row["parse_status"] == ParseStatus.SUCCESS.value
        assert version_row["ingestion_status"] == DocumentStatus.PARSED.value
        assert result.chunk_count == connection.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE document_id = ?",
            (result.document_id,),
        ).fetchone()[0]
    finally:
        connection.close()


def test_text_pdf_ingestion_persists_page_mapped_chunks(database_path: str) -> None:
    result = ingest_document(
        source_path=TEXT_PDF_FIXTURE,
        logical_document_id="incident_response_handbook",
        version="1.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.PDF_TEXT,
        database_path=database_path,
    )

    assert result.parse_status in {ParseStatus.SUCCESS, ParseStatus.PARTIAL}
    assert result.document_status == DocumentStatus.PARSED
    assert result.chunk_count > 0

    connection = get_connection(Path(database_path))
    try:
        page_bounds = connection.execute(
            """
            SELECT MIN(page_start) AS min_page_start,
                   MAX(page_end) AS max_page_end
            FROM knowledge_chunks
            WHERE document_id = ?
            """,
            (result.document_id,),
        ).fetchone()
        assert page_bounds["min_page_start"] >= 1
        assert page_bounds["max_page_end"] >= 1
    finally:
        connection.close()


def test_duplicate_import_reuses_existing_version(database_path: str) -> None:
    first_result = ingest_document(
        source_path=MARKDOWN_FIXTURE,
        logical_document_id="asset_lifecycle_sop",
        version="1.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.MARKDOWN,
        database_path=database_path,
    )
    version_count_before = count_rows(database_path, "knowledge_document_versions")
    chunk_count_before = count_rows(database_path, "knowledge_chunks")

    second_result = ingest_document(
        source_path=MARKDOWN_FIXTURE,
        logical_document_id="asset_lifecycle_sop",
        version="1.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.MARKDOWN,
        database_path=database_path,
    )

    assert second_result.reused_existing_version
    assert second_result.document_id == first_result.document_id
    assert count_rows(database_path, "knowledge_document_versions") == version_count_before
    assert count_rows(database_path, "knowledge_chunks") == chunk_count_before


def test_scan_pdf_failure_is_persisted_without_chunks(database_path: str) -> None:
    result = ingest_document(
        source_path=SCAN_PDF_FIXTURE,
        logical_document_id="visitor_access_registration",
        version="1.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.PDF_IMAGE_ONLY,
        database_path=database_path,
    )

    assert result.parse_status == ParseStatus.FAILED
    assert result.document_status == DocumentStatus.FAILED
    assert result.chunk_count == 0
    assert not result.reused_existing_version

    connection = get_connection(Path(database_path))
    try:
        version_row = connection.execute(
            """
            SELECT parse_status, ingestion_status, markdown_content
            FROM knowledge_document_versions
            WHERE document_id = ?
            """,
            (result.document_id,),
        ).fetchone()
        active_row = connection.execute(
            """
            SELECT active_document_id
            FROM knowledge_documents
            WHERE logical_document_id = ?
            """,
            (result.logical_document_id,),
        ).fetchone()
        assert version_row["parse_status"] == ParseStatus.FAILED.value
        assert version_row["ingestion_status"] == DocumentStatus.FAILED.value
        assert version_row["markdown_content"] is None
        assert active_row["active_document_id"] is None
        assert count_rows(database_path, "knowledge_chunks") == 0
    finally:
        connection.close()


def test_new_successful_version_supersedes_previous_active_version(
    database_path: str,
) -> None:
    first_result = ingest_document(
        source_path=VERSION_ONE_PDF_FIXTURE,
        logical_document_id="remote_access_security_policy",
        version="1.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.PDF_TEXT,
        database_path=database_path,
    )
    second_result = ingest_document(
        source_path=VERSION_TWO_PDF_FIXTURE,
        logical_document_id="remote_access_security_policy",
        version="2.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.PDF_TEXT,
        database_path=database_path,
        previous_version_document_id=first_result.document_id,
    )

    assert first_result.document_status == DocumentStatus.PARSED
    assert second_result.document_status == DocumentStatus.PARSED
    assert first_result.document_id != second_result.document_id

    connection = get_connection(Path(database_path))
    try:
        logical_document = connection.execute(
            """
            SELECT active_document_id
            FROM knowledge_documents
            WHERE logical_document_id = ?
            """,
            (second_result.logical_document_id,),
        ).fetchone()
        version_rows = connection.execute(
            """
            SELECT document_id, version, previous_document_id, ingestion_status
            FROM knowledge_document_versions
            WHERE logical_document_id = ?
            ORDER BY version
            """,
            (second_result.logical_document_id,),
        ).fetchall()
        assert logical_document["active_document_id"] == second_result.document_id
        assert len(version_rows) == 2
        assert version_rows[0]["document_id"] == first_result.document_id
        assert version_rows[0]["ingestion_status"] == DocumentStatus.SUPERSEDED.value
        assert version_rows[1]["document_id"] == second_result.document_id
        assert version_rows[1]["previous_document_id"] == first_result.document_id
        assert version_rows[1]["ingestion_status"] == DocumentStatus.PARSED.value
    finally:
        connection.close()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="knowledge-ingestion-contract-") as temp_dir:
        temp_root = Path(temp_dir)
        test_markdown_ingestion_persists_parsed_document_and_chunks(
            str(temp_root / "markdown.db")
        )
        print("PASS test_markdown_ingestion_persists_parsed_document_and_chunks")
        test_text_pdf_ingestion_persists_page_mapped_chunks(
            str(temp_root / "text_pdf.db")
        )
        print("PASS test_text_pdf_ingestion_persists_page_mapped_chunks")
        test_duplicate_import_reuses_existing_version(
            str(temp_root / "idempotent.db")
        )
        print("PASS test_duplicate_import_reuses_existing_version")
        test_scan_pdf_failure_is_persisted_without_chunks(
            str(temp_root / "scan_failure.db")
        )
        print("PASS test_scan_pdf_failure_is_persisted_without_chunks")
        test_new_successful_version_supersedes_previous_active_version(
            str(temp_root / "version_lifecycle.db")
        )
        print("PASS test_new_successful_version_supersedes_previous_active_version")

    print("\nKnowledge ingestion contract: Passed 5/5")


if __name__ == "__main__":
    main()
