"""26 条回答质量集：确定性断言、可插拔 Judge、既有人工抽检标签与 Eval Trace。"""

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


def normalized_manual_scores(case: dict) -> dict:
    scores = case.get("manual_scores", {})
    complete = bool(scores) and all(value is not None for value in scores.values())
    return {
        "status": "existing_manual_sample" if complete else "manual_review_pending",
        "scores": scores if complete else {},
        "notes": case.get("notes", ""),
    }


def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    with TemporaryDirectory() as directory:
        trace_database = Path(directory) / "trace.db"
        eval_database = Path(directory) / "eval.db"
        previous_trace_db = os.environ.get("TRACE_DATABASE_PATH")
        previous_trace_enabled = os.environ.get("TRACE_PERSISTENCE_ENABLED")
        os.environ["TRACE_DATABASE_PATH"] = str(trace_database)
        os.environ["TRACE_PERSISTENCE_ENABLED"] = "true"
        try:
            run_id = create_eval_run(
                suite_name="answer_quality",
                dataset_version="answer-quality-v1",
                judge_provider=os.getenv("LLM_JUDGE_PROVIDER", "stub"),
                database_path=eval_database,
            )
            passed = 0
            manual_samples = 0
            for case in cases:
                request_id = f"aq-{case['id']}"
                response = handle_message(case["query"], request_id=request_id)
                deterministic = deterministic_quality(case, response)
                judge = judge_answer(case, response, deterministic)
                human = normalized_manual_scores(case)
                manual_samples += int(human["status"] == "existing_manual_sample")
                status = "passed" if deterministic["passed"] else "failed"
                record_eval_case(
                    eval_run_id=run_id,
                    case_id=case["id"],
                    prompt_version=str(response.prompt.get("version", "unresolved")),
                    request_id=request_id,
                    status=status,
                    deterministic=deterministic,
                    judge=judge,
                    human=human,
                    trace={
                        "trace_id": response.trace_id,
                        "workflow_steps": response.workflow_steps,
                        "source_count": len(response.sources),
                        "prompt": response.prompt,
                    },
                    database_path=eval_database,
                )
                passed += int(deterministic["passed"])
            summary = {
                "case_count": len(cases),
                "passed": passed,
                "manual_calibration_samples": manual_samples,
                "judge_mode": os.getenv("LLM_JUDGE_PROVIDER", "stub"),
            }
            complete_eval_run(run_id, status="passed" if passed == len(cases) else "failed", summary=summary, database_path=eval_database)
            saved = get_eval_run(run_id, eval_database)
            assert saved is not None and len(saved["cases"]) == len(cases)
            if passed != len(cases):
                raise SystemExit(f"Answer quality eval failed: {passed}/{len(cases)}")
            print(f"Answer quality eval with Judge and Eval Trace: Passed {passed}/{len(cases)}; manual calibration samples={manual_samples}")
        finally:
            if previous_trace_db is None:
                os.environ.pop("TRACE_DATABASE_PATH", None)
            else:
                os.environ["TRACE_DATABASE_PATH"] = previous_trace_db
            if previous_trace_enabled is None:
                os.environ.pop("TRACE_PERSISTENCE_ENABLED", None)
            else:
                os.environ["TRACE_PERSISTENCE_ENABLED"] = previous_trace_enabled


if __name__ == "__main__":
    main()
