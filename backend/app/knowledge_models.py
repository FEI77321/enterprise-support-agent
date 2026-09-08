# 模块职责：定义企业知识库文档摄入、解析、切块与检索结果的数据契约。
# 这些模型暂不接入主 Agent，只作为后续 PDF、版本治理和向量索引的统一边界。

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


IDENTIFIER_PATTERN = r"^[A-Za-z][A-Za-z0-9_:-]{2,127}$"
SHA256_PATTERN = r"^[a-f0-9]{64}$"
VERSION_PATTERN = r"^\d+\.\d+$"


class SourceType(str, Enum):
    SYNTHETIC = "synthetic"
    USER_AUTHORIZED = "user_authorized"
    PUBLIC = "public"


class DocumentFormat(str, Enum):
    MARKDOWN = "markdown"
    PDF_TEXT = "pdf_text"
    PDF_TABLE = "pdf_table"
    PDF_IMAGE_ONLY = "pdf_image_only"


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class ParseStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ChunkKind(str, Enum):
    PARENT = "parent"
    CHILD = "child"


class ChunkIndexStatus(str, Enum):
    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"
    REMOVED = "removed"


class PageMapEntry(BaseModel):
    """解析文本中的一段字符范围，来自原文档的哪一页。"""

    page_number: int = Field(..., ge=1)
    char_start: int = Field(..., ge=0)
    char_end: int = Field(..., ge=0)

    @model_validator(mode="after")
    def validate_character_range(self) -> "PageMapEntry":
        if self.char_end < self.char_start:
            raise ValueError(
                "char_end must be greater than or equal to char_start"
            )
        return self


class Document(BaseModel):
    """原始文件及其版本元数据。"""

    document_id: str = Field(..., pattern=IDENTIFIER_PATTERN)
    source_type: SourceType
    original_filename: str = Field(..., min_length=1, max_length=255)
    document_format: DocumentFormat
    source_object_key: str = Field(..., min_length=1)
    content_hash: str = Field(..., pattern=SHA256_PATTERN)

    version: str = Field(..., pattern=VERSION_PATTERN)
    previous_version_document_id: str | None = Field(default=None)

    status: DocumentStatus = DocumentStatus.UPLOADED
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_version_relationship(self) -> "Document":
        if self.previous_version_document_id == self.document_id:
            raise ValueError(
                "previous_version_document_id cannot equal document_id"
            )

        if self.version == "1.0" and self.previous_version_document_id:
            raise ValueError(
                "version 1.0 cannot declare a previous version document"
            )

        return self


class ParsedDocument(BaseModel):
    """某个原始文档经某种解析器处理后的结构化结果。"""

    parsed_document_id: str = Field(..., pattern=IDENTIFIER_PATTERN)
    document_id: str = Field(..., pattern=IDENTIFIER_PATTERN)

    parser_name: str = Field(..., min_length=1)
    parser_version: str = Field(..., min_length=1)
    parse_status: ParseStatus

    markdown_content: str | None = Field(default=None)
    page_map: list[PageMapEntry] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)

    created_at: datetime

    @model_validator(mode="after")
    def validate_parse_result(self) -> "ParsedDocument":
        has_content = bool(self.markdown_content and self.markdown_content.strip())

        if self.parse_status == ParseStatus.SUCCESS and not has_content:
            raise ValueError(
                "a successful parse must contain markdown_content"
            )

        if self.parse_status == ParseStatus.FAILED and has_content:
            raise ValueError(
                "a failed parse must not contain markdown_content"
            )

        return self


class KnowledgeChunk(BaseModel):
    """可检索的父块或子块，保留来源、标题路径与页码信息。"""

    chunk_id: str = Field(..., pattern=IDENTIFIER_PATTERN)
    document_id: str = Field(..., pattern=IDENTIFIER_PATTERN)
    parsed_document_id: str = Field(..., pattern=IDENTIFIER_PATTERN)

    document_version: str = Field(..., pattern=VERSION_PATTERN)
    kind: ChunkKind
    parent_chunk_id: str | None = Field(default=None)

    heading_path: list[str] = Field(default_factory=list)
    page_start: int = Field(..., ge=1)
    page_end: int = Field(..., ge=1)

    content: str = Field(..., min_length=1)
    content_hash: str = Field(..., pattern=SHA256_PATTERN)

    index_status: ChunkIndexStatus = ChunkIndexStatus.PENDING

    @model_validator(mode="after")
    def validate_chunk_relationship(self) -> "KnowledgeChunk":
        if self.page_end < self.page_start:
            raise ValueError(
                "page_end must be greater than or equal to page_start"
            )

        if self.kind == ChunkKind.PARENT and self.parent_chunk_id is not None:
            raise ValueError("a parent chunk cannot have parent_chunk_id")

        if self.parent_chunk_id == self.chunk_id:
            raise ValueError("a chunk cannot be its own parent")

        return self


class RetrievalResult(BaseModel):
    """一次检索返回给编排层的标准证据对象。"""

    request_id: str = Field(..., min_length=1)
    rank: int = Field(..., ge=1)

    chunk_id: str = Field(..., pattern=IDENTIFIER_PATTERN)
    context_chunk_id: str | None = Field(default=None)

    document_id: str = Field(..., pattern=IDENTIFIER_PATTERN)
    document_version: str = Field(..., pattern=VERSION_PATTERN)
    source_filename: str = Field(..., min_length=1)
    heading_path: list[str] = Field(default_factory=list)

    page_start: int = Field(..., ge=1)
    page_end: int = Field(..., ge=1)

    content: str = Field(..., min_length=1)
    score: float
    retrieval_strategy: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_result_pages(self) -> "RetrievalResult":
        if self.page_end < self.page_start:
            raise ValueError(
                "page_end must be greater than or equal to page_start"
            )
        return self
