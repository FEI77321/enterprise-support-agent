# 模块职责：验证 SQLite 工单仓储层能够保存和读取完整的 Ticket 数据。

from pathlib import Path
from tempfile import TemporaryDirectory

from eval_path import setup_backend_path


setup_backend_path()

from app.models import Ticket, TicketPriority, TicketStatus
from app.ticket_repository import (
    delete_ticket_record,
    get_ticket_by_id,
    insert_ticket,
    get_next_ticket_sequence,
    list_ticket_records,
    update_ticket_status_record,
)



def test_insert_and_get_ticket() -> tuple[bool, str]:  # 测试函数：验证插入工单后可以按 ticket_id 读取到内容完全一致的工单。
    with TemporaryDirectory() as temporary_directory:
        database_path = Path(temporary_directory) / "tickets-test.db"

        expected_ticket = Ticket(
            ticket_id="TICKET-20260803-0001",
            title="VPN 连接异常",
            description="用户 VPN 登录失败，无法连接公司网络。",
            category="IT_SUPPORT",
            priority=TicketPriority.HIGH,
            status=TicketStatus.OPEN,
            assignee="IT Support Team",
            created_at="2026-08-03T20:00:00",
        )

        saved_ticket = insert_ticket(
            ticket=expected_ticket,
            database_path=database_path,
        )

        if saved_ticket != expected_ticket:
            return False, f"期望返回保存的工单，实际为 {saved_ticket}"

        loaded_ticket = get_ticket_by_id(
            ticket_id=expected_ticket.ticket_id,
            database_path=database_path,
        )

        if loaded_ticket is None:
            return False, "期望读取到已保存的工单，实际为 None"

        if loaded_ticket != expected_ticket:
            return False, (
                "期望读取结果与写入工单一致，"
                f"实际为 {loaded_ticket}"
            )

    return True, ""

def _build_test_ticket(
    ticket_id: str,
    priority: TicketPriority = TicketPriority.HIGH,
    status: TicketStatus = TicketStatus.OPEN,
) -> Ticket:  # 函数：创建仓储层评估使用的固定工单对象，减少重复构造代码。
    return Ticket(
        ticket_id=ticket_id,
        title="VPN 连接异常",
        description="用户 VPN 登录失败，无法连接公司网络。",
        category="IT_SUPPORT",
        priority=priority,
        status=status,
        assignee="IT Support Team",
        created_at="2026-08-03T20:00:00",
    )

def test_next_ticket_sequence_uses_max_existing_suffix() -> tuple[bool, str]:  # 测试函数：验证新流水号始终比数据库中最大工单编号后缀大 1。
    with TemporaryDirectory() as temporary_directory:
        database_path = Path(temporary_directory) / "tickets-test.db"

        insert_ticket(
            _build_test_ticket("TICKET-20260802-0007"),
            database_path,
        )
        insert_ticket(
            _build_test_ticket("TICKET-20260803-0012"),
            database_path,
        )

        next_sequence = get_next_ticket_sequence(database_path)

        if next_sequence != 13:
            return False, f"期望下一个流水号为 13，实际为 {next_sequence}"

    return True, ""



def test_list_ticket_records_filters_by_status_and_priority() -> tuple[bool, str]:  # 测试函数：验证工单列表可同时按状态和优先级筛选。
    with TemporaryDirectory() as temporary_directory:
        database_path = Path(temporary_directory) / "tickets-test.db"

        matched_ticket = _build_test_ticket("TICKET-20260803-0001")
        insert_ticket(matched_ticket, database_path)

        insert_ticket(
            _build_test_ticket(
                "TICKET-20260803-0002",
                priority=TicketPriority.MEDIUM,
            ),
            database_path,
        )

        insert_ticket(
            _build_test_ticket(
                "TICKET-20260803-0003",
                status=TicketStatus.CLOSED,
            ),
            database_path,
        )

        tickets = list_ticket_records(
            status=TicketStatus.OPEN.value,
            priority=TicketPriority.HIGH.value,
            database_path=database_path,
        )

        ticket_ids = [ticket.ticket_id for ticket in tickets]

        if ticket_ids != [matched_ticket.ticket_id]:
            return False, f"期望只筛选到目标工单，实际为 {ticket_ids}"

    return True, ""


def test_update_ticket_status_record() -> tuple[bool, str]:  # 测试函数：验证更新工单状态后，数据库能读取到更新结果。
    with TemporaryDirectory() as temporary_directory:
        database_path = Path(temporary_directory) / "tickets-test.db"
        ticket = _build_test_ticket("TICKET-20260803-0001")

        insert_ticket(ticket, database_path)

        updated_ticket = update_ticket_status_record(
            ticket_id=ticket.ticket_id,
            status=TicketStatus.IN_PROGRESS.value,
            database_path=database_path,
        )

        if updated_ticket is None:
            return False, "期望更新成功，实际返回 None"

        if updated_ticket.status != TicketStatus.IN_PROGRESS:
            return False, f"期望状态为 IN_PROGRESS，实际为 {updated_ticket.status}"

        loaded_ticket = get_ticket_by_id(
            ticket.ticket_id,
            database_path,
        )

        if loaded_ticket is None:
            return False, "期望更新后仍能查询到工单，实际为 None"

        if loaded_ticket.status != TicketStatus.IN_PROGRESS:
            return False, f"期望数据库状态已更新，实际为 {loaded_ticket.status}"

    return True, ""


def test_delete_ticket_record() -> tuple[bool, str]:  # 测试函数：验证删除工单后无法再次查询，并且重复删除返回 False。
    with TemporaryDirectory() as temporary_directory:
        database_path = Path(temporary_directory) / "tickets-test.db"
        ticket = _build_test_ticket("TICKET-20260803-0001")

        insert_ticket(ticket, database_path)

        deleted = delete_ticket_record(
            ticket.ticket_id,
            database_path,
        )

        if not deleted:
            return False, "期望首次删除成功，实际返回 False"

        loaded_ticket = get_ticket_by_id(
            ticket.ticket_id,
            database_path,
        )

        if loaded_ticket is not None:
            return False, f"期望删除后查询不到工单，实际为 {loaded_ticket}"

        deleted_again = delete_ticket_record(
            ticket.ticket_id,
            database_path,
        )

        if deleted_again:
            return False, "期望重复删除不存在的工单返回 False"

    return True, ""



def main() -> None:  # 函数：运行本文件中的工单仓储层评估。
    tests = [
        (
            "insert_and_get_ticket",
            test_insert_and_get_ticket,
        ),
        (
            "list_ticket_records_filters_by_status_and_priority",
            test_list_ticket_records_filters_by_status_and_priority,
        ),
        (
            "update_ticket_status_record",
            test_update_ticket_status_record,
        ),
        (
            "delete_ticket_record",
            test_delete_ticket_record,
        ),
        (
            "next_ticket_sequence_uses_max_existing_suffix",
            test_next_ticket_sequence_uses_max_existing_suffix,
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