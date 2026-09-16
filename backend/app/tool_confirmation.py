# 模块职责：保存、读取和清除用户待确认的高风险工具操作，
# 并识别用户是否确认或取消执行该操作。

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.database import get_connection, initialize_database


class PendingToolConfirmation(BaseModel):  # 类：表示某个会话中等待用户确认的一次高风险工具调用。
    operation_id: str
    session_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str
    expires_at: str


def save_pending_confirmation(
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    reason: str,
    expires_seconds: int = 300,
) -> PendingToolConfirmation:  # 函数：把待确认操作写入 SQLite；同一会话已有操作时更新它。
    initialize_database()

    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(seconds=expires_seconds)
    operation_id = f"op-{uuid4().hex[:12]}"
    arguments_json = json.dumps(
        arguments,
        ensure_ascii=False,
    )
    connection = get_connection()

    try:
        with connection:
            connection.execute("DELETE FROM tool_approvals WHERE session_id = ? AND consumed_at IS NULL", (session_id,))
            connection.execute(
                """
                INSERT INTO tool_approvals (
                    operation_id, session_id, tool_name, arguments_json, reason, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (operation_id, session_id, tool_name, arguments_json, reason, created_at.isoformat(), expires_at.isoformat()),
            )
    finally:
        connection.close()

    return PendingToolConfirmation(
        operation_id=operation_id,
        session_id=session_id,
        tool_name=tool_name,
        arguments=arguments,
        reason=reason,
        expires_at=expires_at.isoformat(),
    )


def get_pending_confirmation(
    session_id: str,
    operation_id: str | None = None,
) -> PendingToolConfirmation | None:  # 函数：读取指定会话的待确认操作；不存在时返回 None。
    initialize_database()
    connection = get_connection()

    try:
        sql = """
            SELECT operation_id, tool_name, arguments_json, reason, expires_at
            FROM tool_approvals
            WHERE session_id = ? AND consumed_at IS NULL AND expires_at > ?
        """
        params: list[str] = [session_id, datetime.now(timezone.utc).isoformat()]
        if operation_id:
            sql += " AND operation_id = ?"
            params.append(operation_id)
        sql += " ORDER BY created_at DESC LIMIT 1"
        row = connection.execute(sql, params).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    arguments = json.loads(row["arguments_json"])

    if not isinstance(arguments, dict):
        raise ValueError("待确认操作的 arguments_json 必须解析为字典")

    return PendingToolConfirmation(
        operation_id=row["operation_id"],
        session_id=session_id,
        tool_name=row["tool_name"],
        arguments=arguments,
        reason=row["reason"],
        expires_at=row["expires_at"],
    )


def clear_pending_confirmation(session_id: str) -> None:  # 函数：删除指定会话的待确认操作，防止同一次确认被重复执行。
    initialize_database()
    connection = get_connection()

    try:
        with connection:
            connection.execute("DELETE FROM tool_approvals WHERE session_id = ? AND consumed_at IS NULL", (session_id,))
    finally:
        connection.close()


def consume_pending_confirmation(
    session_id: str,
    operation_id: str | None = None,
) -> PendingToolConfirmation | None:
    """原子消费审批，阻断过期审批、跨会话确认和确认重放。"""
    pending = get_pending_confirmation(session_id, operation_id)
    if pending is None:
        return None
    connection = get_connection()
    try:
        with connection:
            cursor = connection.execute(
                """
                UPDATE tool_approvals SET consumed_at = ?
                WHERE operation_id = ? AND session_id = ? AND consumed_at IS NULL AND expires_at > ?
                """,
                (datetime.now(timezone.utc).isoformat(), pending.operation_id, session_id, datetime.now(timezone.utc).isoformat()),
            )
            return pending if cursor.rowcount == 1 else None
    finally:
        connection.close()


def get_confirmation_decision(message: str) -> str | None:  # 函数：识别用户消息是确认、取消，还是与待确认操作无关。
    normalized_message = message.strip().lower()

    confirm_messages = {
        "确认",
        "确认删除",
        "确认执行",
        "是",
        "好的",
        "yes",
    }
    cancel_messages = {
        "取消",
        "取消删除",
        "不删除",
        "否",
        "不要",
        "no",
    }

    if normalized_message in confirm_messages:
        return "confirm"

    if normalized_message in cancel_messages:
        return "cancel"

    return None
