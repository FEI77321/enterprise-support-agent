"""写操作可靠性：幂等记录、结果复用和“结果未知”阻断盲重试。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.database import get_connection, initialize_database
from app.tool_registry import ToolResult


@dataclass(frozen=True)
class OperationRecord:
    operation_id: str
    idempotency_key: str
    actor_id: str
    tool_name: str
    arguments_hash: str
    status: str
    result: ToolResult | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def arguments_hash(arguments: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def begin_operation(actor_id: str, tool_name: str, arguments: dict[str, object], idempotency_key: str, database_path: Path | None = None) -> tuple[OperationRecord, bool]:
    """返回记录和是否允许首次执行；同 key 的已完成结果可直接复用。"""
    initialize_database(database_path)
    connection = get_connection(database_path)
    current_hash = arguments_hash(arguments)
    try:
        with connection:
            row = connection.execute("SELECT * FROM agent_operations WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if row:
                if row["actor_id"] != actor_id or row["tool_name"] != tool_name or row["arguments_hash"] != current_hash:
                    raise ValueError("idempotency_key_conflict")
                result = ToolResult.model_validate(json.loads(row["result_json"])) if row["result_json"] else None
                return OperationRecord(row["operation_id"], row["idempotency_key"], row["actor_id"], row["tool_name"], row["arguments_hash"], row["status"], result), False
            operation_id = f"write-{uuid4().hex[:16]}"
            now = _now()
            connection.execute(
                "INSERT INTO agent_operations(operation_id, idempotency_key, actor_id, tool_name, arguments_hash, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'executing', ?, ?)",
                (operation_id, idempotency_key, actor_id, tool_name, current_hash, now, now),
            )
            return OperationRecord(operation_id, idempotency_key, actor_id, tool_name, current_hash, "executing", None), True
    finally:
        connection.close()


def finish_operation(operation_id: str, result: ToolResult, database_path: Path | None = None) -> None:
    initialize_database(database_path)
    connection = get_connection(database_path)
    try:
        with connection:
            connection.execute(
                "UPDATE agent_operations SET status = ?, result_json = ?, updated_at = ? WHERE operation_id = ?",
                ("succeeded" if result.success else "failed", json.dumps(result.model_dump(), ensure_ascii=False), _now(), operation_id),
            )
    finally:
        connection.close()


def mark_operation_unknown(operation_id: str, database_path: Path | None = None) -> None:
    """基础设施超时且无法判断副作用是否已提交时，禁止同 key 再次执行。"""
    initialize_database(database_path)
    connection = get_connection(database_path)
    try:
        with connection:
            connection.execute("UPDATE agent_operations SET status = 'unknown', updated_at = ? WHERE operation_id = ?", (_now(), operation_id))
    finally:
        connection.close()
