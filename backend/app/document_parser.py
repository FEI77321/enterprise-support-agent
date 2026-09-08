# 模块职责：根据文档格式选择解析器，将原始文件转换为 ParsedDocument。
# 当前支持 Markdown 和基于文本层的 PDF；扫描件会明确进入 OCR 待处理路径。

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from pypdf import PdfReader
from pypdf import __version__ as PYPDF_VERSION

from app.knowledge_models import (
    Document,
    DocumentFormat,
    PageMapEntry,
    ParsedDocument,
    ParseStatus,
)


class DocumentParser(Protocol):
    """解析器的统一接口，后续 OCR、表格解析器也要遵守这个契约。"""

    parser_name: str
    parser_version: str

    def supports(self, document_format: DocumentFormat) -> bool:
        """当前解析器能否处理该文档格式。"""

    def parse(
        self,
        document: Document,
        source_path: Path,
    ) -> ParsedDocument:
        """把原始文件解析为统一的 ParsedDocument。"""


def build_failed_result(
    document: Document,
    parser_name: str,
    parser_version: str,
    warning: str,
) -> ParsedDocument:
    """统一构造失败结果，避免失败时意外携带不可信的文本内容。"""

    return ParsedDocument(
        parsed_document_id=f"parsed_{document.document_id}",
        document_id=document.document_id,
        parser_name=parser_name,
        parser_version=parser_version,
        parse_status=ParseStatus.FAILED,
        parse_warnings=[warning],
        created_at=datetime.now(timezone.utc),
    )


class MarkdownDocumentParser:
    """直接读取 UTF-8 Markdown 文件。"""

    parser_name = "markdown"
    parser_version = "1.0"

    def supports(self, document_format: DocumentFormat) -> bool:
        return document_format == DocumentFormat.MARKDOWN

    def parse(
        self,
        document: Document,
        source_path: Path,
    ) -> ParsedDocument:
        try:
            markdown_content = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            return build_failed_result(
                document=document,
                parser_name=self.parser_name,
                parser_version=self.parser_version,
                warning=(
                    "markdown parse failed: "
                    f"{type(error).__name__}"
                ),
            )

        if not markdown_content.strip():
            return build_failed_result(
                document=document,
                parser_name=self.parser_name,
                parser_version=self.parser_version,
                warning="markdown document contains no readable text",
            )

        return ParsedDocument(
            parsed_document_id=f"parsed_{document.document_id}",
            document_id=document.document_id,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            parse_status=ParseStatus.SUCCESS,
            markdown_content=markdown_content,
            page_map=[
                PageMapEntry(
                    page_number=1,
                    char_start=0,
                    char_end=len(markdown_content),
                )
            ],
            created_at=datetime.now(timezone.utc),
        )


class PdfTextDocumentParser:
    """提取 PDF 的文本层，并把输出字符范围映射回原 PDF 页码。"""

    parser_name = "pypdf"
    parser_version = PYPDF_VERSION

    def supports(self, document_format: DocumentFormat) -> bool:
        return document_format in {
            DocumentFormat.PDF_TEXT,
            DocumentFormat.PDF_TABLE,
            DocumentFormat.PDF_IMAGE_ONLY,
        }

    def parse(
        self,
        document: Document,
        source_path: Path,
    ) -> ParsedDocument:
        try:
            reader = PdfReader(str(source_path))
        except Exception as error:
            return build_failed_result(
                document=document,
                parser_name=self.parser_name,
                parser_version=self.parser_version,
                warning=(
                    "pdf open failed: "
                    f"{type(error).__name__}"
                ),
            )

        content_parts: list[str] = []
        page_map: list[PageMapEntry] = []
        warnings: list[str] = []
        current_offset = 0

        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = (page.extract_text() or "").strip()
            except Exception as error:
                warnings.append(
                    f"page {page_number} text extraction failed: "
                    f"{type(error).__name__}"
                )
                continue

            if not page_text:
                warnings.append(
                    f"page {page_number} contains no extractable text"
                )
                continue

            if content_parts:
                content_parts.append("\n\n")
                current_offset += 2

            char_start = current_offset
            content_parts.append(page_text)
            current_offset += len(page_text)

            page_map.append(
                PageMapEntry(
                    page_number=page_number,
                    char_start=char_start,
                    char_end=current_offset,
                )
            )

        markdown_content = "".join(content_parts)

        if not markdown_content.strip():
            return build_failed_result(
                document=document,
                parser_name=self.parser_name,
                parser_version=self.parser_version,
                warning=(
                    "no extractable text found; OCR is required for "
                    "image-only PDFs"
                ),
            )

        parse_status = (
            ParseStatus.PARTIAL
            if warnings
            else ParseStatus.SUCCESS
        )

        return ParsedDocument(
            parsed_document_id=f"parsed_{document.document_id}",
            document_id=document.document_id,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            parse_status=parse_status,
            markdown_content=markdown_content,
            page_map=page_map,
            parse_warnings=warnings,
            created_at=datetime.now(timezone.utc),
        )


PARSERS: tuple[DocumentParser, ...] = (
    MarkdownDocumentParser(),
    PdfTextDocumentParser(),
)


def parse_document(
    document: Document,
    source_path: Path,
) -> ParsedDocument:
    """选择支持当前格式的解析器，并返回统一的解析结果。"""

    for parser in PARSERS:
        if parser.supports(document.document_format):
            return parser.parse(document, source_path)

    return build_failed_result(
        document=document,
        parser_name="unassigned",
        parser_version="1.0",
        warning=(
            "no parser registered for document format: "
            f"{document.document_format.value}"
        ),
    )