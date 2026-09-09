"""Harness 合同：验证统一执行治理不会绕过安全与业务基线。"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.agent_harness import AgentHarness, create_harness_session
from app.agent import handle_message
from app.graph_agent import handle_message as handle_graph_message
from app.tool_action_policy import get_tool_action_policy


def test_risk_levels() -> tuple[bool, str]:
    expected = {
        "search_knowledge_base": "read_only",
        "create_ticket": "write_low_risk",
        "delete_ticket": "write_high_risk",
    }
    actual = {name: get_tool_action_policy(name).risk_level for name in expected}
    return actual == expected, f"risk_levels={actual}"


def test_unknown_tool_is_blocked() -> tuple[bool, str]:
    session = create_harness_session(request_id="harness-unknown", engine="tool_call", max_steps=2)
    result = AgentHarness().execute_tool(session=session, tool_name="drop_database", arguments={})
    return (
        result.status == "blocked"
        and result.tool_result is not None
        and result.tool_result.error_type == "unknown_tool"
        and session.executed_steps == 0
        and session.trace_steps[-1].status == "blocked",
        f"status={result.status}, trace={session.trace_steps}",
    )


def test_invalid_arguments_are_blocked() -> tuple[bool, str]:
    session = create_harness_session(request_id="harness-args", engine="tool_call", max_steps=2)
    result = AgentHarness().execute_tool(
        session=session, tool_name="query_ticket_status", arguments={}
    )
    return (
        result.status == "blocked"
        and result.tool_result is not None
        and result.tool_result.error_type == "invalid_args"
        and session.executed_steps == 0,
        f"status={result.status}, error={result.reason}",
    )


def test_high_risk_tool_requires_confirmation() -> tuple[bool, str]:
    session = create_harness_session(request_id="harness-confirm", engine="tool_call", max_steps=2)
    result = AgentHarness().execute_tool(
        session=session,
        tool_name="delete_ticket",
        arguments={"ticket_id": "TICKET-20260724-0001"},
    )
    return (
        result.status == "confirmation_required"
        and result.requires_confirmation
        and session.executed_steps == 0
        and session.trace_steps[-1].risk_level == "write_high_risk",
        f"status={result.status}, trace={session.trace_steps}",
    )


def test_max_steps_prevents_second_execution() -> tuple[bool, str]:
    session = create_harness_session(request_id="harness-steps", engine="tool_call", max_steps=1)
    first = AgentHarness().execute_tool(
        session=session, tool_name="query_ticket_status", arguments={"ticket_id": "TICKET-20260724-0001"}
    )
    second = AgentHarness().execute_tool(
        session=session, tool_name="query_ticket_status", arguments={"ticket_id": "TICKET-20260724-0001"}
    )
    return (
        first.status == "completed"
        and second.status == "max_steps_exceeded"
        and session.executed_steps == 1
        and session.trace_steps[-1].status == "max_steps_exceeded",
        f"first={first.status}, second={second.status}, steps={session.executed_steps}",
    )


def test_rules_path_returns_harness_trace() -> tuple[bool, str]:
    previous = os.environ.get("AGENT_HARNESS_ENABLED")
    os.environ["AGENT_HARNESS_ENABLED"] = "true"
    try:
        response = handle_message("VPN 连接失败怎么办", request_id="harness-rules")
    finally:
        if previous is None:
            os.environ.pop("AGENT_HARNESS_ENABLED", None)
        else:
            os.environ["AGENT_HARNESS_ENABLED"] = previous

    return (
        response.request_id == "harness-rules"
        and bool(response.harness_trace)
        and response.harness_trace[0]["tool_name"] == "search_knowledge_base"
        and response.harness_trace[0]["status"] == "completed",
        f"trace={response.harness_trace}",
    )


def test_feature_flag_preserves_baseline() -> tuple[bool, str]:
    previous = os.environ.get("AGENT_HARNESS_ENABLED")
    os.environ["AGENT_HARNESS_ENABLED"] = "false"
    try:
        response = handle_message("VPN 连接失败怎么办", request_id="harness-off")
    finally:
        if previous is None:
            os.environ.pop("AGENT_HARNESS_ENABLED", None)
        else:
            os.environ["AGENT_HARNESS_ENABLED"] = previous

    return response.harness_trace == [], f"trace={response.harness_trace}"


def test_langgraph_path_returns_harness_trace() -> tuple[bool, str]:
    previous = os.environ.get("AGENT_HARNESS_ENABLED")
    os.environ["AGENT_HARNESS_ENABLED"] = "true"
    try:
        response = handle_graph_message("VPN 连接失败怎么办", request_id="harness-graph")
    finally:
        if previous is None:
            os.environ.pop("AGENT_HARNESS_ENABLED", None)
        else:
            os.environ["AGENT_HARNESS_ENABLED"] = previous

    return (
        response.request_id == "harness-graph"
        and bool(response.harness_trace)
        and response.harness_trace[0]["tool_name"] == "search_knowledge_base"
        and response.harness_trace[0]["status"] == "completed",
        f"trace={response.harness_trace}",
    )


def main() -> None:
    checks = [
        ("risk_levels", test_risk_levels),
        ("unknown_tool_is_blocked", test_unknown_tool_is_blocked),
        ("invalid_arguments_are_blocked", test_invalid_arguments_are_blocked),
        ("high_risk_tool_requires_confirmation", test_high_risk_tool_requires_confirmation),
        ("max_steps_prevents_second_execution", test_max_steps_prevents_second_execution),
        ("rules_path_returns_harness_trace", test_rules_path_returns_harness_trace),
        ("langgraph_path_returns_harness_trace", test_langgraph_path_returns_harness_trace),
        ("feature_flag_preserves_baseline", test_feature_flag_preserves_baseline),
    ]
    passed = 0
    for name, check in checks:
        success, detail = check()
        print(f"{'PASS' if success else 'FAIL'} {name}: {detail}")
        passed += int(success)
    print(f"\nAgent Harness contract: Passed {passed}/{len(checks)}")
    if passed != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
