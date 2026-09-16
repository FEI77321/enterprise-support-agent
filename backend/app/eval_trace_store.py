"""离线评测的可回放 Trace：把版本、Case、Judge、人工校准与线上 Trace 关联。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.database import get_connection, initialize_database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def create_eval_run(
    *,
    suite_name: str,
    dataset_version: str,
    judge_provider: str,
    baseline_prompt_version: str | None = None,
    candidate_prompt_version: str | None = None,
    database_path: Path | None = None,
) -> str:
    initialize_database(database_path)
    run_id = f"eval-{uuid4().hex[:12]}"
    connection = get_connection(database_path)
    try:
        with connection:
            connection.execute(
                """INSERT INTO agent_eval_runs (
                eval_run_id, suite_name, dataset_version, baseline_prompt_version,
                candidate_prompt_version, judge_provider, status, summary_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'running', '{}', ?)""",
                (run_id, suite_name, dataset_version, baseline_prompt_version,
                 candidate_prompt_version, judge_provider, _now()),
            )
    finally:
        connection.close()
    return run_id


def record_eval_case(
    *,
    eval_run_id: str,
    case_id: str,
    prompt_version: str,
    status: str,
    deterministic: dict,
    judge: dict,
    human: dict,
    trace: dict,
    request_id: str | None = None,
    database_path: Path | None = None,
) -> None:
    initialize_database(database_path)
    connection = get_connection(database_path)
    try:
        with connection:
            connection.execute(
                """INSERT OR REPLACE INTO agent_eval_case_results (
                eval_run_id, case_id, prompt_version, request_id, status,
                deterministic_json, judge_json, human_json, trace_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (eval_run_id, case_id, prompt_version, request_id, status,
                 _dump(deterministic), _dump(judge), _dump(human), _dump(trace), _now()),
            )
    finally:
        connection.close()


def complete_eval_run(eval_run_id: str, *, status: str, summary: dict, database_path: Path | None = None) -> None:
    initialize_database(database_path)
    connection = get_connection(database_path)
    try:
        with connection:
            connection.execute(
                "UPDATE agent_eval_runs SET status = ?, summary_json = ? WHERE eval_run_id = ?",
                (status, _dump(summary), eval_run_id),
            )
    finally:
        connection.close()


def get_eval_run(eval_run_id: str, database_path: Path | None = None) -> dict | None:
    initialize_database(database_path)
    connection = get_connection(database_path)
    try:
        run = connection.execute("SELECT * FROM agent_eval_runs WHERE eval_run_id = ?", (eval_run_id,)).fetchone()
        if run is None:
            return None
        cases = connection.execute(
            "SELECT * FROM agent_eval_case_results WHERE eval_run_id = ? ORDER BY id",
            (eval_run_id,),
        ).fetchall()
        return {
            **dict(run),
            "summary": json.loads(run["summary_json"]),
            "cases": [
                {
                    **dict(case),
                    "deterministic": json.loads(case["deterministic_json"]),
                    "judge": json.loads(case["judge_json"]),
                    "human": json.loads(case["human_json"]),
                    "trace": json.loads(case["trace_json"]),
                }
                for case in cases
            ],
        }
    finally:
        connection.close()
