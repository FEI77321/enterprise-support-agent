"""长期 Memory：显式写入门控、冲突覆盖、TTL 与 owner 隔离。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.database import get_connection, initialize_database


@dataclass(frozen=True)
class MemoryWriteDecision:
    action: str
    reason: str
    memory_id: str | None = None
    memory_key: str | None = None

    def to_public_dict(self) -> dict[str, object]:
        return asdict(self)


_SENSITIVE = re.compile(r"密码|token|密钥|身份证|银行卡|api[ _-]?key", re.IGNORECASE)
_EXPLICIT = re.compile(r"(?:请)?记住(?:我)?[：:，,\s]*(.+)")


def write_explicit_memory(owner_id: str, message: str, database_path: Path | None = None) -> MemoryWriteDecision:
    """只接受用户明确要求记住的稳定偏好；拒绝凭据和隐私高风险内容。"""
    match = _EXPLICIT.search(message.strip())
    if not match:
        return MemoryWriteDecision("skip", "not_explicit_memory_request")
    value = match.group(1).strip()[:160]
    if not value:
        return MemoryWriteDecision("reject", "empty_memory_value")
    if _SENSITIVE.search(value):
        return MemoryWriteDecision("reject", "sensitive_memory_forbidden")
    if not any(marker in value for marker in ("喜欢", "偏好", "习惯", "称呼", "语言", "格式")):
        return MemoryWriteDecision("reject", "only_stable_preference_allowed")

    memory_key = "explicit_preference"
    now = datetime.now(timezone.utc)
    memory_id = f"mem-{uuid4().hex[:16]}"
    expires_at = (now + timedelta(days=180)).isoformat()
    initialize_database(database_path)
    connection = get_connection(database_path)
    try:
        with connection:
            existing = connection.execute(
                "SELECT memory_id FROM agent_memories WHERE owner_id = ? AND memory_type = 'preference' AND memory_key = ?",
                (owner_id, memory_key),
            ).fetchone()
            if existing:
                memory_id = existing["memory_id"]
                connection.execute(
                    """UPDATE agent_memories SET memory_value = ?, source = 'user_explicit', confidence = 1.0,
                    sensitivity = 'low', status = 'active', expires_at = ?, updated_at = ? WHERE memory_id = ?""",
                    (value, expires_at, now.isoformat(), memory_id),
                )
                return MemoryWriteDecision("updated", "conflict_replaced_by_new_explicit_preference", memory_id, memory_key)
            connection.execute(
                """INSERT INTO agent_memories(memory_id, owner_id, memory_type, memory_key, memory_value, source,
                confidence, sensitivity, status, expires_at, created_at, updated_at)
                VALUES (?, ?, 'preference', ?, ?, 'user_explicit', 1.0, 'low', 'active', ?, ?, ?)""",
                (memory_id, owner_id, memory_key, value, expires_at, now.isoformat(), now.isoformat()),
            )
    finally:
        connection.close()
    return MemoryWriteDecision("written", "explicit_stable_preference", memory_id, memory_key)


def get_active_memories(owner_id: str, limit: int = 4, database_path: Path | None = None) -> list[dict[str, str]]:
    initialize_database(database_path)
    connection = get_connection(database_path)
    try:
        rows = connection.execute(
            """SELECT memory_id, memory_type, memory_key, memory_value, source, expires_at FROM agent_memories
            WHERE owner_id = ? AND status = 'active' AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY updated_at DESC LIMIT ?""",
            (owner_id, datetime.now(timezone.utc).isoformat(), limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def expire_memories(database_path: Path | None = None) -> int:
    initialize_database(database_path)
    connection = get_connection(database_path)
    try:
        with connection:
            cursor = connection.execute(
                "UPDATE agent_memories SET status = 'expired', updated_at = ? WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at <= ?",
                (datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
            )
            return cursor.rowcount
    finally:
        connection.close()
