"""验证员工、支持人员、管理员在工单资源与审批上的最小权限边界。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.access_control import Actor, authorize_tool, can_approve_high_risk, reset_current_actor, set_current_actor
from app.tool_registry import run_tool


def main() -> None:
    owner = Actor(f"employee-owner-{uuid4().hex[:6]}", "employee")
    token = set_current_actor(owner)
    try:
        created = run_tool("create_ticket", message="RBAC contract test VPN unavailable")
    finally:
        reset_current_actor(token)
    ticket_id = (created.data or {}).get("ticket", {}).get("ticket_id")
    assert created.success and isinstance(ticket_id, str)
    checks = [
        authorize_tool(owner, "query_ticket_status", {"ticket_id": ticket_id}).allowed,
        not authorize_tool(Actor("employee-other", "employee"), "query_ticket_status", {"ticket_id": ticket_id}).allowed,
        authorize_tool(Actor("support-a", "support"), "query_ticket_status", {"ticket_id": ticket_id}).allowed,
        not authorize_tool(owner, "delete_ticket", {"ticket_id": ticket_id}).allowed,
        not can_approve_high_risk(Actor("support-a", "support")).allowed,
        can_approve_high_risk(Actor("admin-a", "admin")).allowed,
    ]
    assert all(checks), checks
    print(f"RBAC and approval contract: Passed {len(checks)}/{len(checks)}")


if __name__ == "__main__":
    main()
