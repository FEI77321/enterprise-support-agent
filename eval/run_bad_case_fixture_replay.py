"""受控 Bad Case Fixture 回流：每条均有 Trace、根因、修复版本与回归 Case，不冒充线上事故。"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from eval_path import setup_backend_path

setup_backend_path()

from app.bad_case_store import create_bad_case, export_bad_case_as_eval_case, export_regression_dataset, get_bad_case, transition_bad_case
from app.models import ChatResponse
from app.trace_store import get_trace, persist_trace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "eval" / "fixtures" / "reproducible_bad_cases_v1.json"


def main() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["fixture_kind"] == "controlled_fixture"
    with TemporaryDirectory() as directory:
        database = Path(directory) / "bad-case-fixtures.db"
        exported_ids: list[str] = []
        for item in fixture["cases"]:
            request_id = f"fixture-trace-{item['id']}"
            response = ChatResponse(
                request_id=request_id,
                type="clarify",
                answer=item["actual"],
                workflow_steps=["fixture", item["span"]],
                safety={"action": "allow", "fixture": True},
                query_rewrite={"triggered": False},
                prompt={"version": item["fix_version"], "fixture": True},
                timing={"total_ms": 1.0, "agent_core_ms": 0.5},
            )
            persist_trace(response, original_message=item["message"], effective_query=item["message"], engine="controlled_fixture", database_path=database)
            trace = get_trace(request_id, database)
            assert trace is not None and trace["request_id"] == request_id
            bad_case = create_bad_case(
                request_id=request_id,
                category=item["category"], severity="high",
                expected_behavior=item["expected"], actual_behavior=item["actual"],
                root_cause=item["root_cause"], fix_version=item["fix_version"],
                fixture_kind="controlled_fixture", reporter_id="qa-fixture", database_path=database,
            )
            triaged = transition_bad_case(bad_case["bad_case_id"], "triaged", actor_id="qa-fixture", database_path=database)
            added = transition_bad_case(triaged["bad_case_id"], "regression_added", actor_id="qa-fixture", database_path=database)
            resolved = transition_bad_case(added["bad_case_id"], "resolved", actor_id="qa-fixture", database_path=database)
            exported = export_bad_case_as_eval_case(resolved["bad_case_id"], database)
            saved = get_bad_case(resolved["bad_case_id"], database)
            assert exported["fixture_kind"] == "controlled_fixture"
            assert exported["root_cause"] == item["root_cause"]
            assert exported["fix_version"] == item["fix_version"]
            assert saved is not None and saved["status"] == "resolved"
            exported_ids.append(exported["case_id"])
        dataset = export_regression_dataset(database)
        assert dataset["case_count"] == len(fixture["cases"]) == len(set(exported_ids))
    print(f"Controlled Bad Case fixture replay: Passed {len(fixture['cases'])}/{len(fixture['cases'])}")


if __name__ == "__main__":
    main()
