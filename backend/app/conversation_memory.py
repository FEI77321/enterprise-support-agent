# 模块职责：管理用户会话的历史消息，并把消息持久化保存到 SQLite 数据库中，
# 让 Agent 能在服务重启后继续读取同一 session 的上下文。

from datetime import datetime

from pydantic import BaseModel

from app.database import get_connection, initialize_database


class ConversationTurn(BaseModel):  # 类：表示一条对话消息，包含发送角色和消息内容。
    role: str
    content: str


class ConversationMemory(BaseModel):  # 类：表示一个会话的完整记忆，由 session_id 和多条消息组成。
    session_id: str
    turns: list[ConversationTurn]


def _load_turns(
    session_id: str,
    limit: int | None = None,
) -> list[ConversationTurn]:  # 函数：从 SQLite 读取指定会话的消息，可选择只读取最近 limit 条。
    initialize_database()

    if limit is not None and limit <= 0:
        return []

    connection = get_connection()

    try:
        if limit is None:
            rows = connection.execute(
                """
                SELECT role, content
                FROM conversation_turns
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT role, content
                FROM conversation_turns
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

            rows = list(reversed(rows))

        return [
            ConversationTurn(
                role=row["role"],
                content=row["content"],
            )
            for row in rows
        ]
    finally:
        connection.close()


def get_or_create_memory(session_id: str) -> ConversationMemory:  # 函数：读取指定会话的全部记忆；没有历史消息时返回空记忆对象。
    turns = _load_turns(session_id)

    return ConversationMemory(
        session_id=session_id,
        turns=turns,
    )


def add_turn(
    session_id: str,
    role: str,
    content: str,
) -> ConversationMemory:  # 函数：把一条用户或 Agent 消息写入数据库，并返回更新后的会话记忆。
    initialize_database()

    created_at = datetime.now().isoformat(timespec="seconds")
    connection = get_connection()

    try:
        with connection:
            connection.execute(
                """
                INSERT INTO conversation_turns (
                    session_id,
                    role,
                    content,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    created_at,
                ),
            )
    finally:
        connection.close()

    return get_or_create_memory(session_id)


def get_recent_turns(
    session_id: str,
    limit: int = 6,
) -> list[ConversationTurn]:  # 函数：读取指定会话最近的若干条消息，并保持原本的时间顺序。
    return _load_turns(
        session_id=session_id,
        limit=limit,
    )


def clear_memory(session_id: str) -> None:  # 函数：删除指定会话的全部历史消息，用于用户清空上下文或测试清理数据。
    initialize_database()

    connection = get_connection()

    try:
        with connection:
            connection.execute(
                """
                DELETE FROM conversation_turns
                WHERE session_id = ?
                """,
                (session_id,),
            )
    finally:
        connection.close()