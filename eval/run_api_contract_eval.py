"""API 契约评测：验证聊天接口的响应字段和字段类型保持稳定。"""
from eval_path import setup_backend_path

setup_backend_path()
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_chat_rejects_out_of_scope_question() -> tuple[bool, str]:  # 测试函数：验证非企业支持问题不会触发检索或创建工单。
    response = client.post(
        "/chat",
        json={"message": "会议室门被锁了怎么办"},
    )

    if response.status_code != 200:
        return False, f"期望状态码为 200，实际为 {response.status_code}"

    body = response.json()

    if body["type"] != "clarify":
        return False, (
            "非企业支持问题应返回 type=clarify，"
            f"实际为 {body['type']}"
        )

    if "unsupported_question" not in body["workflow_steps"]:
        return False, (
            "非企业支持问题应记录 unsupported_question，"
            f"实际 workflow_steps={body['workflow_steps']}"
        )

    forbidden_steps = {
        "search_knowledge_base",
        "search_vector_store",
        "create_ticket",
    }
    used_forbidden_steps = forbidden_steps.intersection(
        body["workflow_steps"]
    )

    if used_forbidden_steps:
        return False, (
            "非企业支持问题不应检索知识库、向量库或创建工单，"
            f"实际执行了 {sorted(used_forbidden_steps)}"
        )

    return True, ""



def test_chat_response_contract() -> tuple[bool, str]:  # 测试函数：验证 /chat 接口返回企业支持问答所需的核心字段。
    response = client.post(
        "/chat",
        json={"message": "VPN 720 错误怎么办"},
    )

    if response.status_code != 200:
        return False, f"期望状态码为 200，实际为 {response.status_code}"

    body = response.json()

    required_fields = {
        "request_id": str,
        "answer": str,
        "type": str,
        "workflow_steps": list,
        "sources": list,
    }

    for field_name, expected_type in required_fields.items():
        if field_name not in body:
            return False, f"接口响应缺少字段：{field_name}"

        if not isinstance(body[field_name], expected_type):
            return False, (
                f"字段 {field_name} 类型错误，"
                f"期望 {expected_type.__name__}，"
                f"实际 {type(body[field_name]).__name__}"
            )
        if body["type"] != "answer":
            return False, (
                "VPN 知识库问答应返回 type=answer，"
                f"实际为 {body['type']}"
            )

        if "search_knowledge_base" not in body["workflow_steps"]:
            return False, (
                "VPN 知识库问答应经过 search_knowledge_base，"
                f"实际 workflow_steps={body['workflow_steps']}"
            )

    if not body["answer"]:
        return False, "answer 不应为空"

    if not body["sources"]:
        return False, "VPN 知识库问答应返回至少一个来源"

    source = body["sources"][0]

    source_required_fields = {
        "file": str,
        "snippet": str,
        "score": int,
        "chunk_id": str,
    }

    for field_name, expected_type in source_required_fields.items():
        if field_name not in source:
            return False, f"来源对象缺少字段：{field_name}"

        if not isinstance(source[field_name], expected_type):
            return False, (
                f"来源字段 {field_name} 类型错误，"
                f"期望 {expected_type.__name__}，"
                f"实际 {type(source[field_name]).__name__}"
            )

    return True, ""

def test_chat_rejects_too_short_message() -> tuple[bool, str]:  # 测试函数：验证 /chat 会拒绝长度不足的用户消息。
    response = client.post(
        "/chat",
        json={"message": "问"},
    )

    if response.status_code != 422:
        return False, (
            "消息长度不足时应返回 422，"
            f"实际为 {response.status_code}"
        )

    body = response.json()

    if "detail" not in body:
        return False, f"422 响应缺少 detail 字段，实际 body={body}"

    if not isinstance(body["detail"], list):
        return False, (
            "422 响应的 detail 应为列表，"
            f"实际类型为 {type(body['detail']).__name__}"
        )

    return True, ""

def test_system_endpoints_contract() -> tuple[bool, str]:  # 测试函数：验证健康检查和版本接口的基础响应结构。
    health_response = client.get("/health")

    if health_response.status_code != 200:
        return False, (
            "/health 应返回 200，"
            f"实际为 {health_response.status_code}"
        )

    if health_response.json() != {"status": "ok"}:
        return False, (
            "/health 响应不符合契约，"
            f"实际为 {health_response.json()}"
        )

    version_response = client.get("/version")

    if version_response.status_code != 200:
        return False, (
            "/version 应返回 200，"
            f"实际为 {version_response.status_code}"
        )

    body = version_response.json()

    if body.get("code") != 0:
        return False, f"/version 的 code 应为 0，实际为 {body.get('code')}"

    if body.get("message") != "success":
        return False, (
            "/version 的 message 应为 success，"
            f"实际为 {body.get('message')}"
        )

    version_data = body.get("data")

    if not isinstance(version_data, dict):
        return False, f"/version 的 data 应为对象，实际为 {version_data}"

    for field_name in ("name", "version"):
        if not isinstance(version_data.get(field_name), str):
            return False, (
                f"/version 的 data.{field_name} 应为字符串，"
                f"实际为 {version_data.get(field_name)}"
            )

    return True, ""

