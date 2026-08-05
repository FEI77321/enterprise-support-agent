# 模块职责：验证待确认工具操作的保存、读取、清除和 SQLite 持久化行为。
import json

from eval_path import setup_backend_path

setup_backend_path()

from pathlib import Path
import sys
from app.database import get_connection

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT_TEXT = str(PROJECT_ROOT)

if PROJECT_ROOT_TEXT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_TEXT)

from backend.app.tool_confirmation import (
    clear_pending_confirmation,
    get_confirmation_decision,
    get_pending_confirmation,
    save_pending_confirmation,
)

def test_pending_confirmation_persists_to_sqlite() -> tuple[bool, str]:  # 测试函数：验证待确认操作被真实写入 SQLite 数据库。
    session_id = "test-confirmation-sqlite-persistence"
    clear_pending_confirmation(session_id)

    try:
        save_pending_confirmation(
            session_id=session_id,
            tool_name="delete_ticket",
            arguments={
                "ticket_id": "TICKET-20260724-0001",
            },
            reason="删除工单会永久移除数据，需要用户确认。",
        )

        connection = get_connection()

        try:
            row = connection.execute(
                """
                SELECT tool_name, arguments_json, reason
                FROM pending_confirmations
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return False, "期望数据库中存在待确认操作，实际未查询到记录"

        if row["tool_name"] != "delete_ticket":
            return False, f"期望 tool_name=delete_ticket，实际为 {row['tool_name']}"

        arguments = json.loads(row["arguments_json"])

        if arguments.get("ticket_id") != "TICKET-20260724-0001":
            return False, f"期望数据库保存 ticket_id，实际为 {arguments}"

        return True, ""
    finally:
        clear_pending_confirmation(session_id)

def test_confirmation_message_is_recognized() -> tuple[bool, str]:  # 测试函数：验证明确确认消息会被识别为 confirm。
    result = get_confirmation_decision("确认删除")

    if result != "confirm":
        return False, f"期望确认消息返回 confirm，实际为 {result}"

    return True, ""


def test_cancellation_message_is_recognized() -> tuple[bool, str]:  # 测试函数：验证明确取消消息会被识别为 cancel。
    result = get_confirmation_decision("取消删除")

    if result != "cancel":
        return False, f"期望取消消息返回 cancel，实际为 {result}"

    return True, ""


def test_ambiguous_message_is_not_recognized() -> tuple[bool, str]:  # 测试函数：验证模糊消息不会被误判为确认或取消。
    result = get_confirmation_decision("我再考虑一下")

    if result is not None:
        return False, f"期望模糊消息返回 None，实际为 {result}"

    return True, ""


def test_save_and_get_pending_confirmation() -> tuple[bool, str]:  # 测试函数：验证可以保存并读取指定会话的待确认操作。
    session_id = "test-pending-confirmation"
    clear_pending_confirmation(session_id)

    saved = save_pending_confirmation(
        session_id=session_id,
        tool_name="delete_ticket",
        arguments={
            "ticket_id": "TICKET-20260724-0001",
        },
        reason="删除工单会永久移除数据，需要用户确认。",
    )

    loaded = get_pending_confirmation(session_id)

    if loaded is None:
        return False, "期望读取到待确认操作，实际为 None"

    if loaded != saved:
        return False, f"期望读取结果与保存结果一致，实际为 {loaded}"

    if loaded.arguments.get("ticket_id") != "TICKET-20260724-0001":
        return False, f"期望保存 ticket_id，实际为 {loaded.arguments}"

    return True, ""


def test_pending_confirmation_is_session_isolated() -> tuple[bool, str]:  # 测试函数：验证不同会话之间不能读取彼此的待确认操作。
    session_a = "test-confirmation-session-a"
    session_b = "test-confirmation-session-b"

    clear_pending_confirmation(session_a)
    clear_pending_confirmation(session_b)

    save_pending_confirmation(
        session_id=session_a,
        tool_name="delete_ticket",
        arguments={
            "ticket_id": "TICKET-20260724-0001",
        },
        reason="删除工单会永久移除数据，需要用户确认。",
    )

    pending_for_b = get_pending_confirmation(session_b)

    if pending_for_b is not None:
        return False, f"session_b 不应读取 session_a 的待确认操作，实际为 {pending_for_b}"

    return True, ""


def test_clear_pending_confirmation() -> tuple[bool, str]:  # 测试函数：验证清除后不再能读取指定会话的待确认操作。
    session_id = "test-clear-pending-confirmation"

    save_pending_confirmation(
        session_id=session_id,
        tool_name="delete_ticket",
        arguments={
            "ticket_id": "TICKET-20260724-0001",
        },
        reason="删除工单会永久移除数据，需要用户确认。",
    )

    clear_pending_confirmation(session_id)

    loaded = get_pending_confirmation(session_id)

    if loaded is not None:
        return False, f"期望清除后返回 None，实际为 {loaded}"

    return True, ""


def main() -> None:  # 函数：运行本文件中的全部待确认操作存储评估。
    tests = [
        (
            "save_and_get_pending_confirmation",
            test_save_and_get_pending_confirmation,
        ),
        (
            "pending_confirmation_is_session_isolated",
            test_pending_confirmation_is_session_isolated,
        ),
        (
            "clear_pending_confirmation",
            test_clear_pending_confirmation,
        ),
        (
            "confirmation_message_is_recognized",
            test_confirmation_message_is_recognized,
        ),
        (
            "cancellation_message_is_recognized",
            test_cancellation_message_is_recognized,
        ),
        (
            "ambiguous_message_is_not_recognized",
            test_ambiguous_message_is_not_recognized,
        ),
        (
            "pending_confirmation_persists_to_sqlite",
            test_pending_confirmation_persists_to_sqlite,
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