# 模块职责：保存、读取和清除用户待确认的高风险工具操作，
# 并识别用户是否确认或取消执行该操作。

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.database import get_connection, initialize_database


class PendingToolConfirmation(BaseModel):  # 类：表示某个会话中等待用户确认的一次高风险工具调用。
    session_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str


def save_pending_confirmation(
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    reason: str,
) -> PendingToolConfirmation:  # 函数：把待确认操作写入 SQLite；同一会话已有操作时更新它。
    initialize_database()

    created_at = datetime.now().isoformat(timespec="seconds")
    arguments_json = json.dumps(
        arguments,
        ensure_ascii=False,
    )
    connection = get_connection()

    try:
        with connection:
            connection.execute(
                """
                INSERT INTO pending_confirmations (
                    session_id,
                    tool_name,
                    arguments_json,
                    reason,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    tool_name = excluded.tool_name,
                    arguments_json = excluded.arguments_json,
                    reason = excluded.reason,
                    created_at = excluded.created_at
                """,
                (
                    session_id,
                    tool_name,
                    arguments_json,
                    reason,
                    created_at,
                ),
            )
    finally:
        connection.close()

    return PendingToolConfirmation(
        session_id=session_id,
        tool_name=tool_name,
        arguments=arguments,
        reason=reason,
    )


def get_pending_confirmation(
    session_id: str,
) -> PendingToolConfirmation | None:  # 函数：读取指定会话的待确认操作；不存在时返回 None。
    initialize_database()
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT tool_name, arguments_json, reason
            FROM pending_confirmations
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    arguments = json.loads(row["arguments_json"])

    if not isinstance(arguments, dict):
        raise ValueError("待确认操作的 arguments_json 必须解析为字典")

    return PendingToolConfirmation(
        session_id=session_id,
        tool_name=row["tool_name"],
        arguments=arguments,
        reason=row["reason"],
    )


def clear_pending_confirmation(session_id: str) -> None:  # 函数：删除指定会话的待确认操作，防止同一次确认被重复执行。
    initialize_database()
    connection = get_connection()

    try:
        with connection:
            connection.execute(
                """
                DELETE FROM pending_confirmations
                WHERE session_id = ?
                """,
                (session_id,),
            )
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