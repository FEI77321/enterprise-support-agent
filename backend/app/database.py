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
    connection.execute("PRAGMA foreign_keys = ON")

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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                session_id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                covered_until_turn_id INTEGER NOT NULL,
                source_turn_count INTEGER NOT NULL,
                estimated_tokens INTEGER NOT NULL,
                strategy TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_trace_runs (
                request_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                engine TEXT NOT NULL,
                response_type TEXT NOT NULL,
                original_message TEXT NOT NULL,
                effective_query TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                safety_json TEXT NOT NULL,
                rewrite_json TEXT NOT NULL,
                workflow_json TEXT NOT NULL,
                source_count INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_trace_spans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                span_name TEXT NOT NULL,
                span_type TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(request_id) REFERENCES agent_trace_runs(request_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_approvals (
                operation_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_trace_spans_request ON agent_trace_spans(request_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tool_approvals_session ON tool_approvals(session_id)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_ownership (
                ticket_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES tickets(ticket_id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS approval_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id TEXT NOT NULL,
                requester_id TEXT NOT NULL,
                approver_id TEXT,
                decision TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_operations (
                operation_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                actor_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_memories (
                memory_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                memory_key TEXT NOT NULL,
                memory_value TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL NOT NULL,
                sensitivity TEXT NOT NULL,
                status TEXT NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(owner_id, memory_type, memory_key)
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_ticket_ownership_owner ON ticket_ownership(owner_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_operations_key ON agent_operations(idempotency_key)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_memories_owner ON agent_memories(owner_id, status)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_bad_cases (
                bad_case_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                expected_behavior TEXT NOT NULL,
                actual_behavior TEXT NOT NULL,
                status TEXT NOT NULL,
                reporter_id TEXT NOT NULL,
                regression_case_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY(request_id) REFERENCES agent_trace_runs(request_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_bad_case_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bad_case_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(bad_case_id) REFERENCES agent_bad_cases(bad_case_id) ON DELETE CASCADE
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_bad_cases_status ON agent_bad_cases(status, category)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_bad_cases_request ON agent_bad_cases(request_id)")
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(agent_bad_cases)").fetchall()}
        for name, definition in (
            ("root_cause", "TEXT"),
            ("fix_version", "TEXT"),
            ("fixture_kind", "TEXT NOT NULL DEFAULT 'observed'"),
        ):
            if name not in columns:
                connection.execute(f"ALTER TABLE agent_bad_cases ADD COLUMN {name} {definition}")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_eval_runs (
                eval_run_id TEXT PRIMARY KEY,
                suite_name TEXT NOT NULL,
                dataset_version TEXT NOT NULL,
                baseline_prompt_version TEXT,
                candidate_prompt_version TEXT,
                judge_provider TEXT NOT NULL,
                status TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_eval_case_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                eval_run_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                request_id TEXT,
                status TEXT NOT NULL,
                deterministic_json TEXT NOT NULL,
                judge_json TEXT NOT NULL,
                human_json TEXT NOT NULL,
                trace_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(eval_run_id, case_id, prompt_version),
                FOREIGN KEY(eval_run_id) REFERENCES agent_eval_runs(eval_run_id) ON DELETE CASCADE
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_eval_cases_run ON agent_eval_case_results(eval_run_id, case_id)")

        from app.knowledge_repository import (
            initialize_knowledge_tables,
        )

        initialize_knowledge_tables(connection)
    finally:
        connection.close()
