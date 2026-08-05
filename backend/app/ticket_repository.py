# 模块职责：集中管理 tickets 数据表的读写操作，
# 将 SQLite 行数据与项目中的 Ticket 领域模型相互转换。

import sqlite3
from pathlib import Path

from app.database import get_connection, initialize_database
from app.models import Ticket


def _row_to_ticket(row: sqlite3.Row) -> Ticket:  # 函数：将 SQLite 查询结果的一行数据转换为 Ticket 对象。
    return Ticket(
        ticket_id=row["ticket_id"],
        title=row["title"],
        description=row["description"],
        category=row["category"],
        priority=row["priority"],
        status=row["status"],
        assignee=row["assignee"],
        created_at=row["created_at"],
    )


def insert_ticket(
    ticket: Ticket,
    database_path: Path | None = None,
) -> Ticket:  # 函数：将一张完整工单插入 tickets 表，并返回保存后的工单对象。
    initialize_database(database_path)
    connection = get_connection(database_path)

    try:
        with connection:
            connection.execute(
                """
                INSERT INTO tickets (
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
    finally:
        connection.close()

    return ticket


def get_ticket_by_id(
    ticket_id: str,
    database_path: Path | None = None,
) -> Ticket | None:  # 函数：按工单编号查询 tickets 表；未找到时返回 None。
    initialize_database(database_path)
    connection = get_connection(database_path)

    try:
        row = connection.execute(
            """
            SELECT
                ticket_id,
                title,
                description,
                category,
                priority,
                status,
                assignee,
                created_at
            FROM tickets
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    return _row_to_ticket(row)


def list_ticket_records(
    status: str | None = None,
    priority: str | None = None,
    database_path: Path | None = None,
) -> list[Ticket]:  # 函数：按可选状态和优先级筛选工单，并按创建时间从新到旧返回。
    initialize_database(database_path)

    query = """
        SELECT
            ticket_id,
            title,
            description,
            category,
            priority,
            status,
            assignee,
            created_at
        FROM tickets
    """
    conditions = []
    parameters = []

    if status is not None:
        conditions.append("status = ?")
        parameters.append(status)

    if priority is not None:
        conditions.append("priority = ?")
        parameters.append(priority)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC, ticket_id DESC"

    connection = get_connection(database_path)

    try:
        rows = connection.execute(
            query,
            parameters,
        ).fetchall()
    finally:
        connection.close()

    return [
        _row_to_ticket(row)
        for row in rows
    ]


def update_ticket_status_record(
    ticket_id: str,
    status: str,
    database_path: Path | None = None,
) -> Ticket | None:  # 函数：更新指定工单的状态；工单不存在时返回 None。
    initialize_database(database_path)
    connection = get_connection(database_path)

    try:
        with connection:
            cursor = connection.execute(
                """
                UPDATE tickets
                SET status = ?
                WHERE ticket_id = ?
                """,
                (
                    status,
                    ticket_id,
                ),
            )

            if cursor.rowcount == 0:
                return None

            row = connection.execute(
                """
                SELECT
                    ticket_id,
                    title,
                    description,
                    category,
                    priority,
                    status,
                    assignee,
                    created_at
                FROM tickets
                WHERE ticket_id = ?
                """,
                (ticket_id,),
            ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    return _row_to_ticket(row)


def delete_ticket_record(
    ticket_id: str,
    database_path: Path | None = None,
) -> bool:  # 函数：删除指定工单；成功删除返回 True，不存在时返回 False。
    initialize_database(database_path)
    connection = get_connection(database_path)

    try:
        with connection:
            cursor = connection.execute(
                """
                DELETE FROM tickets
                WHERE ticket_id = ?
                """,
                (ticket_id,),
            )
    finally:
        connection.close()

    return cursor.rowcount > 0

def get_next_ticket_sequence(
    database_path: Path | None = None,
) -> int:  # 函数：读取当前工单编号的最大数字后缀，并返回下一个可用流水号。
    initialize_database(database_path)
    connection = get_connection(database_path)

    try:
        row = connection.execute(
            """
            SELECT COALESCE(
                MAX(CAST(SUBSTR(ticket_id, 17) AS INTEGER)),
                0
            ) AS max_sequence
            FROM tickets
            """,
        ).fetchone()
    finally:
        connection.close()

    return int(row["max_sequence"]) + 1