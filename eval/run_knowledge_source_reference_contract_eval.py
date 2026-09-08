"""RAG 2.0 来源回链与旧 Source 兼容性的契约验证。"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.knowledge_ingestion_service import ingest_document
from app.knowledge_models import (
    DocumentFormat,
    RetrievalResult,
    SourceType,
)
from app.knowledge_source_adapter import retrieval_result_to_source
from app.models import Source


FIXTURES_ROOT = PROJECT_ROOT / "eval" / "fixtures" / "synthetic_corpus_v1"
MARKDOWN_FIXTURE = FIXTURES_ROOT / "markdown" / "asset_lifecycle_sop.md"
TEXT_PDF_FIXTURE = FIXTURES_ROOT / "pdf" / "incident_response_handbook.pdf"


def _build_result_from_persisted_parent_chunk(
    database_path: str,
    document_id: str,
    request_id: str,
) -> RetrievalResult:
    """读取真实持久化的 Parent Chunk，模拟未来新检索入口的证据输出。"""

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT chunks.chunk_id,
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
            WHERE chunks.document_id = ?
              AND chunks.kind = 'parent'
            ORDER BY chunks.chunk_id
            LIMIT 1
            """,
            (document_id,),
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    return RetrievalResult(
        request_id=request_id,
        rank=1,
        chunk_id=row["chunk_id"],
        context_chunk_id=None,
        document_id=row["document_id"],
        document_version=row["document_version"],
        source_filename=Path(row["source_path"]).name,
        heading_path=json.loads(row["heading_path_json"]),
        page_start=row["page_start"],
        page_end=row["page_end"],
        content=row["content"],
        score=0.95,
        retrieval_strategy="isolated_source_reference_contract",
    )


def test_legacy_source_json_remains_valid() -> None:
    legacy_payload = {
        "file": "vpn_guide.md",
        "snippet": "VPN 720 错误请检查网络连接。",
        "score": 8,
        "chunk_id": "vpn_guide.md::chunk-6",
    }

    source = Source.model_validate(legacy_payload)

    assert source.model_dump(exclude_none=True) == legacy_payload
    assert source.document_id is None
    assert source.heading_path is None
    assert source.page_start is None
    assert source.page_end is None


def test_markdown_source_reference_from_persisted_chunk(database_path: str) -> None:
    ingestion = ingest_document(
        source_path=MARKDOWN_FIXTURE,
        logical_document_id="asset_lifecycle_sop",
        version="1.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.MARKDOWN,
        database_path=database_path,
    )
    result = _build_result_from_persisted_parent_chunk(
        database_path=database_path,
        document_id=ingestion.document_id,
        request_id="request_markdown_source_001",
    )
    source = retrieval_result_to_source(result)

    assert source.file == MARKDOWN_FIXTURE.name
    assert source.document_id == ingestion.document_id
    assert source.document_version == "1.0"
    assert source.heading_path
    assert source.page_start == 1
    assert source.page_end == 1
    assert source.chunk_id == result.chunk_id
    assert source.score == 95


def test_pdf_source_reference_from_persisted_chunk(database_path: str) -> None:
    ingestion = ingest_document(
        source_path=TEXT_PDF_FIXTURE,
        logical_document_id="incident_response_handbook",
        version="1.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.PDF_TEXT,
        database_path=database_path,
    )
    result = _build_result_from_persisted_parent_chunk(
        database_path=database_path,
        document_id=ingestion.document_id,
        request_id="request_pdf_source_001",
    )
    source = retrieval_result_to_source(result)

    assert source.file == TEXT_PDF_FIXTURE.name
    assert source.document_id == ingestion.document_id
    assert source.document_version == "1.0"
    # 当前基础 PDF 解析只提取文本和页码，不把视觉标题猜成 Markdown 标题。
    # 因而字段存在且可回传，但本 fixture 中路径为空，避免伪造结构化信息。
    assert source.heading_path == []
    assert source.page_start is not None
    assert source.page_end is not None
    assert source.page_end >= source.page_start


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="knowledge-source-contract-") as temp_dir:
        temp_root = Path(temp_dir)
        test_legacy_source_json_remains_valid()
        print("PASS test_legacy_source_json_remains_valid")
        test_markdown_source_reference_from_persisted_chunk(
            str(temp_root / "markdown_source.db")
        )
        print("PASS test_markdown_source_reference_from_persisted_chunk")
        test_pdf_source_reference_from_persisted_chunk(
            str(temp_root / "pdf_source.db")
        )
        print("PASS test_pdf_source_reference_from_persisted_chunk")

    print("\nKnowledge source reference contract: Passed 3/3")


if __name__ == "__main__":
    main()
