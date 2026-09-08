# 模块职责：验证 Markdown、文本型 PDF、图片扫描型 PDF 的解析分流契约。

from datetime import datetime
from hashlib import sha256
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.document_parser import parse_document
from app.knowledge_models import (
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


def test_markdown_parser() -> None:
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

    parsed = parse_document(document, source_path)

    assert parsed.parse_status == ParseStatus.SUCCESS
    assert parsed.markdown_content is not None
    assert "IT 资产生命周期标准操作流程" in parsed.markdown_content
    assert len(parsed.page_map) == 1
    assert parsed.page_map[0].page_number == 1
    assert parsed.page_map[0].char_start == 0
    assert parsed.page_map[0].char_end == len(parsed.markdown_content)


def test_text_pdf_parser() -> None:
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

    parsed = parse_document(document, source_path)

    assert parsed.parse_status == ParseStatus.SUCCESS
    assert parsed.markdown_content is not None
    assert "Synthetic enterprise document" in parsed.markdown_content
    assert "15" in parsed.markdown_content
    assert len(parsed.page_map) >= 1
    assert parsed.page_map[0].page_number == 1
    assert (
        parsed.page_map[-1].char_end
        == len(parsed.markdown_content)
    )


def test_image_only_pdf_requires_ocr() -> None:
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

    parsed = parse_document(document, source_path)

    assert parsed.parse_status == ParseStatus.FAILED
    assert parsed.markdown_content is None
    assert any("OCR" in warning for warning in parsed.parse_warnings)


def main() -> None:
    tests = [
        test_markdown_parser,
        test_text_pdf_parser,
        test_image_only_pdf_requires_ocr,
    ]

    for test in tests:
        test()
        print(f"PASS {test.__name__}")

    print()
    print(f"Document parser contract: Passed {len(tests)}/{len(tests)}")


if __name__ == "__main__":
    main()