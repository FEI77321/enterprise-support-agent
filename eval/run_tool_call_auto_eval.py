# 模块职责：自动工具调用 API 评估：覆盖默认 Mock、OpenAI Provider、非法 Provider、非法 JSON、创建工单、查询工单和无需工具等场景。

from eval_path import setup_backend_path
import sys
import types

setup_backend_path()

from fastapi.testclient import TestClient
import os
from app.main import app
from app.tool_registry import run_tool
from app.tools import delete_ticket


client = TestClient(app)


class FakeInvalidJSONOpenAIResponse:  # 类：模拟返回非法 JSON 的 OpenAI 响应。
    output_text = "not json"


class FakeInvalidJSONOpenAIResponses:  # 类：模拟返回非法 JSON 响应的 responses 对象。
    def create(self, model: str, input: str):  # 函数：模拟或执行客户端的 create 调用。
        return FakeInvalidJSONOpenAIResponse()


class FakeInvalidJSONOpenAIClient:  # 类：模拟会产生非法 JSON 的 OpenAI 客户端。
    def __init__(self, api_key: str, timeout: float, max_retries: int = 0):  # 函数：初始化当前对象所需的状态或依赖。
        self.responses = FakeInvalidJSONOpenAIResponses()





class FakeOpenAIToolCallResponse:  # 类：模拟包含合法工具调用 JSON 的 OpenAI 响应。
    output_text = (
        '{"tool_name": "query_ticket_status", '
        '"arguments": {"ticket_id": "TICKET-20990101-9999"}}'
    )


class FakeOpenAIToolCallResponses:  # 类：模拟工具调用场景下的 responses 子对象。
    def create(self, model: str, input: str):  # 函数：模拟或执行客户端的 create 调用。
        return FakeOpenAIToolCallResponse()


class FakeOpenAIToolCallClient:  # 类：模拟工具调用场景下的 OpenAI 客户端。
    def __init__(self, api_key: str, timeout: float, max_retries: int = 0):  # 函数：初始化当前对象所需的状态或依赖。
        self.responses = FakeOpenAIToolCallResponses()


def test_tool_call_auto_delete_ticket_after_confirmation() -> tuple[bool, str]:  # 测试函数：验证自动接口会拦截删除请求，并在用户确认后真正删除工单。
    session_id = "test-auto-delete-confirm"
    created = run_tool(
        "create_ticket",
        message="用于测试自动删除确认流程的临时工单",
    )

    if not created.success:
        return False, f"创建测试工单失败，实际为 {created}"

    ticket = (created.data or {}).get("ticket") or {}
    ticket_id = ticket.get("ticket_id")

    if not isinstance(ticket_id, str):
        return False, f"期望获得 ticket_id，实际为 {ticket_id}"

    try:
        delete_request = run_auto_with_env(
            message=f"删除工单 {ticket_id}",
            env={"TOOL_CALL_PROVIDER": "mock"},
            session_id=session_id,
        )

        if delete_request.status_code != 200:
            return False, f"删除请求期望状态码 200，实际为 {delete_request.status_code}"

        delete_data = delete_request.json()

        if delete_data.get("decision_type") != "confirmation_required":
            return False, (
                "期望删除请求进入确认状态，"
                f"实际为 {delete_data.get('decision_type')}"
            )

        if not delete_data.get("requires_confirmation"):
            return False, f"期望 requires_confirmation=True，实际为 {delete_data}"

        queried_before_confirm = run_tool(
            "query_ticket_status",
            ticket_id=ticket_id,
        )

        if not (queried_before_confirm.data or {}).get("found"):
            return False, "未确认前不应删除工单，但工单已不存在"

        confirm_request = run_auto_with_env(
            message="确认删除",
            env={"TOOL_CALL_PROVIDER": "mock"},
            session_id=session_id,
        )

        if confirm_request.status_code != 200:
            return False, f"确认请求期望状态码 200，实际为 {confirm_request.status_code}"

        confirm_data = confirm_request.json()

        if confirm_data.get("decision_type") != "confirmed_tool_call":
            return False, (
                "期望确认后执行工具调用，"
                f"实际为 {confirm_data.get('decision_type')}"
            )

        queried_after_confirm = run_tool(
            "query_ticket_status",
            ticket_id=ticket_id,
        )

        if (queried_after_confirm.data or {}).get("found"):
            return False, "确认删除后工单仍然存在"

        return True, ""
    finally:
        delete_ticket(ticket_id)

