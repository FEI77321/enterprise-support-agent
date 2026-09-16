"""验证高风险工具审批的会话绑定、单次消费和过期失效。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.tool_action_policy import get_tool_action_policy
from app.tool_confirmation import consume_pending_confirmation, get_pending_confirmation, save_pending_confirmation


def main() -> None:
    session = f"hitl-eval-{uuid4().hex[:8]}"
    pending = save_pending_confirmation(session, "delete_ticket", {"ticket_id": "TICKET-20240101-0001"}, "high risk", 60)
    checks = [
        get_tool_action_policy("create_ticket").requires_confirmation is False,
        get_tool_action_policy("delete_ticket").requires_confirmation is True,
        get_pending_confirmation("another-session", pending.operation_id) is None,
        consume_pending_confirmation(session, pending.operation_id) is not None,
        consume_pending_confirmation(session, pending.operation_id) is None,
    ]
    expired = save_pending_confirmation(f"{session}-expiry", "delete_ticket", {"ticket_id": "TICKET-20240101-0001"}, "high risk", 0)
    checks.append(get_pending_confirmation(f"{session}-expiry", expired.operation_id) is None)
    assert all(checks), checks
    print(f"Human-in-the-loop contract: Passed {len(checks)}/{len(checks)}")


if __name__ == "__main__":
    main()
