"""Agent Trace 的持久化、读取与聚合指标。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_trace_database_path, is_trace_persistence_enabled
from app.database import get_connection, initialize_database
from app.models import ChatResponse


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def persist_trace(
    response: ChatResponse,
    *,
    original_message: str,
    effective_query: str,
    engine: str,
    database_path: Path | None = None,
) -> None:
    """把一次回答写成可回放的 root run + spans；同 request_id 时幂等覆盖。"""
    if not is_trace_persistence_enabled():
        return
    target = database_path or get_trace_database_path()
    initialize_database(target)
    now = _now()
    source_payload = [source.model_dump() for source in response.sources]
    metadata = {
        "ticket_id": response.ticket.ticket_id if response.ticket else None,
        "harness_trace_count": len(response.harness_trace),
        "source_files": [source.file for source in response.sources],
        "memory": response.memory,
        "context": response.context,
        "prompt": response.prompt,
        "timing": response.timing,
    }
    spans: list[tuple[str, str, str, dict[str, Any]]] = [
        ("input_guard", "safety", response.safety.get("action", "allow"), response.safety),
        ("query_rewrite", "rewrite", "rewritten" if response.query_rewrite.get("triggered") else "passthrough", response.query_rewrite),
        ("workflow", "trajectory", "completed", {"steps": response.workflow_steps}),
        ("retrieval", "retrieval", "completed", {"sources": source_payload}),
        ("memory", "memory", str(response.memory.get("write", {}).get("action", "skip")), response.memory),
        (
            "prompt_resolution",
            "prompt",
            str(response.prompt.get("channel", "active")),
            response.prompt,
        ),
        (
            "context_budget",
            "context",
            "compressed" if response.context.get("compression_triggered") else "within_budget",
            response.context,
        ),
    ]
    spans.extend(
        (
            f"timing:{name}",
            "timing",
            "completed",
            {"metric": name, "elapsed_ms": value},
        )
        for name, value in response.timing.items()
    )
    spans.extend(
        (f"tool:{item.get('tool_name', 'unknown')}", "tool", str(item.get("status", "unknown")), item)
        for item in response.harness_trace
    )
    spans.append(("response", "output", response.type, {"answer": response.answer, "type": response.type}))

    connection = get_connection(target)
    try:
        with connection:
            connection.execute("DELETE FROM agent_trace_spans WHERE request_id = ?", (response.request_id,))
            connection.execute(
                """
                INSERT INTO agent_trace_runs (
                    request_id, created_at, engine, response_type, original_message,
                    effective_query, prompt_version, safety_json, rewrite_json,
                    workflow_json, source_count, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    created_at = excluded.created_at,
                    engine = excluded.engine,
                    response_type = excluded.response_type,
                    original_message = excluded.original_message,
                    effective_query = excluded.effective_query,
                    prompt_version = excluded.prompt_version,
                    safety_json = excluded.safety_json,
                    rewrite_json = excluded.rewrite_json,
                    workflow_json = excluded.workflow_json,
                    source_count = excluded.source_count,
                    metadata_json = excluded.metadata_json
                """,
                (
                    response.request_id, now, engine, response.type, original_message,
                    effective_query, str(response.prompt.get("version", "unresolved")), _dump(response.safety),
                    _dump(response.query_rewrite), _dump(response.workflow_steps),
                    len(response.sources), _dump(metadata),
                ),
            )
            connection.executemany(
                """
                INSERT INTO agent_trace_spans (
                    request_id, span_name, span_type, status, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(response.request_id, name, span_type, status, _dump(payload), now) for name, span_type, status, payload in spans],
            )
    finally:
        connection.close()


def get_trace(request_id: str, database_path: Path | None = None) -> dict[str, Any] | None:
    target = database_path or get_trace_database_path()
    initialize_database(target)
    connection = get_connection(target)
    try:
        run = connection.execute("SELECT * FROM agent_trace_runs WHERE request_id = ?", (request_id,)).fetchone()
        if run is None:
            return None
        spans = connection.execute(
            "SELECT span_name, span_type, status, payload_json, created_at FROM agent_trace_spans WHERE request_id = ? ORDER BY id",
            (request_id,),
        ).fetchall()
        return {
            "request_id": run["request_id"], "created_at": run["created_at"],
            "engine": run["engine"], "response_type": run["response_type"],
            "original_message": run["original_message"], "effective_query": run["effective_query"],
            "prompt_version": run["prompt_version"], "safety": json.loads(run["safety_json"]),
            "query_rewrite": json.loads(run["rewrite_json"]), "workflow_steps": json.loads(run["workflow_json"]),
            "source_count": run["source_count"], "metadata": json.loads(run["metadata_json"]),
            "spans": [{**dict(span), "payload": json.loads(span["payload_json"])} for span in spans],
        }
    finally:
        connection.close()


def get_trace_summary(database_path: Path | None = None) -> dict[str, int]:
    target = database_path or get_trace_database_path()
    initialize_database(target)
    connection = get_connection(target)
    try:
        rows = connection.execute("SELECT response_type, COUNT(*) AS count FROM agent_trace_runs GROUP BY response_type").fetchall()
        return {row["response_type"]: row["count"] for row in rows}
    finally:
        connection.close()


