# 模块职责：验证 SQLite 数据库能被初始化，并包含会话记忆和待确认操作所需的数据表。

from pathlib import Path
import sys
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT_TEXT = str(PROJECT_ROOT)

if PROJECT_ROOT_TEXT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_TEXT)

from backend.app.database import get_connection, initialize_database


def test_initialize_database_creates_required_tables() -> tuple[bool, str]:  # 测试函数：验证初始化数据库后会创建会话记忆和待确认操作数据表。
    with TemporaryDirectory() as temporary_directory:
        database_path = Path(temporary_directory) / "test.db"

        initialize_database(database_path)

        connection = get_connection(database_path)
        try:
            rows = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        finally:
            connection.close()

        table_names = {
            row["name"]
            for row in rows
        }

        expected_tables = {
            "conversation_turns",
            "pending_confirmations",
            "tickets",
        }

        missing_tables = expected_tables - table_names

        if missing_tables:
            return False, f"缺少数据表: {sorted(missing_tables)}"

    return True, ""


def test_initialize_database_is_idempotent() -> tuple[bool, str]:  # 测试函数：验证重复初始化数据库不会报错或删除已有表。
    with TemporaryDirectory() as temporary_directory:
        database_path = Path(temporary_directory) / "test.db"

        initialize_database(database_path)
        initialize_database(database_path)

        connection = get_connection(database_path)
        try:
            row = connection.execute(
                """
                SELECT COUNT(*) AS table_count
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'conversation_turns'
                """
            ).fetchone()
        finally:
            connection.close()
        if row is None or row["table_count"] != 1:
            return False, f"期望 conversation_turns 表存在一次，实际为 {row}"

    return True, ""


def main() -> None:  # 函数：运行本文件中的全部数据库基础设施评估。
    tests = [
        (
            "initialize_database_creates_required_tables",
            test_initialize_database_creates_required_tables,
        ),
        (
            "initialize_database_is_idempotent",
            test_initialize_database_is_idempotent,
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