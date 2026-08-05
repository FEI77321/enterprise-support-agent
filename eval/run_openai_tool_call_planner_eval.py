# 模块职责：OpenAI 工具规划器评估：通过替换 openai 模块为 Fake 客户端，验证无 Key 降级和请求参数构造，无需真实网络调用。

import os
import sys
import types

from eval_path import setup_backend_path


setup_backend_path()

from app.tool_call_planner import plan_tool_call_with_openai


class FakeResponse:  # 类：模拟 OpenAI Responses API 返回的 output_text 对象。
    output_text = (
        '{"tool_name": "query_ticket_status", '
        '"arguments": {"ticket_id": "TICKET-20260724-0001"}}'
    )


class FakeResponses:  # 类：模拟 OpenAI 客户端中的 responses 子对象。
    def __init__(self, captured: dict):  # 函数：初始化当前对象所需的状态或依赖。
        self.captured = captured

    def create(self, model: str, input: str):  # 函数：模拟或执行客户端的 create 调用。
        self.captured["model"] = model
        self.captured["input"] = input
        return FakeResponse()


class FakeOpenAI:  # 类：模拟 OpenAI 客户端，供离线测试注入使用。
    def __init__(self, api_key: str, timeout: float):  # 函数：初始化当前对象所需的状态或依赖。
        captured["api_key"] = api_key
        captured["timeout"] = timeout
        self.responses = FakeResponses(captured)


captured = {}


def test_openai_tool_call_planner_without_api_key() -> tuple[bool, str]:  # 测试函数：验证 OpenAI 工具 调用 规划器 无 API key 场景。
    old_api_key = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = ""

    try:
        llm_output = plan_tool_call_with_openai("帮我查工单 TICKET-20260724-0001")
    finally:
        if old_api_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = old_api_key

    expected = '{"tool_name": null, "arguments": {}}'

    if llm_output != expected:
        return False, f"期望无 API key 时不调用工具，实际为 {llm_output}"

    return True, ""


def test_openai_tool_call_planner_with_mock_client() -> tuple[bool, str]:  # 测试函数：验证 OpenAI 工具 调用 规划器 带 模拟 客户端 场景。
    fake_openai_module = types.ModuleType("openai")
    fake_openai_module.OpenAI = FakeOpenAI

    old_openai_module = sys.modules.get("openai")
    old_env = {
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "OPENAI_MODEL": os.environ.get("OPENAI_MODEL"),
        "OPENAI_TIMEOUT_SECONDS": os.environ.get("OPENAI_TIMEOUT_SECONDS"),
    }

    sys.modules["openai"] = fake_openai_module
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["OPENAI_MODEL"] = "test-model"
    os.environ["OPENAI_TIMEOUT_SECONDS"] = "3.5"

    captured.clear()

    try:
        llm_output = plan_tool_call_with_openai(
            "帮我查询工单 TICKET-20260724-0001 的状态"
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

    expected_output = (
        '{"tool_name": "query_ticket_status", '
        '"arguments": {"ticket_id": "TICKET-20260724-0001"}}'
    )

    if llm_output != expected_output:
        return False, f"期望返回 mock tool call JSON，实际为 {llm_output}"

    if captured.get("api_key") != "test-key":
        return False, f"期望 api_key=test-key，实际为 {captured.get('api_key')}"

    if captured.get("timeout") != 3.5:
        return False, f"期望 timeout=3.5，实际为 {captured.get('timeout')}"

    if captured.get("model") != "test-model":
        return False, f"期望 model=test-model，实际为 {captured.get('model')}"

    prompt = captured.get("input", "")

    if "query_ticket_status" not in prompt:
        return False, "期望 prompt 包含 query_ticket_status 工具说明"

    if "TICKET-20260724-0001" not in prompt:
        return False, "期望 prompt 包含用户问题中的工单号"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("openai_tool_call_planner_without_api_key", test_openai_tool_call_planner_without_api_key),
        ("openai_tool_call_planner_with_mock_client", test_openai_tool_call_planner_with_mock_client),
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
