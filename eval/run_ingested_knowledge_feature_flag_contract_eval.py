"""验证 RAG 2.0 实验检索开关默认关闭且可受控返回来源回链。"""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent import handle_message
from app.database import get_connection
from app.knowledge_ingestion_service import ingest_document
from app.knowledge_models import DocumentFormat, SourceType
from app.knowledge_repository import mark_active_document_chunks_indexed
from app.tool_registry import ToolResult


MARKDOWN_FIXTURE = (
    PROJECT_ROOT
    / "eval"
    / "fixtures"
    / "synthetic_corpus_v1"
    / "markdown"
    / "asset_lifecycle_sop.md"
)


@contextmanager
def temporary_environment(**updates: str | None):
    previous_values = {name: os.environ.get(name) for name in updates}
    try:
        for name, value in updates.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in previous_values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def fake_old_tool_result(tool_name: str, **_kwargs) -> ToolResult:
    if tool_name == "search_knowledge_base":
        return ToolResult(
            tool_name=tool_name,
            success=True,
            data={"results": []},
        )

    if tool_name == "search_vector_store":
        return ToolResult(
            tool_name=tool_name,
            success=True,
            data={"results": []},
        )

    if tool_name == "create_ticket":
        return ToolResult(
            tool_name=tool_name,
            success=True,
            data={
                "ticket": {
                    "ticket_id": "TICKET-20260908-9999",
                    "title": "实验开关契约工单",
                    "description": "仅用于 feature flag 契约测试",
                    "category": "其他",
                    "priority": "LOW",
                    "status": "OPEN",
                    "assignee": "IT 支持组",
                    "created_at": "2026-09-08T00:00:00+00:00",
                }
            },
        )

    raise AssertionError(f"unexpected old tool call: {tool_name}")


def mark_indexed(database_path: str, document_id: str) -> None:
    connection = get_connection(Path(database_path))
    try:
        with connection:
            marked_count = mark_active_document_chunks_indexed(
                connection=connection,
                document_id=document_id,
                indexed_at=datetime.now(timezone.utc).isoformat(),
            )
        assert marked_count > 0
    finally:
        connection.close()


def test_flag_disabled_does_not_call_experimental_retriever() -> None:
    with temporary_environment(
        ENABLE_LLM_ANSWER="false",
        INGESTED_KNOWLEDGE_EXPERIMENT_ENABLED=None,
    ):
        with patch(
            "app.agent.search_ingested_knowledge",
            side_effect=AssertionError("flag-disabled request must not query RAG 2.0"),
        ), patch("app.agent.run_tool", side_effect=fake_old_tool_result):
            response = handle_message(
                "显示器",
                request_id="request_flag_disabled_001",
            )

    assert "search_ingested_knowledge_experiment" not in response.workflow_steps
    assert response.type == "ticket_created"


def test_flag_enabled_returns_experimental_source_reference(
    database_path: str,
) -> None:
    ingestion = ingest_document(
        source_path=MARKDOWN_FIXTURE,
        logical_document_id="asset_lifecycle_sop",
        version="1.0",
        source_type=SourceType.SYNTHETIC,
        document_format=DocumentFormat.MARKDOWN,
        database_path=database_path,
    )
    mark_indexed(database_path, ingestion.document_id)

    with temporary_environment(
        ENABLE_LLM_ANSWER="false",
        INGESTED_KNOWLEDGE_EXPERIMENT_ENABLED="true",
        INGESTED_KNOWLEDGE_DATABASE_PATH=database_path,
    ):
        with patch("app.agent.run_tool", side_effect=fake_old_tool_result):
            response = handle_message(
                "显示器",
                request_id="request_flag_enabled_001",
            )

    assert response.type == "answer"
    assert "search_knowledge_base" in response.workflow_steps
    assert "search_ingested_knowledge_experiment" in response.workflow_steps
    assert "ingested_knowledge_experiment_answer" in response.workflow_steps
    assert response.sources

    source = response.sources[0]
    assert source.file == MARKDOWN_FIXTURE.name
    assert source.document_id == ingestion.document_id
    assert source.document_version == "1.0"
    assert source.heading_path
    assert source.page_start == 1
    assert source.page_end == 1


def main() -> None:
    test_flag_disabled_does_not_call_experimental_retriever()
    print("PASS test_flag_disabled_does_not_call_experimental_retriever")

    with tempfile.TemporaryDirectory(prefix="ingested-feature-flag-") as temp_dir:
        test_flag_enabled_returns_experimental_source_reference(
            str(Path(temp_dir) / "feature_flag.db")
        )
    print("PASS test_flag_enabled_returns_experimental_source_reference")

    print("\nIngested knowledge feature flag contract: Passed 2/2")


if __name__ == "__main__":
    main()
