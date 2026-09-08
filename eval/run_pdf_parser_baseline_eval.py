"""Day 6：记录基础 PDF 解析器在复杂表格 fixture 上的能力边界与耗时。"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.document_parser import parse_document
from app.knowledge_models import (
    Document,
    DocumentFormat,
    DocumentStatus,
    ParseStatus,
    SourceType,
)


PDF_ROOT = PROJECT_ROOT / "eval" / "fixtures" / "synthetic_corpus_v1" / "pdf"
RUN_COUNT = 5


@dataclass(frozen=True)
class PdfBaselineCase:
    filename: str
    expected_text_anchors: tuple[str, ...]


CASES = (
    PdfBaselineCase(
        filename="expense_approval_matrix.pdf",
        expected_text_anchors=(
            "费用审批矩阵",
            "费用类型",
            "金额区间",
            "直属主管",
            "5001",
        ),
    ),
    PdfBaselineCase(
        filename="network_change_window_calendar.pdf",
        expected_text_anchors=(
            "网络变更窗口日历",
            "变更等级",
            "允许窗口",
            "高风险变更",
            "冻结期",
        ),
    ),
)


def build_document(case_index: int, source_path: Path) -> Document:
    """创建仅供评测使用的版本化 Document。"""

    now = datetime.now(timezone.utc)
    return Document(
        document_id=f"doc_pdf_baseline_{case_index:03d}",
        source_type=SourceType.SYNTHETIC,
        original_filename=source_path.name,
        document_format=DocumentFormat.PDF_TABLE,
        source_object_key=str(source_path.resolve()),
        content_hash=sha256(source_path.read_bytes()).hexdigest(),
        version="1.0",
        status=DocumentStatus.PARSING,
        created_at=now,
        updated_at=now,
    )


def has_structured_markdown_table(markdown_content: str) -> bool:
    """判断文本是否保留了 Markdown 表格行，而非只含页脚中的单个竖线。"""

    return any(
        line.count("|") >= 2
        for line in markdown_content.splitlines()
    )


def evaluate_case(case_index: int, case: PdfBaselineCase) -> dict:
    source_path = PDF_ROOT / case.filename
    document = build_document(case_index, source_path)
    durations_ms: list[float] = []
    parsed_document = None

    for _ in range(RUN_COUNT):
        started_at = time.perf_counter()
        parsed_document = parse_document(document, source_path)
        durations_ms.append((time.perf_counter() - started_at) * 1000)

    assert parsed_document is not None
    markdown_content = parsed_document.markdown_content or ""
    anchor_matches = {
        anchor: anchor in markdown_content
        for anchor in case.expected_text_anchors
    }

    return {
        "filename": case.filename,
        "parse_status": parsed_document.parse_status,
        "page_count": len(parsed_document.page_map),
        "character_count": len(markdown_content),
        "warning_count": len(parsed_document.parse_warnings),
        "anchor_matches": anchor_matches,
        "structured_markdown_table": has_structured_markdown_table(
            markdown_content
        ),
        "mean_duration_ms": sum(durations_ms) / len(durations_ms),
        "min_duration_ms": min(durations_ms),
        "max_duration_ms": max(durations_ms),
    }


def main() -> None:
    for case_index, case in enumerate(CASES, start=1):
        result = evaluate_case(case_index, case)
        assert result["parse_status"] == ParseStatus.SUCCESS
        assert result["page_count"] == 1
        assert all(result["anchor_matches"].values())
        assert not result["structured_markdown_table"]

        print(f"PASS {result['filename']}")
        print(
            "  text_anchor_coverage="
            f"{sum(result['anchor_matches'].values())}"
            f"/{len(result['anchor_matches'])}"
        )
        print(
            "  table_structure_preserved="
            f"{result['structured_markdown_table']}"
        )
        print(
            "  timing_ms="
            f"mean={result['mean_duration_ms']:.3f}, "
            f"min={result['min_duration_ms']:.3f}, "
            f"max={result['max_duration_ms']:.3f}"
        )

    print("\nPDF parser baseline: Passed 2/2")
    print(
        "Status: pypdf preserves text anchors and page mapping, "
        "but does not preserve table rows and columns as Markdown."
    )


if __name__ == "__main__":
    main()
