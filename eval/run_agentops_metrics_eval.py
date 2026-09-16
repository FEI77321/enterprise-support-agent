"""验证 AgentOps 指标与 Trace Timeline 都来自结构化执行记录。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.models import ChatResponse
from app.trace_store import get_agentops_metrics, get_trace_timeline, persist_trace


def response(request_id: str, *, blocked: bool = False, rewritten: bool = False, failed_tool: bool = False) -> ChatResponse:
    return ChatResponse(
        request_id=request_id, type="clarify" if blocked else "answer", answer="ok",
        workflow_steps=["input_guard"], safety={"action": "block" if blocked else "allow", "reason": "test"},
        query_rewrite={"triggered": rewritten}, memory={"write": {"action": "skip"}},
        harness_trace=[{"tool_name": "search_knowledge_base", "status": "failed" if failed_tool else "completed", "elapsed_ms": 3.0}],
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Path(temp_dir) / "agentops.db"
        os.environ["TRACE_PERSISTENCE_ENABLED"] = "true"
        persist_trace(response("ops-1", rewritten=True), original_message="a", effective_query="a", engine="rules", database_path=database)
        persist_trace(response("ops-2", blocked=True, failed_tool=True), original_message="b", effective_query="b", engine="rules", database_path=database)
        metrics = get_agentops_metrics(database)
        timeline = get_trace_timeline("ops-1", database)
        checks = [
            metrics["trace_runs"] == 2,
            metrics["prompt_injection_block_rate"] == 0.5,
            metrics["query_rewrite_trigger_rate"] == 0.5,
            metrics["tool_failure_rate"] == 0.5,
            timeline is not None and {item["name"] for item in timeline} >= {"input_guard", "memory", "response"},
        ]
    assert all(checks), checks
    print(f"AgentOps metrics and timeline: Passed {len(checks)}/{len(checks)}")


if __name__ == "__main__":
    main()