def test_tool_call_auto_cancel_delete_ticket() -> tuple[bool, str]:  # 测试函数：验证用户取消删除后，系统会清除待确认操作并保留工单。
    session_id = "test-auto-delete-cancel"
    created = run_tool(
        "create_ticket",
        message="用于测试取消删除流程的临时工单",
    )

    if not created.success:
        return False, f"创建测试工单失败，实际为 {created}"

    ticket = (created.data or {}).get("ticket") or {}
    ticket_id = ticket.get("ticket_id")

    if not isinstance(ticket_id, str):
        return False, f"期望获得 ticket_id，实际为 {ticket_id}"

    try:
        delete_request = client.post(
            "/tool-call/auto",
            json={
                "message": f"删除工单 {ticket_id}",
                "session_id": session_id,
            },
        )

        if delete_request.status_code != 200:
            return False, f"删除请求期望状态码 200，实际为 {delete_request.status_code}"

        if delete_request.json().get("decision_type") != "confirmation_required":
            return False, "期望删除请求进入 confirmation_required 状态"

        cancel_request = client.post(
            "/tool-call/auto",
            json={
                "message": "取消删除",
                "session_id": session_id,
            },
        )

        if cancel_request.status_code != 200:
            return False, f"取消请求期望状态码 200，实际为 {cancel_request.status_code}"

        cancel_data = cancel_request.json()

        if cancel_data.get("decision_type") != "confirmation_cancelled":
            return False, (
                "期望取消后返回 confirmation_cancelled，"
                f"实际为 {cancel_data.get('decision_type')}"
            )

        queried_after_cancel = run_tool(
            "query_ticket_status",
            ticket_id=ticket_id,
        )

        if not (queried_after_cancel.data or {}).get("found"):
            return False, "取消删除后工单不应被删除"

        return True, ""
    finally:
        delete_ticket(ticket_id)



def run_auto_with_fake_openai(
    message: str,
    fake_client_class,
):  # 函数：负责 运行 自动 带 模拟 OpenAI 相关逻辑。
    fake_openai_module = types.ModuleType("openai")
    fake_openai_module.OpenAI = fake_client_class

    old_openai_module = sys.modules.get("openai")
    old_env = {
        "TOOL_CALL_PROVIDER": os.environ.get("TOOL_CALL_PROVIDER"),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "OPENAI_MODEL": os.environ.get("OPENAI_MODEL"),
        "OPENAI_TIMEOUT_SECONDS": os.environ.get("OPENAI_TIMEOUT_SECONDS"),
    }

    sys.modules["openai"] = fake_openai_module
    os.environ["TOOL_CALL_PROVIDER"] = "openai"
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["OPENAI_MODEL"] = "test-model"
    os.environ["OPENAI_TIMEOUT_SECONDS"] = "3.5"

    try:
        return client.post(
            "/tool-call/auto",
            json={
                "message": message,
            },
        )
    finally:
        if old_openai_module is None:
            sys.modules.pop("openai", None)
        else:
            sys.modules["openai"] = old_openai_module

        for key, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

def test_tool_call_auto_invalid_provider() -> tuple[bool, str]:  # 测试函数：验证 工具 调用 自动 非法 Provider 场景。
    response = run_auto_with_env(
        message="帮我查询工单 TICKET-20260724-0001 的状态",
        env={
            "TOOL_CALL_PROVIDER": "bad-provider",
        },
    )

    if response.status_code != 200:
        return False, f"期望状态码 200，实际为 {response.status_code}"

    data = response.json()

    if data.get("success"):
        return False, f"期望 success=False，实际为 {data}"

    if data.get("error_type") != "invalid_tool_call_provider":
        return False, (
            "期望 error_type=invalid_tool_call_provider，"
            f"实际为 {data.get('error_type')}"
        )

    workflow_steps = data.get("workflow_steps") or []

    if "plan_tool_call_failed" not in workflow_steps:
        return False, f"期望 workflow_steps 包含 plan_tool_call_failed，实际为 {workflow_steps}"

    return True, ""


