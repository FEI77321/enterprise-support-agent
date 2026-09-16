# 模块职责：工单接口路由模块：将创建、查询、筛选、更新和删除工单的业务工具包装为 REST 风格 HTTP 接口。

from fastapi import HTTPException,APIRouter, Header
from app.tools import (
    list_tickets,
    update_ticket_status,
    delete_ticket,
    create_ticket,
    query_ticket_status
)
from app.access_control import (
    authorize_tool, can_manage_ticket, get_ticket_owner, record_ticket_owner,
    resolve_actor,
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
        x_actor_id: str | None = Header(default=None),
        x_actor_role: str | None = Header(default=None),
) -> list[Ticket]:  # 函数：负责 获取 工单 相关逻辑。
    actor = resolve_actor(x_actor_id, x_actor_role)
    tickets = list_tickets(status, priority)
    if actor.role in {"support", "admin"}:
        return tickets
    return [ticket for ticket in tickets if get_ticket_owner(ticket.ticket_id) == actor.actor_id]


@router.post("", response_model=Ticket)
def post_ticket(
    request: TicketCreateRequest,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
) -> Ticket:  # 函数：负责 post 工单 相关逻辑。
    actor = resolve_actor(x_actor_id, x_actor_role)
    ticket = create_ticket(request.message)
    record_ticket_owner(ticket.ticket_id, actor.actor_id)
    return ticket

@router.get("/{ticket_id}", response_model=Ticket)
def get_ticket(
    ticket_id: str,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
) -> Ticket:  # 函数：负责 获取 工单 相关逻辑。
    decision = authorize_tool(resolve_actor(x_actor_id, x_actor_role), "query_ticket_status", {"ticket_id": ticket_id})
    if not decision.allowed:
        raise HTTPException(status_code=403, detail="无权读取该工单")
    ticket = query_ticket_status(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"工单不存在：{ticket_id}")
    return ticket

@router.patch("/{ticket_id}/status", response_model=Ticket)
def patch_ticket_status(
    ticket_id: str, request: TicketStatusUpdate,
    x_actor_id: str | None = Header(default=None), x_actor_role: str | None = Header(default=None),
) -> Ticket:  # 函数：负责 patch 工单 状态 相关逻辑。
    decision = can_manage_ticket(resolve_actor(x_actor_id, x_actor_role))
    if not decision.allowed:
        raise HTTPException(status_code=403, detail="仅 IT Support 或管理员可以更新工单")
    ticket = update_ticket_status(ticket_id, request.status)

    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail=f"工单不存在：{ticket_id}",
        )

    return ticket


@router.delete("/{ticket_id}")
def remove_ticket(
    ticket_id: str,
    x_actor_id: str | None = Header(default=None), x_actor_role: str | None = Header(default=None),
) -> dict[str, str]:  # 函数：负责 remove 工单 相关逻辑。
    decision = authorize_tool(resolve_actor(x_actor_id, x_actor_role), "delete_ticket", {"ticket_id": ticket_id})
    if not decision.allowed:
        raise HTTPException(status_code=403, detail="仅管理员可以删除工单")
    deleted=delete_ticket(ticket_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"工单不存在：{ticket_id}",
        )
    return {
        "message":f"工单已删除：{ticket_id}",
    }
