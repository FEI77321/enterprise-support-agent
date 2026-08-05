# 模块职责：会话记忆集成评估：验证自动工具调用接口会记录用户与 Agent 消息、能利用同一会话的历史完成追问，并且不同会话之间不会泄露上下文。

from eval_path import setup_backend_path


setup_backend_path()

from fastapi.testclient import TestClient

from app.conversation_memory import clear_memory, get_recent_turns
from app.main import app


client = TestClient(app)


def test_cleared_memory_is_not_used_by_follow_up() -> tuple[bool, str]:  # 测试函数：验证清空会话记忆后，后续追问不会继续使用旧上下文。
    session_id = "test-cleared-memory-follow-up"

    clear_memory(session_id)

    first_response = client.post(
        "/tool-call/auto",
        json={
            "message": "帮我查询工单 TICKET-20260724-0001 的状态",
            "session_id": session_id,
        },
    )

    if first_response.status_code != 200:
        return False, f"首轮期望状态码 200，实际为 {first_response.status_code}"

    clear_response = client.post(
        "/conversation-memory/clear",
        json={
            "session_id": session_id,
        },
    )

    if clear_response.status_code != 200:
        return False, f"清空接口期望状态码 200，实际为 {clear_response.status_code}"

    follow_up_response = client.post(
        "/tool-call/auto",
        json={
            "message": "它现在是什么状态？",
            "session_id": session_id,
        },
    )

    if follow_up_response.status_code != 200:
        return False, f"追问期望状态码 200，实际为 {follow_up_response.status_code}"

    data = follow_up_response.json()

    if data.get("tool_name") is not None:
        return False, (
            "记忆已清空，追问不应继续查询旧工单，"
            f"实际调用工具为 {data.get('tool_name')}"
        )

    if data.get("decision_type") != "no_tool":
        return False, (
            "记忆清空后应无法理解“它”的指代，"
            f"实际 decision_type={data.get('decision_type')}"
        )

    return True, ""



def test_clear_conversation_memory_api() -> tuple[bool, str]:
    session_id = "test-clear-memory-api"

    clear_memory(session_id)

    client.post(
        "/tool-call/auto",
        json={
            "message": "帮我查询工单 TICKET-20260724-0001 的状态",
            "session_id": session_id,
        },
    )

    turns_before_clear = get_recent_turns(session_id)

    if len(turns_before_clear) != 2:
        return False, f"清空前期望有 2 条记忆，实际为 {len(turns_before_clear)}"

    response = client.post(
        "/conversation-memory/clear",
        json={
            "session_id": session_id,
        },
    )

    if response.status_code != 200:
        return False, f"期望状态码 200，实际为 {response.status_code}"

    data = response.json()

    if not data.get("success"):
        return False, f"期望清空成功，实际为 {data}"

    turns_after_clear = get_recent_turns(session_id)

    if turns_after_clear:
        return False, f"期望清空后没有记忆，实际为 {turns_after_clear}"

    return True, ""


def test_different_sessions_do_not_share_memory() -> tuple[bool, str]:  # 测试函数：验证 不同 会话 do 不 共享 记忆 场景。
    session_a = "test-memory-isolation-a"
    session_b = "test-memory-isolation-b"

    clear_memory(session_a)
    clear_memory(session_b)

    first_response = client.post(
        "/tool-call/auto",
        json={
            "message": "帮我查询工单 TICKET-20260724-0001 的状态",
            "session_id": session_a,
        },
    )

    if first_response.status_code != 200:
        return False, f"session_a 首轮状态码应为 200，实际为 {first_response.status_code}"

    second_response = client.post(
        "/tool-call/auto",
        json={
            "message": "它现在是什么状态？",
            "session_id": session_b,
        },
    )

    if second_response.status_code != 200:
        return False, f"session_b 追问状态码应为 200，实际为 {second_response.status_code}"

    data = second_response.json()

    if data.get("tool_name") is not None:
        return False, (
            "session_b 不应读取 session_a 的工单号，"
            f"实际调用工具为 {data.get('tool_name')}"
        )

    if data.get("decision_type") != "no_tool":
        return False, (
            "session_b 没有历史上下文时应返回 no_tool，"
            f"实际为 {data.get('decision_type')}"
        )

    return True, ""



def test_auto_request_uses_previous_ticket_from_memory() -> tuple[bool, str]:  # 测试函数：验证 自动 请求 使用 历史 工单 from 记忆 场景。
    session_id = "test-tool-call-follow-up"
    clear_memory(session_id)

    first_response = client.post(
        "/tool-call/auto",
        json={
            "message": "帮我查询工单 TICKET-20260724-0001 的状态",
            "session_id": session_id,
        },
    )

    if first_response.status_code != 200:
        return False, f"第一轮期望状态码 200，实际为 {first_response.status_code}"

    second_response = client.post(
        "/tool-call/auto",
        json={
            "message": "它现在是什么状态？",
            "session_id": session_id,
        },
    )

    if second_response.status_code != 200:
        return False, f"第二轮期望状态码 200，实际为 {second_response.status_code}"

    data = second_response.json()

    if not data.get("success"):
        return False, f"期望追问调用成功，实际为 {data}"

    if data.get("tool_name") != "query_ticket_status":
        return False, (
            "期望根据历史工单调用 query_ticket_status，"
            f"实际为 {data.get('tool_name')}"
        )

    return True, ""



def test_auto_request_records_conversation_memory() -> tuple[bool, str]:  # 测试函数：验证 自动 请求 records 对话 记忆 场景。
    session_id = "test-tool-call-memory"
    message = "帮我查询工单 TICKET-20260724-0001 的状态"

    clear_memory(session_id)

    response = client.post(
        "/tool-call/auto",
        json={
            "message": message,
            "session_id": session_id,
        },
    )

    if response.status_code != 200:
        return False, f"期望状态码 200，实际为 {response.status_code}"

    turns = get_recent_turns(session_id)

    if len(turns) != 2:
        return False, f"期望保存 2 条对话，实际为 {len(turns)}"

    if turns[0].role != "user":
        return False, f"期望第一条 role=user，实际为 {turns[0].role}"

    if turns[0].content != message:
        return False, f"期望第一条保存用户消息，实际为 {turns[0].content}"

    if turns[1].role != "assistant":
        return False, f"期望第二条 role=assistant，实际为 {turns[1].role}"

    if not turns[1].content:
        return False, "期望第二条保存 Agent 回复，实际为空"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        (
            "auto_request_records_conversation_memory",
            test_auto_request_records_conversation_memory,
        ),
        (
            "auto_request_uses_previous_ticket_from_memory",
            test_auto_request_uses_previous_ticket_from_memory,
        ),
        (
            "different_sessions_do_not_share_memory",
            test_different_sessions_do_not_share_memory,
        ),
        (
            "clear_conversation_memory_api",
            test_clear_conversation_memory_api,
        ),
        (
            "cleared_memory_is_not_used_by_follow_up",
            test_cleared_memory_is_not_used_by_follow_up,
        ),
    ]

    passed = 0

    for name, test_func in tests:
        ok, reason = test_func()
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}")

        if ok:
            passed += 1
        else:
            print(f"  Reason: {reason}")

    print()
    print(f"Passed: {passed}/{len(tests)}")

    if passed != len(tests):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
