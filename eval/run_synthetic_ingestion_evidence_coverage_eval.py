# 模块职责：评估 synthetic 语料经解析和切块后，
# 黄金集证据是否仍可在解析全文及 Child Chunk 中被找到。
# 注意：这是摄入质量基线，不是主 Agent 的检索指标评测。

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re

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

CORPUS_ROOT = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "synthetic_corpus_v1"
)
MANIFEST_PATH = CORPUS_ROOT / "manifest.json"
GOLDEN_CASES_PATH = CORPUS_ROOT / "synthetic_golden_cases_v1.json"

FORMAT_MAP = {
    "markdown": DocumentFormat.MARKDOWN,
    "pdf_text": DocumentFormat.PDF_TEXT,
    "pdf_table": DocumentFormat.PDF_TABLE,
    "pdf_image_only": DocumentFormat.PDF_IMAGE_ONLY,
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_evidence_text(value: str) -> str:
    """移除 PDF 或表格解析产生的空白差异，用于事实证据匹配。"""

    return re.sub(r"\s+", "", value)


def contains_all_fact_anchors(
    parsed_text: str,
    expected_answer_contains: list[str],
) -> bool:
    """判断解析文本是否保留了该用例要求的全部关键事实。"""

    normalized_parsed_text = normalize_evidence_text(parsed_text)

    return all(
        normalize_evidence_text(anchor)
        in normalized_parsed_text
        for anchor in expected_answer_contains
    )


def build_document(manifest_document: dict) -> tuple[Document, Path]:
    """根据 manifest 记录构造 Document 与真实文件路径。"""

    source_path = CORPUS_ROOT / manifest_document["path"]

    document = Document(
        document_id=manifest_document["document_id"],
        source_type=SourceType.SYNTHETIC,
        original_filename=source_path.name,
        document_format=FORMAT_MAP[manifest_document["format"]],
        source_object_key=manifest_document["path"],
        content_hash=sha256(source_path.read_bytes()).hexdigest(),
        version=manifest_document["version"],
        previous_version_document_id=manifest_document.get(
            "supersedes"
        ),
        created_at=NOW,
        updated_at=NOW,
    )

    return document, source_path


def ingest_synthetic_corpus(
    manifest: dict,
) -> dict[str, dict]:
    """在内存中完成 manifest 文档的解析与切块，不写 SQLite/Chroma。"""

    ingested_documents: dict[str, dict] = {}

    for manifest_document in manifest["documents"]:
        document, source_path = build_document(manifest_document)

        parsed_document = parse_document(
            document=document,
            source_path=source_path,
        )
        chunks = chunk_parsed_document(
            document=document,
            parsed_document=parsed_document,
            child_chunk_size=400,
            child_chunk_overlap=60,
        )

        ingested_documents[document.document_id] = {
            "manifest_document": manifest_document,
            "document": document,
            "parsed_document": parsed_document,
            "chunks": chunks,
        }

    return ingested_documents


def main() -> None:
    manifest = load_json(MANIFEST_PATH)
    golden_suite = load_json(GOLDEN_CASES_PATH)

    if golden_suite["corpus_id"] != manifest["corpus_id"]:
        raise ValueError("golden suite and manifest corpus_id do not match")

    ingested_documents = ingest_synthetic_corpus(manifest)

    total_documents = len(ingested_documents)
    parse_success_count = 0
    parse_failed_count = 0
    parent_chunk_count = 0
    child_chunk_count = 0

    for result in ingested_documents.values():
        parsed_document = result["parsed_document"]
        chunks = result["chunks"]

        if parsed_document.parse_status == ParseStatus.FAILED:
            parse_failed_count += 1
        else:
            parse_success_count += 1

        parent_chunk_count += sum(
            chunk.kind == ChunkKind.PARENT
            for chunk in chunks
        )
        child_chunk_count += sum(
            chunk.kind == ChunkKind.CHILD
            for chunk in chunks
        )

    answer_cases = [
        case
        for case in golden_suite["cases"]
        if case["expected_action"] == "answer"
    ]
    needs_ocr_cases = [
        case
        for case in golden_suite["cases"]
        if case["expected_action"] == "needs_ocr"
    ]
    refuse_cases = [
        case
        for case in golden_suite["cases"]
        if case["expected_action"] == "refuse"
    ]

    raw_exact_hits = 0
    normalized_evidence_hits = 0
    normalized_anchor_hits = 0
    usable_evidence_hits = 0
    child_chunk_evidence_hits = 0

    unresolved_parsed_cases: list[dict] = []
    unresolved_child_chunk_cases: list[dict] = []
    annotation_conflicts: list[dict] = []

    for case in answer_cases:
        document_id = case["expected_document_id"]
        expected_evidence_text = case["expected_evidence_text"]

        if document_id not in ingested_documents:
            raise ValueError(
                f"{case['id']}: expected document is not ingested: "
                f"{document_id}"
            )

        result = ingested_documents[document_id]
        parsed_document = result["parsed_document"]
        chunks = result["chunks"]

        parsed_text = parsed_document.markdown_content or ""

        raw_exact_found = (
            expected_evidence_text in parsed_text
        )
        normalized_evidence_found = (
            normalize_evidence_text(expected_evidence_text)
            in normalize_evidence_text(parsed_text)
        )
        normalized_anchors_found = contains_all_fact_anchors(
            parsed_text=parsed_text,
            expected_answer_contains=case["expected_answer_contains"],
        )
        usable_evidence_found = (
            normalized_evidence_found
            or normalized_anchors_found
        )

        child_chunk_evidence_found = any(
            (
                normalize_evidence_text(expected_evidence_text)
                in normalize_evidence_text(chunk.content)
            )
            or contains_all_fact_anchors(
                parsed_text=chunk.content,
                expected_answer_contains=(
                    case["expected_answer_contains"]
                ),
            )
            for chunk in chunks
            if chunk.kind == ChunkKind.CHILD
        )

        if raw_exact_found:
            raw_exact_hits += 1

        if normalized_evidence_found:
            normalized_evidence_hits += 1

        if normalized_anchors_found:
            normalized_anchor_hits += 1

        if usable_evidence_found:
            usable_evidence_hits += 1

        if child_chunk_evidence_found:
            child_chunk_evidence_hits += 1

        if not usable_evidence_found:
            unresolved_parsed_cases.append(
                {
                    "case_id": case["id"],
                    "document_id": document_id,
                    "document_format": (
                        result["manifest_document"]["format"]
                    ),
                    "parse_status": (
                        parsed_document.parse_status.value
                    ),
                    "raw_exact_found": raw_exact_found,
                    "normalized_evidence_found": (
                        normalized_evidence_found
                    ),
                    "normalized_anchors_found": (
                        normalized_anchors_found
                    ),
                    "expected_evidence_text": expected_evidence_text,
                }
            )

        if not child_chunk_evidence_found:
            unresolved_child_chunk_cases.append(
                {
                    "case_id": case["id"],
                    "document_id": document_id,
                    "document_format": (
                        result["manifest_document"]["format"]
                    ),
                }
            )

        if (
            normalized_evidence_found
            and not normalized_anchors_found
        ):
            annotation_conflicts.append(
                {
                    "case_id": case["id"],
                    "document_id": document_id,
                    "expected_answer_contains": (
                        case["expected_answer_contains"]
                    ),
                    "expected_evidence_text": expected_evidence_text,
                }
            )

    ocr_routing_hits = 0

    for case in needs_ocr_cases:
        document_id = case["expected_document_id"]

        if document_id not in ingested_documents:
            raise ValueError(
                f"{case['id']}: OCR document is not ingested: "
                f"{document_id}"
            )

        result = ingested_documents[document_id]
        parsed_document = result["parsed_document"]
        chunks = result["chunks"]

        routed_to_ocr = (
            parsed_document.parse_status == ParseStatus.FAILED
            and chunks == []
            and any(
                "OCR" in warning
                for warning in parsed_document.parse_warnings
            )
        )

        if routed_to_ocr:
            ocr_routing_hits += 1
        else:
            raise AssertionError(
                f"{case['id']}: image-only PDF must fail parsing "
                "and produce no chunks"
            )

    print(
        "Synthetic ingestion baseline "
        f"for corpus={manifest['corpus_id']}"
    )
    print(
        f"Documents: total={total_documents}, "
        f"parse_success={parse_success_count}, "
        f"parse_failed={parse_failed_count}"
    )
    print(
        f"Chunks: parents={parent_chunk_count}, "
        f"children={child_chunk_count}"
    )
    print(
        "Answer raw exact evidence coverage: "
        f"{raw_exact_hits}/{len(answer_cases)}"
    )
    print(
        "Answer normalized evidence coverage: "
        f"{normalized_evidence_hits}/{len(answer_cases)}"
    )
    print(
        "Answer normalized fact-anchor coverage: "
        f"{normalized_anchor_hits}/{len(answer_cases)}"
    )
    print(
        "Answer usable evidence coverage in ParsedDocument: "
        f"{usable_evidence_hits}/{len(answer_cases)}"
    )
    print(
        "Answer usable evidence coverage in ChildChunk: "
        f"{child_chunk_evidence_hits}/{len(answer_cases)}"
    )
    print(
        f"OCR routing: {ocr_routing_hits}/{len(needs_ocr_cases)}"
    )
    print(
        "Refuse cases: "
        f"{len(refuse_cases)} "
        "(reserved for later false-positive / refusal evaluation)"
    )

    if unresolved_parsed_cases:
        print()
        print(
            "Unresolved parsed evidence cases "
            "(baseline findings, not a script failure):"
        )

        for case in unresolved_parsed_cases:
            print(
                f"- {case['case_id']} | "
                f"document={case['document_id']} | "
                f"format={case['document_format']} | "
                f"parse_status={case['parse_status']} | "
                f"raw_exact_found={case['raw_exact_found']} | "
                "normalized_evidence_found="
                f"{case['normalized_evidence_found']} | "
                "normalized_anchors_found="
                f"{case['normalized_anchors_found']}"
            )

    if unresolved_child_chunk_cases:
        print()
        print(
            "Unresolved child-chunk evidence cases "
            "(chunking findings, not a script failure):"
        )

        for case in unresolved_child_chunk_cases:
            print(
                f"- {case['case_id']} | "
                f"document={case['document_id']} | "
                f"format={case['document_format']}"
            )

    if annotation_conflicts:
        print()
        print(
            "Annotation conflicts "
            "(evidence exists, but answer anchors differ):"
        )

        for conflict in annotation_conflicts:
            print(
                f"- {conflict['case_id']} | "
                f"document={conflict['document_id']}"
            )

    print()
    print(
        "Status: ingestion evidence baseline only; "
        "no Recall/MRR/nDCG/FPR metric was calculated."
    )


if __name__ == "__main__":
    main()
