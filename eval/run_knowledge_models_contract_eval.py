# 模块职责：验证 Day 4 知识库数据契约的字段、版本关系、父子 chunk 与来源信息。

from datetime import datetime

from pydantic import ValidationError

from eval_path import setup_backend_path

setup_backend_path()

from app.knowledge_models import (
    ChunkIndexStatus,
    ChunkKind,
    Document,
    DocumentFormat,
    DocumentStatus,
    KnowledgeChunk,
    PageMapEntry,
    ParsedDocument,
    ParseStatus,
    RetrievalResult,
    SourceType,
)


HASH_A = "a" * 64
HASH_B = "b" * 64
NOW = datetime(2026, 9, 8, 12, 0, 0)


def expect_validation_error(callback) -> None:
    try:
        callback()
    except ValidationError:
        return

    raise AssertionError("expected ValidationError")


def test_version_relationship() -> None:
    old_document = Document(
        document_id="doc_remote_access_v1",
        source_type=SourceType.SYNTHETIC,
        original_filename="remote_access_security_policy_v1.pdf",
        document_format=DocumentFormat.PDF_TEXT,
        source_object_key="synthetic/remote_access_security_policy_v1.pdf",
        content_hash=HASH_A,
        version="1.0",
        status=DocumentStatus.INDEXED,
        created_at=NOW,
        updated_at=NOW,
    )

    new_document = Document(
        document_id="doc_remote_access_v2",
        source_type=SourceType.SYNTHETIC,
        original_filename="remote_access_security_policy_v2.pdf",
        document_format=DocumentFormat.PDF_TEXT,
        source_object_key="synthetic/remote_access_security_policy_v2.pdf",
        content_hash=HASH_B,
        version="2.0",
        previous_version_document_id=old_document.document_id,
        status=DocumentStatus.INDEXED,
        created_at=NOW,
        updated_at=NOW,
    )

    assert new_document.previous_version_document_id == old_document.document_id

    expect_validation_error(
        lambda: Document(
            document_id="doc_invalid_v1",
            source_type=SourceType.SYNTHETIC,
            original_filename="invalid.pdf",
            document_format=DocumentFormat.PDF_TEXT,
            source_object_key="synthetic/invalid.pdf",
            content_hash=HASH_A,
            version="1.0",
            previous_version_document_id="doc_remote_access_v1",
            created_at=NOW,
            updated_at=NOW,
        )
    )


def test_parse_contract() -> None:
    parsed = ParsedDocument(
        parsed_document_id="parsed_remote_access_v2",
        document_id="doc_remote_access_v2",
        parser_name="pypdf",
        parser_version="1.0",
        parse_status=ParseStatus.SUCCESS,
        markdown_content=(
            "# 远程访问安全规范\n\n"
            "远程会话闲置超过 15 分钟时自动断开。"
        ),
        page_map=[
            PageMapEntry(
                page_number=1,
                char_start=0,
                char_end=30,
            )
        ],
        created_at=NOW,
    )

    assert parsed.parse_status == ParseStatus.SUCCESS

    expect_validation_error(
        lambda: ParsedDocument(
            parsed_document_id="parsed_failed_but_has_content",
            document_id="doc_remote_access_v2",
            parser_name="pypdf",
            parser_version="1.0",
            parse_status=ParseStatus.FAILED,
            markdown_content="不应该存在的解析内容",
            created_at=NOW,
        )
    )


def test_parent_child_chunk_contract() -> None:
    parent = KnowledgeChunk(
        chunk_id="chunk_remote_access_parent_001",
        document_id="doc_remote_access_v2",
        parsed_document_id="parsed_remote_access_v2",
        document_version="2.0",
        kind=ChunkKind.PARENT,
        heading_path=["远程访问安全规范", "访问控制"],
        page_start=1,
        page_end=1,
        content="远程会话闲置超过 15 分钟时自动断开。",
        content_hash=HASH_A,
        index_status=ChunkIndexStatus.INDEXED,
    )

    child = KnowledgeChunk(
        chunk_id="chunk_remote_access_child_001",
        document_id="doc_remote_access_v2",
        parsed_document_id="parsed_remote_access_v2",
        document_version="2.0",
        kind=ChunkKind.CHILD,
        parent_chunk_id=parent.chunk_id,
        heading_path=["远程访问安全规范", "访问控制"],
        page_start=1,
        page_end=1,
        content="远程会话闲置超过 15 分钟时自动断开。",
        content_hash=HASH_B,
        index_status=ChunkIndexStatus.INDEXED,
    )

    assert child.parent_chunk_id == parent.chunk_id

    expect_validation_error(
        lambda: KnowledgeChunk(
            chunk_id="chunk_invalid_parent",
            document_id="doc_remote_access_v2",
            parsed_document_id="parsed_remote_access_v2",
            document_version="2.0",
            kind=ChunkKind.PARENT,
            parent_chunk_id=parent.chunk_id,
            page_start=1,
            page_end=1,
            content="错误父块",
            content_hash=HASH_A,
        )
    )


def test_retrieval_result_contract() -> None:
    result = RetrievalResult(
        request_id="request_contract_eval_001",
        rank=1,
        chunk_id="chunk_remote_access_child_001",
        context_chunk_id="chunk_remote_access_parent_001",
        document_id="doc_remote_access_v2",
        document_version="2.0",
        source_filename="remote_access_security_policy_v2.pdf",
        page_start=1,
        page_end=1,
        content="远程会话闲置超过 15 分钟时自动断开。",
        score=0.95,
        retrieval_strategy="hybrid_rrf",
    )

    assert result.context_chunk_id == "chunk_remote_access_parent_001"


def main() -> None:
    tests = [
        test_version_relationship,
        test_parse_contract,
        test_parent_child_chunk_contract,
        test_retrieval_result_contract,
    ]

    for test in tests:
        test()
        print(f"PASS {test.__name__}")

    print()
    print(f"Knowledge models contract: Passed {len(tests)}/{len(tests)}")


if __name__ == "__main__":
    main()