def get_trace_timeline(request_id: str, database_path: Path | None = None) -> list[dict[str, Any]] | None:
    trace = get_trace(request_id, database_path)
    if trace is None:
        return None
    return [
        {
            "name": span["span_name"], "type": span["span_type"], "status": span["status"],
            "created_at": span["created_at"],
            "summary": _timeline_summary(span["payload"]),
        }
        for span in trace["spans"]
    ]


def _timeline_summary(payload: dict[str, Any]) -> str:
    if "reason" in payload:
        return str(payload["reason"])
    if "steps" in payload:
        return " → ".join(payload["steps"])
    if "sources" in payload:
        return f"sources={len(payload['sources'])}"
    if "compression_triggered" in payload:
        return (
            f"compressed={payload.get('compression_triggered')} "
            f"recent={payload.get('recent_turn_count', 0)} "
            f"reduction={payload.get('estimated_reduction_ratio', 0)}"
        )
    if "tool_name" in payload:
        return f"{payload['tool_name']} ({payload.get('error_type') or 'ok'})"
    if "content_hash" in payload:
        return f"{payload.get('version', 'unknown')} ({payload.get('channel', 'active')})"
    if "elapsed_ms" in payload:
        return f"{payload.get('metric', 'phase')}={payload['elapsed_ms']}ms"
    if "answer" in payload:
        return str(payload.get("type", "response"))
    return "recorded"


def get_agentops_metrics(database_path: Path | None = None) -> dict[str, Any]:
    """面向运营面板的运行质量指标；不使用 LLM judge，全部来自结构化 Trace。"""
    target = database_path or get_trace_database_path()
    initialize_database(target)
    connection = get_connection(target)
    try:
        runs = connection.execute("SELECT response_type, safety_json, rewrite_json, metadata_json FROM agent_trace_runs").fetchall()
        tool_spans = connection.execute("SELECT status, payload_json FROM agent_trace_spans WHERE span_type = 'tool'").fetchall()
        timing_spans = connection.execute("SELECT payload_json FROM agent_trace_spans WHERE span_type = 'timing'").fetchall()
        bad_case_rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM agent_bad_cases GROUP BY status"
        ).fetchall()
        total = len(runs)
        safety_blocks = sum(json.loads(row["safety_json"]).get("action") == "block" for row in runs)
        rewrite_triggered = sum(json.loads(row["rewrite_json"]).get("triggered") is True for row in runs)
        response_types: dict[str, int] = {}
        context_decisions = [json.loads(row["metadata_json"]).get("context", {}) for row in runs]
        for row in runs:
            response_types[row["response_type"]] = response_types.get(row["response_type"], 0) + 1
        tool_failures = sum(row["status"] not in {"completed"} for row in tool_spans)
        bad_cases = {row["status"]: row["count"] for row in bad_case_rows}
        latencies = [json.loads(row["payload_json"]).get("elapsed_ms") for row in tool_spans]
        latency_values = sorted(value for value in latencies if isinstance(value, (float, int)))
        timing_by_metric: dict[str, list[float]] = {}
        for row in timing_spans:
            payload = json.loads(row["payload_json"])
            metric, value = payload.get("metric"), payload.get("elapsed_ms")
            if isinstance(metric, str) and isinstance(value, (float, int)):
                timing_by_metric.setdefault(metric, []).append(float(value))
        percentile = lambda ratio: latency_values[max(0, int(len(latency_values) * ratio + 0.9999) - 1)] if latency_values else None
        timing_percentiles = {
            metric: {
                "p50": sorted(values)[max(0, int(len(values) * 0.5 + 0.9999) - 1)],
                "p95": sorted(values)[max(0, int(len(values) * 0.95 + 0.9999) - 1)],
            }
            for metric, values in timing_by_metric.items()
        }
        return {
            "trace_runs": total,
            "response_types": response_types,
            "prompt_injection_block_rate": round(safety_blocks / total, 4) if total else 0.0,
            "query_rewrite_trigger_rate": round(rewrite_triggered / total, 4) if total else 0.0,
            "tool_calls": len(tool_spans),
            "tool_failure_rate": round(tool_failures / len(tool_spans), 4) if tool_spans else 0.0,
            "tool_elapsed_ms": {"p50": percentile(0.5), "p95": percentile(0.95)},
            "request_phase_elapsed_ms": timing_percentiles,
            "context_compression_trigger_rate": round(
                sum(item.get("compression_triggered") is True for item in context_decisions) / total,
                4,
            ) if total else 0.0,
            "context_estimated_reduction_ratio": round(
                sum(float(item.get("estimated_reduction_ratio", 0.0)) for item in context_decisions) / total,
                4,
            ) if total else 0.0,
            "bad_cases": bad_cases,
            "open_bad_case_count": sum(
                count for status, count in bad_cases.items() if status != "resolved"
            ),
        }
    finally:
        connection.close()
