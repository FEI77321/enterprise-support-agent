# 模块职责：处理工单领域业务规则，例如生成工单标题、判断优先级和创建编号，
# 并通过 ticket_repository 将工单持久化到 SQLite 数据库。

from datetime import datetime

from app.models import Ticket, TicketPriority, TicketStatus
from app.ticket_repository import (
    delete_ticket_record,
    get_next_ticket_sequence,
    get_ticket_by_id,
    insert_ticket,
    list_ticket_records,
    update_ticket_status_record,
)


def create_ticket(message: str) -> Ticket:  # 函数：根据用户问题生成完整工单，并保存到 SQLite。
    now = datetime.now()
    ticket_sequence = get_next_ticket_sequence()
    ticket_id = f"TICKET-{now:%Y%m%d}-{ticket_sequence:04d}"

    priority = (
        TicketPriority.HIGH
        if any(word in message for word in ["无法", "开不了", "蓝屏", "故障"])
        else TicketPriority.MEDIUM
    )

    ticket = Ticket(
        ticket_id=ticket_id,
        title=_build_ticket_title(message),
        description=message,
        category="IT_SUPPORT",
        priority=priority,
        status=TicketStatus.OPEN,
        assignee="IT Support Team",
        created_at=now.isoformat(timespec="seconds"),
    )

    return insert_ticket(ticket)


def query_ticket_status(ticket_id: str) -> Ticket | None:  # 函数：按工单编号查询 SQLite 中的工单详情。
    return get_ticket_by_id(ticket_id)


def _build_ticket_title(message: str) -> str:  # 函数：根据问题关键词生成便于支持人员处理的工单标题。
    if "蓝屏" in message:
        return "电脑蓝屏无法正常使用"

    if "VPN" in message or "vpn" in message:
        return "VPN 连接异常"

    if "账号" in message or "登录" in message:
        return "账号登录异常"

    return "用户支持请求"


def list_tickets(
    status: TicketStatus | str | None = None,
    priority: TicketPriority | str | None = None,
) -> list[Ticket]:  # 函数：按可选状态和优先级筛选 SQLite 中的工单。
    status_value = status.value if isinstance(status, TicketStatus) else status
    priority_value = (
        priority.value
        if isinstance(priority, TicketPriority)
        else priority
    )

    return list_ticket_records(
        status=status_value,
        priority=priority_value,
    )


def update_ticket_status(
    ticket_id: str,
    status: TicketStatus | str,
) -> Ticket | None:  # 函数：更新指定工单状态，并返回更新后的工单。
    status_value = status.value if isinstance(status, TicketStatus) else status

    return update_ticket_status_record(
        ticket_id=ticket_id,
        status=status_value,
    )


def delete_ticket(ticket_id: str) -> bool:  # 函数：从 SQLite 删除指定工单，返回是否删除成功。
    return delete_ticket_record(ticket_id)