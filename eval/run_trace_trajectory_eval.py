"""端到端验证 Answer/Rewrite/Safety Trace 是否完整、可解释、可检索。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.agent import handle_message
from app.trace_store import get_trace


def main() -> None:
    cases = json.loads((PROJECT_ROOT / "eval" / "datasets" / "v1" / "trajectory_cases.json").read_text(encoding="utf-8"))["cases"]
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TRACE_DATABASE_PATH"] = str(Path(temp_dir) / "trace.db")
        os.environ["TRACE_PERSISTENCE_ENABLED"] = "true"
        for case in cases:
            response = handle_message(case["input"], request_id=case["id"])
            assert response.type == case["expected_type"], case
            trace = get_trace(case["id"])
            assert trace is not None, case
            span_names = {span["span_name"] for span in trace["spans"]}
            for required in case.get("required_spans", []):
                assert required in span_names, (case, span_names)
            if "expected_rewrite" in case:
                assert trace["query_rewrite"]["triggered"] is case["expected_rewrite"], case
            if "expected_safety" in case:
                assert trace["safety"]["action"] == case["expected_safety"], case
    print(f"Trace trajectory eval: Passed {len(cases)}/{len(cases)}")


if __name__ == "__main__":
    main()
