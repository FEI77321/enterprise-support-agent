# 模块职责：提供 SQLite 数据库连接与表初始化能力，为会话记忆、待确认操作和工单持久化提供基础设施。

import sqlite3
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATABASE_FILE = DATA_DIR / "enterprise_support_agent.db"


def get_connection(database_path: Path | None = None) -> sqlite3.Connection:  # 函数：打开指定 SQLite 数据库并返回可按列名读取结果的连接。
    target_database = database_path or DATABASE_FILE

    target_database.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(target_database)
    connection.row_factory = sqlite3.Row

    return connection


def initialize_database(database_path: Path | None = None) -> None:  # 函数：创建项目需要的 SQLite 数据表，重复执行也不会破坏已有数据。
    connection = get_connection(database_path)
    try:
        with connection:
            connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_confirmations (
                session_id TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL,
                assignee TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
    finally:
        connection.close()