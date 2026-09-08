# 模块职责：验证 synthetic 黄金集中的 answer 用例，
# 是否能在当前解析与切块结果中动态定位到相关 Child Chunk。
# 该脚本不运行检索算法，不计算 Recall/MRR/nDCG/FPR。

from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.knowledge_models import ChunkKind, ParseStatus
from run_synthetic_ingestion_evidence_coverage_eval import (
    CORPUS_ROOT,
    ingest_synthetic_corpus,
    load_json,
    normalize_evidence_text,
)


ASSERTIONS_PATH = (
    CORPUS_ROOT
    / "synthetic_retrieval_assertions_v1.json"
)
MANIFEST_PATH = CORPUS_ROOT / "manifest.json"
GOLDEN_CASES_PATH = (
    CORPUS_ROOT
    / "synthetic_golden_cases_v1.json"
)


def contains_all_terms(
    text: str,
    required_terms: list[str],
) -> bool:
    """判断一个 chunk 是否包含全部必需事实锚点。"""

    normalized_text = normalize_evidence_text(text)

    return all(
        normalize_evidence_text(term) in normalized_text
        for term in required_terms
    )


def get_required_terms(
    case: dict,
    answer_term_overrides: dict[str, list[str]],
) -> list[str]:
    """优先使用版本化覆盖；没有覆盖时沿用冻结黄金集的答案锚点。"""

    return answer_term_overrides.get(
        case["id"],
        case["expected_answer_contains"],
    )


def resolve_relevant_child_chunk_ids(
    case: dict,
    ingested_documents: dict[str, dict],
    answer_term_overrides: dict[str, list[str]],
) -> list[str]:
    """按文档、版本、页码与事实锚点动态解析当前相关 Child Chunk。"""

    document_id = case["expected_document_id"]

    if not document_id:
        raise ValueError(
            f"{case['id']}: answer case requires expected_document_id"
        )

    if document_id not in ingested_documents:
        raise ValueError(
            f"{case['id']}: expected document was not ingested: "
            f"{document_id}"
        )

    result = ingested_documents[document_id]
    document = result["document"]
    parsed_document = result["parsed_document"]
    chunks = result["chunks"]

    if document.version != case["expected_document_version"]:
        raise ValueError(
            f"{case['id']}: document version mismatch, "
            f"expected={case['expected_document_version']}, "
            f"actual={document.version}"
        )

    if parsed_document.parse_status == ParseStatus.FAILED:
        raise AssertionError(
            f"{case['id']}: expected answer document failed parsing"
        )

    required_terms = get_required_terms(
        case=case,
        answer_term_overrides=answer_term_overrides,
    )

    if not required_terms:
        raise ValueError(
            f"{case['id']}: answer case requires fact anchors"
        )

    expected_page = case.get("expected_page")
    relevant_chunk_ids: list[str] = []

    for chunk in chunks:
        if chunk.kind != ChunkKind.CHILD:
            continue

        if expected_page is not None:
            page_matches = (
                chunk.page_start
                <= expected_page
                <= chunk.page_end
            )

            if not page_matches:
                continue

        if contains_all_terms(
            text=chunk.content,
            required_terms=required_terms,
        ):
            relevant_chunk_ids.append(chunk.chunk_id)

    return relevant_chunk_ids


def main() -> None:
    manifest = load_json(MANIFEST_PATH)
    golden_suite = load_json(GOLDEN_CASES_PATH)
    assertions = load_json(ASSERTIONS_PATH)

    if assertions["corpus_id"] != manifest["corpus_id"]:
        raise ValueError("assertions and manifest corpus_id do not match")

    if assertions["corpus_id"] != golden_suite["corpus_id"]:
        raise ValueError(
            "assertions and golden suite corpus_id do not match"
        )

    if (
        assertions["source_golden_suite"]
        != GOLDEN_CASES_PATH.name
    ):
        raise ValueError(
            "assertions source_golden_suite does not match "
            "the loaded golden suite"
        )

    answer_cases = [
        case
        for case in golden_suite["cases"]
        if case["expected_action"] == "answer"
    ]
    answer_case_ids = {
        case["id"]
        for case in answer_cases
    }

    answer_term_overrides = assertions[
        "answer_term_overrides"
    ]

    unknown_override_ids = (
        set(answer_term_overrides)
        - answer_case_ids
    )

    if unknown_override_ids:
        raise ValueError(
            "answer_term_overrides contains unknown case IDs: "
            f"{sorted(unknown_override_ids)}"
        )

    ingested_documents = ingest_synthetic_corpus(manifest)

    resolved_case_count = 0

    for case in answer_cases:
        relevant_chunk_ids = resolve_relevant_child_chunk_ids(
            case=case,
            ingested_documents=ingested_documents,
            answer_term_overrides=answer_term_overrides,
        )

        if not relevant_chunk_ids:
            raise AssertionError(
                f"{case['id']}: no relevant Child Chunk could be "
                "resolved from its required fact anchors"
            )

        resolved_case_count += 1

        print(
            f"PASS {case['id']}: "
            f"relevant_child_chunks={relevant_chunk_ids}"
        )

    print()
    print(
        "Synthetic retrieval-ready contract: "
        f"Passed {resolved_case_count}/{len(answer_cases)}"
    )
    print(
        "Status: relevant Child Chunk ground truth is resolved "
        "dynamically; no retrieval ranking metric was calculated."
    )


if __name__ == "__main__":
    main()