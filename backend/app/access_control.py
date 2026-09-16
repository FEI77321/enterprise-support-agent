"""身份、角色与资源归属：所有入口共享的最小 RBAC / ABAC 决策层。"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.database import get_connection, initialize_database

Role = Literal["employee", "support", "admin"]


@dataclass(frozen=True)
class Actor:
    actor_id: str
    role: Role = "employee"


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    actor_id: str
    role: Role

    def to_public_dict(self) -> dict[str, object]:
        return asdict(self)


_current_actor: ContextVar[Actor] = ContextVar("current_actor", default=Actor("system-admin", "admin"))


def get_current_actor() -> Actor:
    return _current_actor.get()


def set_current_actor(actor: Actor) -> Token[Actor]:
    return _current_actor.set(actor)


def reset_current_actor(token: Token[Actor]) -> None:
    _current_actor.reset(token)


def resolve_actor(actor_id: str | None, role: str | None) -> Actor:
    normalized_role = (role or "employee").lower()
    safe_role: Role = normalized_role if normalized_role in {"employee", "support", "admin"} else "employee"
    return Actor((actor_id or "employee-demo").strip()[:64] or "employee-demo", safe_role)


def record_ticket_owner(ticket_id: str, owner_id: str, database_path: Path | None = None) -> None:
    initialize_database(database_path)
    connection = get_connection(database_path)
    try:
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO ticket_ownership(ticket_id, owner_id, created_at) VALUES (?, ?, ?)",
                (ticket_id, owner_id, datetime.now(timezone.utc).isoformat()),
            )
    finally:
        connection.close()


def get_ticket_owner(ticket_id: str, database_path: Path | None = None) -> str | None:
    initialize_database(database_path)
    connection = get_connection(database_path)
    try:
        row = connection.execute("SELECT owner_id FROM ticket_ownership WHERE ticket_id = ?", (ticket_id,)).fetchone()
        return row["owner_id"] if row else None
    finally:
        connection.close()


def authorize_tool(actor: Actor, tool_name: str, arguments: dict[str, object]) -> AuthorizationDecision:
    if tool_name in {"search_knowledge_base", "search_vector_store", "create_ticket"}:
        return AuthorizationDecision(True, "role_allowed", actor.actor_id, actor.role)
    if tool_name == "delete_ticket":
        return AuthorizationDecision(actor.role == "admin", "admin_required" if actor.role != "admin" else "role_allowed", actor.actor_id, actor.role)
    if tool_name == "query_ticket_status":
        ticket_id = arguments.get("ticket_id")
        if not isinstance(ticket_id, str):
            return AuthorizationDecision(False, "ticket_id_required", actor.actor_id, actor.role)
        if actor.role in {"support", "admin"}:
            return AuthorizationDecision(True, "support_scope", actor.actor_id, actor.role)
        owner = get_ticket_owner(ticket_id)
        return AuthorizationDecision(owner == actor.actor_id, "owner_scope" if owner == actor.actor_id else "ticket_not_owned", actor.actor_id, actor.role)
    return AuthorizationDecision(False, "unknown_tool", actor.actor_id, actor.role)


def can_approve_high_risk(actor: Actor) -> AuthorizationDecision:
    return AuthorizationDecision(actor.role == "admin", "admin_required" if actor.role != "admin" else "approver_allowed", actor.actor_id, actor.role)


def can_manage_ticket(actor: Actor) -> AuthorizationDecision:
    return AuthorizationDecision(actor.role in {"support", "admin"}, "support_role_required" if actor.role == "employee" else "support_scope", actor.actor_id, actor.role)


def record_approval_event(operation_id: str, requester_id: str, approver_id: str | None, decision: str, reason: str | None = None) -> None:
    initialize_database()
    connection = get_connection()
    try:
        with connection:
            connection.execute(
                "INSERT INTO approval_audit_events(operation_id, requester_id, approver_id, decision, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (operation_id, requester_id, approver_id, decision, reason, datetime.now(timezone.utc).isoformat()),
            )
    finally:
        connection.close()
