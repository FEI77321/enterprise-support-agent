# 模块职责：验证父子切块、来源元数据继承、PDF 页码回链与失败解析分流。

from datetime import datetime
from hashlib import sha256
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.document_chunker import chunk_parsed_document
from app.document_parser import parse_document
from app.knowledge_models import (
    ChunkKind,
    Document,
    DocumentFormat,
    ParseStatus,
    SourceType,
)


NOW = datetime(2026, 9, 8, 12, 0, 0)

FIXTURE_ROOT = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "synthetic_corpus_v1"
)


def build_document(
    document_id: str,
    source_path: Path,
    document_format: DocumentFormat,
) -> Document:
    """根据 fixture 文件构造带真实内容哈希的 Document。"""

    return Document(
        document_id=document_id,
        source_type=SourceType.SYNTHETIC,
        original_filename=source_path.name,
        document_format=document_format,
        source_object_key=str(source_path.relative_to(FIXTURE_ROOT)),
        content_hash=sha256(source_path.read_bytes()).hexdigest(),
        version="1.0",
        created_at=NOW,
        updated_at=NOW,
    )


def test_markdown_parent_child_relationship_and_provenance() -> None:
    """Markdown 标题应形成父块，子块应完整继承来源元数据。"""

    source_path = (
        FIXTURE_ROOT
        / "markdown"
        / "asset_lifecycle_sop.md"
    )
    document = build_document(
        document_id="doc_asset_lifecycle_v1",
        source_path=source_path,
        document_format=DocumentFormat.MARKDOWN,
    )

    parsed_document = parse_document(document, source_path)

    chunks = chunk_parsed_document(
        document=document,
        parsed_document=parsed_document,
        child_chunk_size=160,
        child_chunk_overlap=30,
    )

    parent_chunks = [
        chunk
        for chunk in chunks
        if chunk.kind == ChunkKind.PARENT
    ]
    child_chunks = [
        chunk
        for chunk in chunks
        if chunk.kind == ChunkKind.CHILD
    ]
    parent_chunk_ids = {
        chunk.chunk_id
        for chunk in parent_chunks
    }

    assert parsed_document.parse_status == ParseStatus.SUCCESS
    assert len(parent_chunks) == 4
    assert len(child_chunks) >= len(parent_chunks)

    assert all(
        child_chunk.parent_chunk_id in parent_chunk_ids
        for child_chunk in child_chunks
    )
    assert all(
        parent_chunk.parent_chunk_id is None
        for parent_chunk in parent_chunks
    )

    assert all(
        chunk.document_id == document.document_id
        for chunk in chunks
    )
    assert all(
        chunk.parsed_document_id
        == parsed_document.parsed_document_id
        for chunk in chunks
    )
    assert all(
        chunk.document_version == document.version
        for chunk in chunks
    )

    assert all(
        chunk.page_start == 1
        and chunk.page_end == 1
        for chunk in chunks
    )

    assert all(
        chunk.content_hash
        == sha256(chunk.content.encode("utf-8")).hexdigest()
        for chunk in chunks
    )

    assert any(
        parent_chunk.heading_path
        == [
            "IT 资产生命周期标准操作流程",
            "新设备领用",
        ]
        for parent_chunk in parent_chunks
    )


def test_text_pdf_chunks_preserve_page_mapping() -> None:
    """普通文本型 PDF 应产出可回链到原页码的父子块。"""

    source_path = (
        FIXTURE_ROOT
        / "pdf"
        / "remote_access_security_policy_v2.pdf"
    )
    document = build_document(
        document_id="doc_remote_access_v2",
        source_path=source_path,
        document_format=DocumentFormat.PDF_TEXT,
    )

    parsed_document = parse_document(document, source_path)

    chunks = chunk_parsed_document(
        document=document,
        parsed_document=parsed_document,
        child_chunk_size=160,
        child_chunk_overlap=30,
    )

    parent_chunks = [
        chunk
        for chunk in chunks
        if chunk.kind == ChunkKind.PARENT
    ]
    child_chunks = [
        chunk
        for chunk in chunks
        if chunk.kind == ChunkKind.CHILD
    ]

    assert parsed_document.parse_status == ParseStatus.SUCCESS
    assert parent_chunks
    assert child_chunks

    assert all(
        chunk.page_start == 1
        and chunk.page_end == 1
        for chunk in chunks
    )
    assert all(
        chunk.document_version == "1.0"
        for chunk in chunks
    )
    assert all(
        child_chunk.parent_chunk_id
        for child_chunk in child_chunks
    )


def test_failed_parse_creates_no_chunks() -> None:
    """扫描件未经过 OCR 时，解析失败不得残留任何 chunk。"""

    source_path = (
        FIXTURE_ROOT
        / "pdf"
        / "visitor_access_registration_scan.pdf"
    )
    document = build_document(
        document_id="doc_visitor_access_scan_v1",
        source_path=source_path,
        document_format=DocumentFormat.PDF_IMAGE_ONLY,
    )

    parsed_document = parse_document(document, source_path)

    chunks = chunk_parsed_document(
        document=document,
        parsed_document=parsed_document,
    )

    assert parsed_document.parse_status == ParseStatus.FAILED
    assert chunks == []


def test_document_mismatch_is_rejected() -> None:
    """原始 Document 与 ParsedDocument 不匹配时，不能生成错误归属的 chunk。"""

    source_path = (
        FIXTURE_ROOT
        / "markdown"
        / "asset_lifecycle_sop.md"
    )
    original_document = build_document(
        document_id="doc_asset_lifecycle_v1",
        source_path=source_path,
        document_format=DocumentFormat.MARKDOWN,
    )
    parsed_document = parse_document(
        original_document,
        source_path,
    )

    wrong_document = original_document.model_copy(
        update={
            "document_id": "doc_different_source_v1",
        }
    )

    try:
        chunk_parsed_document(
            document=wrong_document,
            parsed_document=parsed_document,
        )
    except ValueError as error:
        assert (
            str(error)
            == "parsed_document.document_id must match document.document_id"
        )
        return

    raise AssertionError(
        "expected document mismatch to raise ValueError"
    )


def main() -> None:
    tests = [
        test_markdown_parent_child_relationship_and_provenance,
        test_text_pdf_chunks_preserve_page_mapping,
        test_failed_parse_creates_no_chunks,
        test_document_mismatch_is_rejected,
    ]

    for test in tests:
        test()
        print(f"PASS {test.__name__}")

    print()
    print(f"Document chunker contract: Passed {len(tests)}/{len(tests)}")


if __name__ == "__main__":
    main()