"""Bad Case 生命周期与 Dataset 回流的离线契约回归。"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from eval_path import setup_backend_path

setup_backend_path()

from app.bad_case_store import create_bad_case, export_bad_case_as_eval_case, export_regression_dataset, get_bad_case, transition_bad_case
from app.models import ChatResponse
from app.trace_store import get_agentops_metrics, persist_trace
from export_bad_case_dataset import write_dataset


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    passed = 0
    with TemporaryDirectory() as directory:
        database_path = Path(directory) / "bad-case.db"
        output_path = Path(directory) / "dataset.json"
        response = ChatResponse(
            request_id="trace-bad-case-001", type="answer", answer="错误的回答",
            workflow_steps=["retrieve", "respond"], safety={"action": "allow"},
        )
        persist_trace(response, original_message="VPN 连不上该怎么办？", effective_query="VPN 连不上", engine="rules", database_path=database_path)

        bad_case = create_bad_case(
            request_id=response.request_id, category="retrieval", severity="high",
            expected_behavior="应引用 VPN 排障文档并给出可执行步骤",
            actual_behavior="未检索到来源且给出泛化回答", reporter_id="qa-01", database_path=database_path,
        )
        expect(bad_case["status"] == "open", "new bad case must be open")
        expect(len(get_bad_case(bad_case["bad_case_id"], database_path)["events"]) == 1, "creation needs an audit event")
        passed += 2

        persist_trace(response, original_message="VPN 连不上该怎么办？", effective_query="VPN 连不上", engine="rules", database_path=database_path)
        expect(get_bad_case(bad_case["bad_case_id"], database_path) is not None, "trace refresh must preserve bad case relation")
        passed += 1

        try:
            export_bad_case_as_eval_case(bad_case["bad_case_id"], database_path)
            raise AssertionError("open bad case must not export")
        except ValueError as exc:
            expect(str(exc) == "bad_case_not_ready_for_regression", "export guard mismatch")
        passed += 1

        triaged = transition_bad_case(bad_case["bad_case_id"], "triaged", actor_id="support-01", database_path=database_path)
        expect(triaged["status"] == "triaged" and len(triaged["events"]) == 2, "triage lifecycle mismatch")
        passed += 1

        added = transition_bad_case(bad_case["bad_case_id"], "regression_added", actor_id="qa-01", database_path=database_path)
        exported_case = export_bad_case_as_eval_case(added["bad_case_id"], database_path)
        expect(exported_case["input"] == "VPN 连不上该怎么办？", "regression input must come from trace")
        expect(exported_case["case_id"] == added["regression_case_id"], "regression case id mismatch")
        passed += 2

        resolved = transition_bad_case(bad_case["bad_case_id"], "resolved", actor_id="support-01", database_path=database_path)
        dataset = export_regression_dataset(database_path)
        written = write_dataset(output_path, database_path)
        expect(resolved["resolved_at"] is not None and dataset["case_count"] == 1, "resolved case must remain in regression dataset")
        expect(json.loads(output_path.read_text(encoding="utf-8"))["case_count"] == written["case_count"] == 1, "dataset export file mismatch")
        passed += 2

        metrics = get_agentops_metrics(database_path)
        expect(metrics["bad_cases"] == {"resolved": 1} and metrics["open_bad_case_count"] == 0, "AgentOps bad case metrics mismatch")
        passed += 1

    print(f"Bad Case lifecycle and dataset feedback: Passed {passed}/10")


if __name__ == "__main__":
    main()