def test_openapi_contains_core_paths() -> tuple[bool, str]:  # 测试函数：验证 OpenAPI 文档暴露聊天和系统核心接口。
    response = client.get("/openapi.json")

    if response.status_code != 200:
        return False, (
            "/openapi.json 应返回 200，"
            f"实际为 {response.status_code}"
        )

    schema = response.json()
    paths = schema.get("paths")

    if not isinstance(paths, dict):
        return False, "OpenAPI 文档缺少 paths 对象"

    expected_methods = {
        "/chat": "post",
        "/health": "get",
        "/version": "get",
    }

    for path, method in expected_methods.items():
        if path not in paths:
            return False, f"OpenAPI 文档缺少路径：{path}"

        if method not in paths[path]:
            return False, (
                f"OpenAPI 文档中 {path} 缺少 "
                f"{method.upper()} 方法"
            )

    return True, ""

def test_ticket_lifecycle_contract() -> tuple[bool, str]:  # 测试函数：验证工单创建、查询、更新和删除接口能够组成完整生命周期。
    ticket_id: str | None = None

    try:
        create_response = client.post(
            "/tickets",
            json={"message": "API 契约评测专用工单，请删除"},
        )

        if create_response.status_code != 200:
            return False, (
                "创建工单应返回 200，"
                f"实际为 {create_response.status_code}"
            )

        created_ticket = create_response.json()
        ticket_id = created_ticket.get("ticket_id")

        if not isinstance(ticket_id, str) or not ticket_id:
            return False, (
                "创建工单响应缺少有效 ticket_id，"
                f"实际为 {created_ticket}"
            )

        if created_ticket.get("status") != "OPEN":
            return False, (
                "新建工单状态应为 OPEN，"
                f"实际为 {created_ticket.get('status')}"
            )

        get_response = client.get(f"/tickets/{ticket_id}")

        if get_response.status_code != 200:
            return False, (
                "查询刚创建的工单应返回 200，"
                f"实际为 {get_response.status_code}"
            )

        if get_response.json().get("ticket_id") != ticket_id:
            return False, "查询到的工单 ticket_id 与创建结果不一致"

        update_response = client.patch(
            f"/tickets/{ticket_id}/status",
            json={"status": "IN_PROGRESS"},
        )

        if update_response.status_code != 200:
            return False, (
                "更新工单状态应返回 200，"
                f"实际为 {update_response.status_code}"
            )

        if update_response.json().get("status") != "IN_PROGRESS":
            return False, (
                "工单状态更新失败，"
                f"实际为 {update_response.json().get('status')}"
            )
        list_response = client.get(
            "/tickets",
            params={"status": "IN_PROGRESS"},
        )

        if list_response.status_code != 200:
            return False, (
                "按状态筛选工单应返回 200，"
                f"实际为 {list_response.status_code}"
            )

        tickets = list_response.json()
        ticket_ids = {
            ticket.get("ticket_id")
            for ticket in tickets
        }

        if ticket_id not in ticket_ids:
            return False, (
                "按 IN_PROGRESS 筛选时应包含刚更新的工单，"
                f"实际 ticket_ids={sorted(ticket_ids)}"
            )

        delete_response = client.delete(f"/tickets/{ticket_id}")

        if delete_response.status_code != 200:
            return False, (
                "删除工单应返回 200，"
                f"实际为 {delete_response.status_code}"
            )

        query_after_delete_response = client.get(
            f"/tickets/{ticket_id}"
        )

        if query_after_delete_response.status_code != 404:
            return False, (
                "删除工单后再次查询应返回 404，"
                f"实际为 {query_after_delete_response.status_code}"
            )

        ticket_id = None
        return True, ""

    finally:
        if ticket_id is not None:
            client.delete(f"/tickets/{ticket_id}")

def test_ticket_status_rejects_invalid_value() -> tuple[bool, str]:  # 测试函数：验证工单状态更新接口会拒绝不在枚举范围内的状态。
    response = client.patch(
        "/tickets/TICKET-NOT-USED/status",
        json={"status": "DONE"},
    )

    if response.status_code != 422:
        return False, (
            "非法工单状态应返回 422，"
            f"实际为 {response.status_code}"
        )

    body = response.json()

    if "detail" not in body:
        return False, f"422 响应缺少 detail 字段，实际 body={body}"

    return True, ""

def test_ticket_not_found_contract() -> tuple[bool, str]:  # 测试函数：验证查询不存在的工单时返回标准 404 响应。
    ticket_id = "TICKET-NOT-FOUND-FOR-EVAL"

    response = client.get(f"/tickets/{ticket_id}")

    if response.status_code != 404:
        return False, (
            "查询不存在的工单应返回 404，"
            f"实际为 {response.status_code}"
        )

    body = response.json()

    if "detail" not in body:
        return False, f"404 响应缺少 detail 字段，实际 body={body}"

    if ticket_id not in body["detail"]:
        return False, (
            "404 错误信息应包含请求的 ticket_id，"
            f"实际 detail={body['detail']}"
        )

    return True, ""



def main() -> None:  # 函数：执行 API 契约评测并输出结果。
    tests = [
        test_chat_response_contract,
        test_chat_rejects_too_short_message,
        test_chat_rejects_out_of_scope_question,
        test_system_endpoints_contract,
        test_openapi_contains_core_paths,
        test_ticket_lifecycle_contract,
        test_ticket_status_rejects_invalid_value,
        test_ticket_not_found_contract,
    ]

    passed_count = 0

    for test in tests:
        passed, reason = test()

        if passed:
            print(f"PASS {test.__name__}")
            passed_count += 1
        else:
            print(f"FAIL {test.__name__}: {reason}")

    print(f"\nAPI contract eval: Passed {passed_count}/{len(tests)}")


if __name__ == "__main__":
    main()