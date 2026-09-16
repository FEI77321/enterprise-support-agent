"""验证写操作的幂等复用、冲突拦截与结果未知保护。"""

from __future__ import annotations

import sys
import os
import time
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.access_control import Actor, reset_current_actor, set_current_actor
from app.agent_harness import AgentHarness, create_harness_session
from app.operation_store import begin_operation, mark_operation_unknown
from app.tool_registry import ToolResult
import app.agent_harness as harness_module


def main() -> None:
    actor = Actor(f"reliability-user-{uuid4().hex[:6]}", "employee")
    token = set_current_actor(actor)
    try:
        key = f"idempotency-{uuid4().hex}"
        first = AgentHarness().execute_tool(
            session=create_harness_session(request_id="reliability-first", engine="tool_call", max_steps=2),
            tool_name="create_ticket", arguments={"message": "Idempotency contract VPN failure"}, idempotency_key=key,
        )
        second = AgentHarness().execute_tool(
            session=create_harness_session(request_id="reliability-second", engine="tool_call", max_steps=2),
            tool_name="create_ticket", arguments={"message": "Idempotency contract VPN failure"}, idempotency_key=key,
        )
        conflict = AgentHarness().execute_tool(
            session=create_harness_session(request_id="reliability-conflict", engine="tool_call", max_steps=2),
            tool_name="create_ticket", arguments={"message": "Different ticket payload"}, idempotency_key=key,
        )
        unknown_key = f"unknown-{uuid4().hex}"
        pending, should_execute = begin_operation(actor.actor_id, "create_ticket", {"message": "unknown"}, unknown_key)
        mark_operation_unknown(pending.operation_id)
        unknown, unknown_should_execute = begin_operation(actor.actor_id, "create_ticket", {"message": "unknown"}, unknown_key)
        original_run_tool = harness_module.run_tool
        old_timeout = os.environ.get("TOOL_EXECUTION_TIMEOUT_SECONDS")
        try:
            def slow_write(tool_name: str, **_kwargs: object) -> ToolResult:
                time.sleep(0.05)
                return ToolResult(tool_name=tool_name, success=True, data={"unexpected": True})

            harness_module.run_tool = slow_write
            os.environ["TOOL_EXECUTION_TIMEOUT_SECONDS"] = "0.001"
            timeout_result = AgentHarness().execute_tool(
                session=create_harness_session(request_id="reliability-timeout", engine="tool_call", max_steps=2),
                tool_name="create_ticket", arguments={"message": "write timeout contract"}, idempotency_key=f"timeout-{uuid4().hex}",
            )
        finally:
            harness_module.run_tool = original_run_tool
            if old_timeout is None:
                os.environ.pop("TOOL_EXECUTION_TIMEOUT_SECONDS", None)
            else:
                os.environ["TOOL_EXECUTION_TIMEOUT_SECONDS"] = old_timeout

        checks = [
            first.status == "completed" and first.tool_result is not None and first.tool_result.success,
            second.status == "completed" and second.tool_result == first.tool_result,
            conflict.status == "blocked" and conflict.tool_result is not None and conflict.tool_result.error_type == "idempotency_key_conflict",
            should_execute,
            not unknown_should_execute and unknown.status == "unknown",
            AgentHarness().execute_tool(session=create_harness_session(request_id="read", engine="tool_call", max_steps=2), tool_name="search_knowledge_base", arguments={"query": "VPN"}).status == "completed",
            timeout_result.status == "failed" and timeout_result.tool_result is not None and timeout_result.tool_result.error_type == "operation_result_unknown",
        ]
    finally:
        reset_current_actor(token)
    assert all(checks), checks
    print(f"Tool reliability contract: Passed {len(checks)}/{len(checks)}")


if __name__ == "__main__":
    main()
