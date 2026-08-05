# 模块职责：验证旧 tickets.json 可迁移到 SQLite，且重复迁移不会产生重复工单。

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from eval_path import setup_backend_path


setup_backend_path()

from app.ticket_migration import migrate_legacy_tickets
from app.ticket_repository import get_ticket_by_id


def test_migrate_legacy_tickets_is_idempotent() -> tuple[bool, str]:  # 测试函数：验证首次迁移会导入工单，重复迁移不会重复插入。
    with TemporaryDirectory() as temporary_directory:
        temporary_path = Path(temporary_directory)
        source_file = temporary_path / "tickets.json"
        database_path = temporary_path / "tickets-test.db"

        source_file.write_text(
            json.dumps(
                [
                    {
                        "ticket_id": "TICKET-20260803-0001",
                        "title": "VPN 连接异常",
                        "description": "用户 VPN 登录失败，无法连接公司网络。",
                        "category": "IT_SUPPORT",
                        "priority": "HIGH",
                        "status": "OPEN",
                        "assignee": "IT Support Team",
                        "created_at": "2026-08-03T20:00:00",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        first_migrated_count = migrate_legacy_tickets(
            source_file=source_file,
            database_path=database_path,
        )

        if first_migrated_count != 1:
            return False, f"期望首次迁移 1 条，实际为 {first_migrated_count}"

        migrated_ticket = get_ticket_by_id(
            ticket_id="TICKET-20260803-0001",
            database_path=database_path,
        )

        if migrated_ticket is None:
            return False, "期望迁移后能查询到工单，实际为 None"

        second_migrated_count = migrate_legacy_tickets(
            source_file=source_file,
            database_path=database_path,
        )

        if second_migrated_count != 0:
            return False, f"期望重复迁移新增 0 条，实际为 {second_migrated_count}"

    return True, ""


def main() -> None:  # 函数：运行本文件中的工单 JSON 到 SQLite 迁移评估。
    tests = [
        (
            "migrate_legacy_tickets_is_idempotent",
            test_migrate_legacy_tickets_is_idempotent,
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