"""Bad Case 生命周期：把失败 Trace 转成可回归、可度量的 Eval Dataset。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.database import get_connection, initialize_database
from app.trace_store import get_trace


_ALLOWED_TRANSITIONS = {
    "open": {"triaged"},
    "triaged": {"regression_added", "resolved"},
    "regression_added": {"resolved"},
    "resolved": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_case(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _record_event(connection: Any, bad_case_id: str, event_type: str, actor_id: str, detail: dict[str, Any], created_at: str) -> None:
    connection.execute(
        """
        INSERT INTO agent_bad_case_events (bad_case_id, event_type, actor_id, detail_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (bad_case_id, event_type, actor_id, json.dumps(detail, ensure_ascii=False, sort_keys=True), created_at),
    )


def create_bad_case(
    *, request_id: str, category: str, severity: str, expected_behavior: str,
    actual_behavior: str, reporter_id: str, database_path: Path | None = None,
) -> dict[str, Any]:
    """创建与 Trace 强关联的失败案例；不存在 Trace 时拒绝悬空记录。"""
    initialize_database(database_path)
    if get_trace(request_id, database_path) is None:
        raise ValueError("trace_not_found")
    now = _now()
    bad_case_id = f"bc-{uuid4().hex[:12]}"
    connection = get_connection(database_path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO agent_bad_cases (
                    bad_case_id, request_id, category, severity, expected_behavior,
                    actual_behavior, status, reporter_id, regression_case_id,
                    created_at, updated_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, NULL, ?, ?, NULL)
                """,
                (bad_case_id, request_id, category, severity, expected_behavior,
                 actual_behavior, reporter_id, now, now),
            )
            _record_event(connection, bad_case_id, "created", reporter_id, {"status": "open"}, now)
            row = connection.execute("SELECT * FROM agent_bad_cases WHERE bad_case_id = ?", (bad_case_id,)).fetchone()
            return _row_to_case(row) or {}
    finally:
        connection.close()


def get_bad_case(bad_case_id: str, database_path: Path | None = None) -> dict[str, Any] | None:
    initialize_database(database_path)
    connection = get_connection(database_path)
    try:
        row = connection.execute("SELECT * FROM agent_bad_cases WHERE bad_case_id = ?", (bad_case_id,)).fetchone()
        if row is None:
            return None
        case = _row_to_case(row) or {}
        events = connection.execute(
            "SELECT event_type, actor_id, detail_json, created_at FROM agent_bad_case_events WHERE bad_case_id = ? ORDER BY id",
            (bad_case_id,),
        ).fetchall()
        case["events"] = [{**dict(event), "detail": json.loads(event["detail_json"])} for event in events]
        return case
    finally:
        connection.close()


def list_bad_cases(*, status: str | None = None, category: str | None = None, database_path: Path | None = None) -> list[dict[str, Any]]:
    initialize_database(database_path)
    clauses: list[str] = []
    values: list[str] = []
    if status:
        clauses.append("status = ?")
        values.append(status)
    if category:
        clauses.append("category = ?")
        values.append(category)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    connection = get_connection(database_path)
    try:
        rows = connection.execute(
            f"SELECT * FROM agent_bad_cases{where} ORDER BY created_at DESC", values
        ).fetchall()
        return [(_row_to_case(row) or {}) for row in rows]
    finally:
        connection.close()


def transition_bad_case(bad_case_id: str, target_status: str, *, actor_id: str, database_path: Path | None = None) -> dict[str, Any]:
    initialize_database(database_path)
    connection = get_connection(database_path)
    try:
        with connection:
            row = connection.execute("SELECT * FROM agent_bad_cases WHERE bad_case_id = ?", (bad_case_id,)).fetchone()
            if row is None:
                raise ValueError("bad_case_not_found")
            current_status = row["status"]
            if target_status not in _ALLOWED_TRANSITIONS.get(current_status, set()):
                raise ValueError(f"invalid_bad_case_transition:{current_status}->{target_status}")
            now = _now()
            regression_case_id = row["regression_case_id"]
            if target_status == "regression_added" and regression_case_id is None:
                regression_case_id = f"regression-{bad_case_id}"
            resolved_at = now if target_status == "resolved" else row["resolved_at"]
            connection.execute(
                """UPDATE agent_bad_cases
                SET status = ?, regression_case_id = ?, updated_at = ?, resolved_at = ?
                WHERE bad_case_id = ?""",
                (target_status, regression_case_id, now, resolved_at, bad_case_id),
            )
            _record_event(connection, bad_case_id, "status_changed", actor_id, {"from": current_status, "to": target_status}, now)
    finally:
        connection.close()
    case = get_bad_case(bad_case_id, database_path)
    if case is None:
        raise ValueError("bad_case_not_found")
    return case


def export_bad_case_as_eval_case(bad_case_id: str, database_path: Path | None = None) -> dict[str, Any]:
    """仅允许已纳入回归的案例导出，确保 Dataset 不是随意的失败记录集合。"""
    case = get_bad_case(bad_case_id, database_path)
    if case is None:
        raise ValueError("bad_case_not_found")
    if case["status"] not in {"regression_added", "resolved"}:
        raise ValueError("bad_case_not_ready_for_regression")
    trace = get_trace(case["request_id"], database_path)
    if trace is None:
        raise ValueError("trace_not_found")
    return {
        "case_id": case["regression_case_id"],
        "source_bad_case_id": case["bad_case_id"],
        "input": trace["original_message"],
        "expected_behavior": case["expected_behavior"],
        "actual_behavior": case["actual_behavior"],
        "category": case["category"],
        "severity": case["severity"],
        "trace_context": {
            "request_id": trace["request_id"],
            "prompt_version": trace["prompt_version"],
            "engine": trace["engine"],
        },
    }


def export_regression_dataset(database_path: Path | None = None) -> dict[str, Any]:
    cases = [
        export_bad_case_as_eval_case(case["bad_case_id"], database_path)
        for case in list_bad_cases(database_path=database_path)
        if case["status"] in {"regression_added", "resolved"}
    ]
    return {
        "dataset_version": "bad-case-feedback-v1",
        "generated_at": _now(),
        "case_count": len(cases),
        "cases": cases,
    }
