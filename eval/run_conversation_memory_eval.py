# 模块职责：会话记忆单元评估：验证会话创建、追加消息、限制最近消息数量等底层内存操作，保证多轮能力的基础数据结构可靠。

from eval_path import setup_backend_path


setup_backend_path()

from app.conversation_memory import (
    add_turn,
    clear_memory,
    get_or_create_memory,
    get_recent_turns,
)
from app.database import get_connection

def test_add_turn_persists_to_sqlite() -> tuple[bool, str]:  # 测试函数：验证新增消息确实被写入 SQLite，而不是只保存在 Python 内存中。
    session_id = "test-memory-sqlite-persistence"
    clear_memory(session_id)

    try:
        add_turn(
            session_id=session_id,
            role="user",
            content="这条消息应写入数据库。",
        )

        connection = get_connection()

        try:
            row = connection.execute(
                """
                SELECT role, content
                FROM conversation_turns
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return False, "期望数据库中存在消息记录，实际未查询到记录"

        if row["role"] != "user":
            return False, f"期望 role=user，实际为 {row['role']}"

        if row["content"] != "这条消息应写入数据库。":
            return False, f"期望数据库保存指定内容，实际为 {row['content']}"

        return True, ""
    finally:
        clear_memory(session_id)


def test_create_memory() -> tuple[bool, str]:  # 测试函数：验证 创建 记忆 场景。
    session_id = "test-session-create"
    clear_memory(session_id)

    memory = get_or_create_memory(session_id)

    if memory.session_id != session_id:
        return False, f"期望 session_id={session_id}，实际为 {memory.session_id}"

    if memory.turns != []:
        return False, f"期望 turns 为空，实际为 {memory.turns}"

    return True, ""


def test_add_turns() -> tuple[bool, str]:  # 测试函数：验证 add turns 场景。
    session_id = "test-session-add"
    clear_memory(session_id)

    add_turn(session_id, "user", "你好")
    memory = add_turn(session_id, "assistant", "你好，有什么可以帮你？")

    if len(memory.turns) != 2:
        return False, f"期望 2 轮对话，实际为 {len(memory.turns)}"

    if memory.turns[0].role != "user":
        return False, f"期望第一轮 role=user，实际为 {memory.turns[0].role}"

    if memory.turns[1].content != "你好，有什么可以帮你？":
        return False, f"期望第二轮内容正确，实际为 {memory.turns[1].content}"

    return True, ""


def test_recent_turns_limit() -> tuple[bool, str]:  # 测试函数：验证 最近 turns 数量限制 场景。
    session_id = "test-session-recent"
    clear_memory(session_id)

    for index in range(10):
        add_turn(session_id, "user", f"message-{index}")

    recent_turns = get_recent_turns(session_id, limit=3)

    if len(recent_turns) != 3:
        return False, f"期望最近 3 条，实际为 {len(recent_turns)}"

    contents = [turn.content for turn in recent_turns]

    if contents != ["message-7", "message-8", "message-9"]:
        return False, f"期望返回最后 3 条，实际为 {contents}"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("create_memory", test_create_memory),
        ("add_turns", test_add_turns),
        ("recent_turns_limit", test_recent_turns_limit),
        (
            "add_turn_persists_to_sqlite",
            test_add_turn_persists_to_sqlite,
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
