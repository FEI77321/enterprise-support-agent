"""在同一 Answer Quality Dataset 上比较 baseline/candidate Prompt，并落盘 Eval Trace。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from eval_path import setup_backend_path

setup_backend_path()

from app.agent import handle_message
from app.answer_quality_judge import deterministic_quality, judge_answer
from app.eval_trace_store import complete_eval_run, create_eval_run, get_eval_run, record_eval_case


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "eval" / "answer_quality_cases.json"
BASELINE = "support-agent-v2.0"
CANDIDATE = "support-agent-v2.1"


def run_version(version: str, cases: list[dict], eval_run_id: str, database: Path) -> int:
    previous_force = os.environ.get("PROMPT_FORCE_VERSION")
    os.environ["PROMPT_FORCE_VERSION"] = version
    passed = 0
    try:
        for case in cases:
            request_id = f"prompt-{version[-3:]}-{case['id']}"
            response = handle_message(case["query"], request_id=request_id)
            deterministic = deterministic_quality(case, response)
            judge = judge_answer(case, response, deterministic)
            status = "passed" if deterministic["passed"] else "failed"
            record_eval_case(
                eval_run_id=eval_run_id,
                case_id=case["id"],
                prompt_version=version,
                request_id=request_id,
                status=status,
                deterministic=deterministic,
                judge=judge,
                human={"status": "not_scored_in_prompt_regression"},
                trace={"prompt": response.prompt, "trace_id": response.trace_id},
                database_path=database,
            )
            passed += int(deterministic["passed"])
    finally:
        if previous_force is None:
            os.environ.pop("PROMPT_FORCE_VERSION", None)
        else:
            os.environ["PROMPT_FORCE_VERSION"] = previous_force
    return passed


def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    with TemporaryDirectory() as directory:
        database = Path(directory) / "prompt-regression.db"
        run_id = create_eval_run(
            suite_name="prompt_regression",
            dataset_version="answer-quality-v1",
            judge_provider=os.getenv("LLM_JUDGE_PROVIDER", "stub"),
            baseline_prompt_version=BASELINE,
            candidate_prompt_version=CANDIDATE,
            database_path=database,
        )
        baseline = run_version(BASELINE, cases, run_id, database)
        candidate = run_version(CANDIDATE, cases, run_id, database)
        release_allowed = candidate >= baseline and candidate == len(cases)
        summary = {
            "case_count": len(cases), "baseline_passed": baseline,
            "candidate_passed": candidate, "release_allowed": release_allowed,
            "decision": "candidate_allowed" if release_allowed else "candidate_blocked",
        }
        complete_eval_run(run_id, status="passed" if release_allowed else "failed", summary=summary, database_path=database)
        stored = get_eval_run(run_id, database)
        assert stored is not None and len(stored["cases"]) == len(cases) * 2
        if not release_allowed:
            raise SystemExit(f"Prompt regression failed: baseline={baseline}, candidate={candidate}, total={len(cases)}")
        print(f"Prompt regression gate: Passed baseline {baseline}/{len(cases)}, candidate {candidate}/{len(cases)}, release_allowed=true")


if __name__ == "__main__":
    main()
