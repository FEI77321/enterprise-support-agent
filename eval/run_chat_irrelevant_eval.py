# 模块职责：无关聊天问题评估：验证普通 /chat 遇到非企业支持范围问题时，不会自动创建 IT 工单。

from eval_path import setup_backend_path

setup_backend_path()

from fastapi.testclient import TestClient

from app.main import app
from app.agent import handle_message

client = TestClient(app)

def test_account_lock_question_stays_in_support_scope() -> tuple[bool, str]:  # 测试函数：验证账号被锁问题不会被错误拦截为无关聊天。
    response = handle_message("账号被锁了怎么办")

    if "unsupported_question" in response.workflow_steps:
        return False, (
            "账号问题不应被范围判断拦截，"
            f"实际为 {response.workflow_steps}"
        )

    if response.type != "answer":
        return False, f"期望 response.type 为 answer，实际为 {response.type}"

    source_files = {source.file for source in response.sources}

    if "account_login_faq.md" not in source_files:
        return False, (
            "期望命中 account_login_faq.md，"
            f"实际来源为 {sorted(source_files)}"
        )

    return True, ""



def test_non_it_lock_question_does_not_create_ticket() -> tuple[bool, str]:  # 测试函数：验证非账号语境下的“被锁”问题不会被当成 IT 工单。
    response = handle_message("会议室门被锁了怎么办")

    if response.type != "clarify":
        return False, f"期望 response.type 为 clarify，实际为 {response.type}"

    if response.ticket is not None:
        return False, f"期望不创建工单，实际 ticket={response.ticket}"

    if "unsupported_question" not in response.workflow_steps:
        return False, (
            "期望 workflow_steps 包含 unsupported_question，"
            f"实际为 {response.workflow_steps}"
        )
    retrieval_steps = {
        "search_knowledge_base",
        "search_vector_store",
    }

    used_retrieval_steps = retrieval_steps.intersection(
        response.workflow_steps
    )

    if used_retrieval_steps:
        return False, (
            "无关问题应在检索前被范围判断拦截，"
            f"实际仍调用了 {sorted(used_retrieval_steps)}"
        )

    if "create_ticket" in response.workflow_steps:
        return False, (
            "非 IT 问题不应进入 create_ticket，"
            f"实际为 {response.workflow_steps}"
        )

    return True, ""


def test_irrelevant_chat_does_not_create_ticket() -> tuple[bool, str]:  # 测试函数：验证无关问题不会创建工单。
    response = client.post("/chat", json={"message": "今天午饭吃什么？"})

    if response.status_code != 200:
        return False, f"期望 status_code=200，实际为 {response.status_code}, body={response.text}"

    data = response.json()

    if data.get("type") == "ticket_created":
        return False, f"无关问题不应创建工单，实际响应为 {data}"

    if data.get("ticket") is not None:
        return False, f"无关问题 ticket 应为空，实际为 {data.get('ticket')}"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的全部无关聊天问题评估。
    tests = [
        (
            "irrelevant_chat_does_not_create_ticket",
            test_irrelevant_chat_does_not_create_ticket,
        ),
        (
            "non_it_lock_question_does_not_create_ticket",
            test_non_it_lock_question_does_not_create_ticket,
        ),
        (
            "account_lock_question_stays_in_support_scope",
            test_account_lock_question_stays_in_support_scope,
        ),
    ]

    passed = 0

    for name, test_func in tests:
        ok, reason = test_func()
        print(f"{'PASS' if ok else 'FAIL'} {name}")

        if ok:
            passed += 1
        else:
            print(f"  Reason: {reason}")

    print()
    print(f"Irrelevant chat eval: Passed {passed}/{len(tests)}")

    if passed != len(tests):
        raise SystemExit(1)

if __name__ == "__main__":
    main()