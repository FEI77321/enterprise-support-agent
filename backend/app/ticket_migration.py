# 模块职责：将旧版 tickets.json 中的工单数据迁移到 SQLite 的 tickets 表，
# 并保证重复执行不会创建相同 ticket_id 的重复工单。

import json
from pathlib import Path

from app.database import get_connection, initialize_database
from app.models import Ticket


LEGACY_TICKETS_FILE = Path(__file__).resolve().parent.parent / "data" / "tickets.json"


def migrate_legacy_tickets(
    source_file: Path | None = None,
    database_path: Path | None = None,
) -> int:  # 函数：读取旧 JSON 工单并迁移到 SQLite，返回本次实际新增的工单数量。
    target_source_file = source_file or LEGACY_TICKETS_FILE

    if not target_source_file.exists():
        return 0

    raw_text = target_source_file.read_text(encoding="utf-8")
    raw_tickets = json.loads(raw_text)

    if not isinstance(raw_tickets, list):
        raise ValueError("旧工单 JSON 的顶层数据必须是列表")

    tickets = [
        Ticket(**ticket_data)
        for ticket_data in raw_tickets
    ]

    initialize_database(database_path)
    connection = get_connection(database_path)
    migrated_count = 0

    try:
        with connection:
            for ticket in tickets:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO tickets (
                        ticket_id,
                        title,
                        description,
                        category,
                        priority,
                        status,
                        assignee,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticket.ticket_id,
                        ticket.title,
                        ticket.description,
                        ticket.category,
                        ticket.priority.value,
                        ticket.status.value,
                        ticket.assignee,
                        ticket.created_at,
                    ),
                )

                migrated_count += cursor.rowcount
    finally:
        connection.close()

    return migrated_count