def test_tool_call_auto_openai_invalid_json() -> tuple[bool, str]:  # 测试函数：验证 工具 调用 自动 OpenAI 非法 json 场景。
    response = run_auto_with_fake_openai(
        message="帮我查询工单 TICKET-20990101-9999 的状态",
        fake_client_class=FakeInvalidJSONOpenAIClient,
    )

    if response.status_code != 200:
        return False, f"期望状态码 200，实际为 {response.status_code}"

    data = response.json()
    workflow_steps = data.get("workflow_steps") or []

    if "plan_tool_call:openai" not in workflow_steps:
        return False, f"期望 workflow_steps 包含 plan_tool_call:openai，实际为 {workflow_steps}"

    if data.get("success"):
        return False, f"期望 success=False，实际为 {data}"

    if data.get("error_type") != "invalid_json":
        return False, f"期望 error_type=invalid_json，实际为 {data.get('error_type')}"

    return True, ""



def test_tool_call_auto_openai_with_mock_client() -> tuple[bool, str]:  # 测试函数：验证 工具 调用 自动 OpenAI 带 模拟 客户端 场景。
    fake_openai_module = types.ModuleType("openai")
    fake_openai_module.OpenAI = FakeOpenAIToolCallClient

    old_openai_module = sys.modules.get("openai")
    old_env = {
        "TOOL_CALL_PROVIDER": os.environ.get("TOOL_CALL_PROVIDER"),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "OPENAI_MODEL": os.environ.get("OPENAI_MODEL"),
        "OPENAI_TIMEOUT_SECONDS": os.environ.get("OPENAI_TIMEOUT_SECONDS"),
    }

    sys.modules["openai"] = fake_openai_module
    os.environ["TOOL_CALL_PROVIDER"] = "openai"
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["OPENAI_MODEL"] = "test-model"
    os.environ["OPENAI_TIMEOUT_SECONDS"] = "3.5"

    try:
        response = run_auto_with_fake_openai(
            message="帮我查询工单 TICKET-20990101-9999 的状态",
            fake_client_class=FakeOpenAIToolCallClient,
        )
    finally:
        if old_openai_module is None:
            sys.modules.pop("openai", None)
        else:
            sys.modules["openai"] = old_openai_module

        for key, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

    if response.status_code != 200:
        return False, f"期望状态码 200，实际为 {response.status_code}"

    data = response.json()
    workflow_steps = data.get("workflow_steps") or []

    if "plan_tool_call:openai" not in workflow_steps:
        return False, f"期望 workflow_steps 包含 plan_tool_call:openai，实际为 {workflow_steps}"

    if not data.get("success"):
        return False, f"期望 success=True，实际为 {data}"

    if data.get("tool_name") != "query_ticket_status":
        return False, f"期望 tool_name=query_ticket_status，实际为 {data.get('tool_name')}"

    if "TICKET-20990101-9999" not in (data.get("answer") or ""):
        return False, f"期望 answer 包含工单号，实际为 {data.get('answer')}"

    return True, ""


def run_auto_with_env(
    message: str,
    env: dict[str, str],
    session_id: str | None = None,
):  # 函数：负责 运行 自动 带环境变量和可选会话 ID 的请求。
    old_env = {}

    for key, value in env.items():
        old_env[key] = os.environ.get(key)
        os.environ[key] = value

    try:
        return client.post(
            "/tool-call/auto",
            json={
                "message": message,
                "session_id": session_id,
            },
        )
    finally:
        for key, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def test_tool_call_auto_uses_mock_provider_by_default() -> tuple[bool, str]:  # 测试函数：验证 工具 调用 自动 使用 模拟 Provider by 默认 场景。
    response = run_auto_with_env(
        message="帮我查询工单 TICKET-20260724-0001 的状态",
        env={
            "TOOL_CALL_PROVIDER": "",
        },
    )

    if response.status_code != 200:
        return False, f"期望状态码 200，实际为 {response.status_code}"

    data = response.json()
    workflow_steps = data.get("workflow_steps") or []

    if "plan_tool_call:mock" not in workflow_steps:
        return False, f"期望 workflow_steps 包含 plan_tool_call:mock，实际为 {workflow_steps}"

    return True, ""


