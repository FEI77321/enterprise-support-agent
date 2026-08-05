# 模块职责：工单接口路由模块：将创建、查询、筛选、更新和删除工单的业务工具包装为 REST 风格 HTTP 接口。

from fastapi import HTTPException,APIRouter
from app.tools import (
    list_tickets,
    update_ticket_status,
    delete_ticket,
    create_ticket,
    query_ticket_status
)
from app.models import (
    Ticket,
    TicketStatus,
    TicketPriority,
    TicketCreateRequest,
    TicketStatusUpdate
)

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get( "", response_model=list[Ticket])
def get_tickets(
        status:TicketStatus| None=None,
        priority:TicketPriority| None=None,
) -> list[Ticket]:  # 函数：负责 获取 工单 相关逻辑。
    return list_tickets(status, priority)


@router.post("", response_model=Ticket)
def post_ticket(request: TicketCreateRequest) -> Ticket:  # 函数：负责 post 工单 相关逻辑。
    return create_ticket(request.message)

@router.get("/{ticket_id}", response_model=Ticket)
def get_ticket(ticket_id: str) -> Ticket:  # 函数：负责 获取 工单 相关逻辑。
    ticket = query_ticket_status(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"工单不存在：{ticket_id}")
    return ticket

@router.patch("/{ticket_id}/status", response_model=Ticket)
def patch_ticket_status(ticket_id: str, request: TicketStatusUpdate) -> Ticket:  # 函数：负责 patch 工单 状态 相关逻辑。
    ticket = update_ticket_status(ticket_id, request.status)

    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail=f"工单不存在：{ticket_id}",
        )

    return ticket


@router.delete("/{ticket_id}")
def remove_ticket(ticket_id: str) -> dict[str, str]:  # 函数：负责 remove 工单 相关逻辑。
    deleted=delete_ticket(ticket_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"工单不存在：{ticket_id}",
        )
    return {
        "message":f"工单已删除：{ticket_id}",
    }