def test_tool_call_auto_openai_without_api_key() -> tuple[bool, str]:  # 测试函数：验证 工具 调用 自动 OpenAI 无 API key 场景。
    response = run_auto_with_env(
        message="帮我查询工单 TICKET-20260724-0001 的状态",
        env={
            "TOOL_CALL_PROVIDER": "openai",
            "OPENAI_API_KEY": "",
        },
    )

    if response.status_code != 200:
        return False, f"期望状态码 200，实际为 {response.status_code}"

    data = response.json()
    workflow_steps = data.get("workflow_steps") or []

    if "plan_tool_call:openai" not in workflow_steps:
        return False, f"期望 workflow_steps 包含 plan_tool_call:openai，实际为 {workflow_steps}"

    if data.get("decision_type") != "no_tool":
        return False, f"期望无 API key 时 decision_type=no_tool，实际为 {data.get('decision_type')}"

    return True, ""




def test_tool_call_auto_query_ticket() -> tuple[bool, str]:  # 测试函数：验证 工具 调用 自动 查询 工单 场景。
    response = client.post(
        "/tool-call/auto",
        json={
            "message": "帮我查询工单 TICKET-20260724-0001 的状态",
        },
    )

    if response.status_code != 200:
        return False, f"期望状态码 200，实际为 {response.status_code}"

    data = response.json()

    if not data.get("success"):
        return False, f"期望 success=True，实际为 {data}"

    if data.get("tool_name") != "query_ticket_status":
        return False, f"期望调用 query_ticket_status，实际为 {data.get('tool_name')}"

    if "TICKET-20260724-0001" not in (data.get("answer") or ""):
        return False, f"期望 answer 包含工单号，实际为 {data.get('answer')}"

    return True, ""


def test_tool_call_auto_create_ticket() -> tuple[bool, str]:  # 测试函数：验证 工具 调用 自动 创建 工单 场景。
    response = client.post(
        "/tool-call/auto",
        json={
            "message": "创建工单：VPN 登录失败，用户无法连接公司网络",
        },
    )

    if response.status_code != 200:
        return False, f"期望状态码 200，实际为 {response.status_code}"

    data = response.json()

    if not data.get("success"):
        return False, f"期望 success=True，实际为 {data}"

    if data.get("tool_name") != "create_ticket":
        return False, f"期望调用 create_ticket，实际为 {data.get('tool_name')}"

    if "已创建工单" not in (data.get("answer") or ""):
        return False, f"期望返回创建工单提示，实际 answer={data.get('answer')}"

    return True, ""


def test_tool_call_auto_no_tool() -> tuple[bool, str]:  # 测试函数：验证 工具 调用 自动 无 工具 场景。
    response = client.post(
        "/tool-call/auto",
        json={
            "message": "你好",
        },
    )

    if response.status_code != 200:
        return False, f"期望状态码 200，实际为 {response.status_code}"

    data = response.json()

    if not data.get("success"):
        return False, f"期望 success=True，实际为 {data}"

    if data.get("decision_type") != "no_tool":
        return False, f"期望 decision_type=no_tool，实际为 {data.get('decision_type')}"

    if data.get("error_type") is not None:
        return False, f"期望 error_type=None，实际为 {data.get('error_type')}"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("tool_call_auto_uses_mock_provider_by_default", test_tool_call_auto_uses_mock_provider_by_default),
        ("tool_call_auto_openai_without_api_key", test_tool_call_auto_openai_without_api_key),
        ("tool_call_auto_openai_with_mock_client", test_tool_call_auto_openai_with_mock_client),
        ("tool_call_auto_openai_invalid_json", test_tool_call_auto_openai_invalid_json),
        ("tool_call_auto_query_ticket", test_tool_call_auto_query_ticket),
        ("tool_call_auto_create_ticket", test_tool_call_auto_create_ticket),
        ("tool_call_auto_no_tool", test_tool_call_auto_no_tool),
        ("tool_call_auto_invalid_provider", test_tool_call_auto_invalid_provider),
        (
            "tool_call_auto_delete_ticket_after_confirmation",
            test_tool_call_auto_delete_ticket_after_confirmation,
        ),
        (
            "tool_call_auto_cancel_delete_ticket",
            test_tool_call_auto_cancel_delete_ticket,
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
