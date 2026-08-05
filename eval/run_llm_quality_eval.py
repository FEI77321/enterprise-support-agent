# 模块职责：LLM 质量与降级评估：验证 Stub、OpenAI 缺少 Key、模拟 OpenAI 成功返回和来源引用等场景，确保回答链路可控且可测试。

import os
import sys

import types

from eval_path import setup_backend_path

setup_backend_path()

import app.agent as agent_module
from app.agent import handle_message
from app.llm_client import (
    LLMAnswerResult,
    generate_answer_result,
    generate_openai_answer,
)


def run_with_env(message: str, env: dict[str, str]):  # 函数：负责 运行 带 环境变量 相关逻辑。
    old_env = {}

    for key, value in env.items():
        old_env[key] = os.environ.get(key)
        os.environ[key] = value

    try:
        return handle_message(message)
    finally:
        for key, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

def run_with_fake_llm_answer(answer: str):  # 函数：临时替换 LLM 返回内容，并执行一次启用 LLM 的 VPN 问答。
    old_generate_answer_result = agent_module.generate_answer_result

    def fake_generate_answer_result(prompt: str) -> LLMAnswerResult:  # 函数：模拟固定文本的 LLM 回答。
        return LLMAnswerResult(
            answer=answer,
            success=True,
            provider="stub",
        )

    agent_module.generate_answer_result = fake_generate_answer_result

    try:
        return run_with_env(
            message="VPN 720 错误怎么办",
            env={
                "ENABLE_LLM_ANSWER": "true",
                "LLM_PROVIDER": "stub",
            },
        )
    finally:
        agent_module.generate_answer_result = old_generate_answer_result

def test_llm_mismatched_file_and_chunk_falls_back_to_rule_answer() -> tuple[bool, str]:  # 测试函数：验证 File 与 Chunk ID 不匹配时，Agent 会降级到规则回答。
    fake_answer = (
        "请先重启 VPN 客户端，并检查虚拟网卡驱动状态。\n\n"
        "参考来源：\n"
        "- File: leave_policy.md, Chunk ID: vpn_guide.md::chunk-6"
    )

    response = run_with_fake_llm_answer(fake_answer)

    if response.answer == fake_answer:
        return False, "LLM 的 File 与 Chunk ID 不匹配，但 Agent 仍采用了该回答"

    if "llm_invalid_citation_fallback" not in response.workflow_steps:
        return False, (
            "期望 workflow_steps 包含 llm_invalid_citation_fallback，"
            f"实际为 {response.workflow_steps}"
        )

    return True, ""



def check_common_llm_answer(response) -> tuple[bool, str]:  # 函数：负责 check 通用 大模型 回答 相关逻辑。
    if response.type != "answer":
        return False, f"期望 response.type=answer，实际为 {response.type}"

    if not response.answer:
        return False, "期望返回 answer，但实际 answer 为空"

    if not response.sources:
        return False, "期望保留知识库 sources，但实际 sources 为空"

    source_files = {source.file for source in response.sources}

    if "vpn_guide.md" not in source_files:
        return False, f"期望 sources 包含 vpn_guide.md，实际为 {sorted(source_files)}"

    expected_steps = ["rule_answer", "llm_answer", "knowledge_answer"]
    missing_steps = [
        step
        for step in expected_steps
        if step not in response.workflow_steps
    ]

    if missing_steps:
        return False, (
            f"期望 workflow_steps 包含 {missing_steps}，"
            f"实际为 {response.workflow_steps}"
        )

    if response.ticket is not None:
        return False, f"期望不创建工单，但实际 ticket={response.ticket}"

    return True, ""

def test_openai_missing_api_key_reason() -> tuple[bool, str]:  # 测试函数：验证 OpenAI 缺少 API key reason 场景。
    old_env = {
        "LLM_PROVIDER": os.environ.get("LLM_PROVIDER"),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
    }

    os.environ["LLM_PROVIDER"] = "openai"
    os.environ["OPENAI_API_KEY"] = ""

    try:
        result = generate_answer_result("test prompt")
    finally:
        for key, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

    if result.success:
        return False, "期望缺少 API Key 时 success=False"

    if result.provider != "openai":
        return False, f"期望 provider=openai，实际为 {result.provider}"

    if result.error_reason != "api_key_missing":
        return False, f"期望 error_reason=api_key_missing，实际为 {result.error_reason}"

    if "暂不可用" not in result.answer:
        return False, f"期望 fallback answer 包含 暂不可用，实际为 {result.answer}"

    return True, ""




def test_llm_stub_answer() -> tuple[bool, str]:  # 测试函数：验证 大模型 模拟回答 回答 场景。
    response = run_with_env(
        message="VPN 720 错误怎么办",
        env={
            "ENABLE_LLM_ANSWER": "true",
            "LLM_PROVIDER": "stub",
        },
    )

    return check_common_llm_answer(response)


def test_openai_provider_without_api_key() -> tuple[bool, str]:  # 测试函数：验证 OpenAI Provider 无 API key 场景。
    response = run_with_env(
        message="VPN 720 错误怎么办",
        env={
            "ENABLE_LLM_ANSWER": "true",
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": "",
        },
    )

    ok, reason = check_common_llm_answer(response)
    if not ok:
        return ok, reason

    if "暂不可用"  in response.answer:
        return False, f"期望返回大模型不可用提示，实际 answer={response.answer}"

    if "llm_fallback_to_rule_answer" not in response.workflow_steps:
        return False, (
            "期望 workflow_steps 包含 llm_fallback_to_rule_answer，"
            f"实际为 {response.workflow_steps}"
        )

    return True, ""


def test_openai_provider_with_mock_client() -> tuple[bool, str]:  # 测试函数：验证 OpenAI Provider 带 模拟 客户端 场景。
    captured = {}

    class FakeResponses:  # 类：模拟 OpenAI 客户端中的 responses 子对象。
        def create(self, model: str, input: str):  # 函数：模拟或执行客户端的 create 调用。
            captured["model"] = model
            captured["input"] = input

            class FakeResponse:  # 类：模拟 OpenAI Responses API 返回的 output_text 对象。
                output_text = "mock openai answer"

            return FakeResponse()

    class FakeOpenAI:  # 类：模拟 OpenAI 客户端，供离线测试注入使用。
        def __init__(self, api_key: str, timeout: float):  # 函数：初始化当前对象所需的状态或依赖。
            captured["api_key"] = api_key
            captured["timeout"] = timeout
            self.responses = FakeResponses()

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

    try:
        answer = generate_openai_answer("test prompt")
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

    if answer != "mock openai answer":
        return False, f"期望返回 mock openai answer，实际 answer={answer}"

    expected = {
        "api_key": "test-key",
        "timeout": 3.5,
        "model": "test-model",
        "input": "test prompt",
    }

    for key, value in expected.items():
        if captured.get(key) != value:
            return False, f"期望 captured[{key}]={value}，实际为 {captured.get(key)}"

    return True, ""


def test_llm_answer_contains_source_citation() -> tuple[bool, str]:  # 测试函数：验证 大模型 回答 包含 来源 引用 场景。
    old_generate_answer_result = agent_module.generate_answer_result
    def fake_generate_answer_result(prompt: str) -> LLMAnswerResult:  # 函数：负责 模拟 生成 回答 结果 相关逻辑。
        from app.llm_client import LLMAnswerResult
        return LLMAnswerResult(
            answer=(
                "VPN 720 错误通常和虚拟网卡驱动或 VPN 客户端配置异常有关。"
                "建议先重启 VPN 客户端，并检查虚拟网卡驱动状态。\n\n"
                "参考来源：\n"
                "- File: vpn_guide.md, Chunk ID: vpn_guide.md::chunk-6"
            ),
            success=True,
            provider="stub",
        )
    agent_module.generate_answer_result = fake_generate_answer_result

    try:
        response = run_with_env(
            message="VPN 720 错误怎么办",
            env={
                "ENABLE_LLM_ANSWER": "true",
                "LLM_PROVIDER": "stub",
            },
        )
    finally:
        agent_module.generate_answer_result = old_generate_answer_result

    ok, reason = check_common_llm_answer(response)
    if not ok:
        return ok, reason

    cited_source = next(
        (
            source
            for source in response.sources
            if source.file == "vpn_guide.md"
        ),
        None,
    )

    if cited_source is None:
        return False, f"期望 response.sources 包含 vpn_guide.md，实际为 {response.sources}"


    required_texts = [
        "参考来源",
        "File",
        "Chunk ID",
        cited_source.file,
        cited_source.chunk_id,
    ]

    for text in required_texts:
        if text not in response.answer:
            return False, f"期望 LLM answer 包含 {text}，实际 answer={response.answer}"

    return True, ""

def test_llm_invalid_citation_falls_back_to_rule_answer() -> tuple[bool, str]:  # 测试函数：验证 LLM 引用不存在的知识块时，Agent 会降级到规则回答。
    old_generate_answer_result = agent_module.generate_answer_result

    def fake_generate_answer_result(prompt: str) -> LLMAnswerResult:  # 函数：模拟返回包含错误来源引用的 LLM 回答。
        return LLMAnswerResult(
            answer=(
                "请重启 VPN 客户端。\n\n"
                "参考来源：\n"
                "- File: vpn_guide.md, Chunk ID: vpn_guide.md::chunk-999"
            ),
            success=True,
            provider="stub",
        )

    agent_module.generate_answer_result = fake_generate_answer_result

    try:
        response = run_with_env(
            message="VPN 720 错误怎么办",
            env={
                "ENABLE_LLM_ANSWER": "true",
                "LLM_PROVIDER": "stub",
            },
        )
    finally:
        agent_module.generate_answer_result = old_generate_answer_result

    if "vpn_guide.md::chunk-999" in response.answer:
        return False, "LLM 引用了不存在的 chunk，但 Agent 未降级"

    if "llm_invalid_citation_fallback" not in response.workflow_steps:
        return False, (
            "期望 workflow_steps 包含 llm_invalid_citation_fallback，"
            f"实际为 {response.workflow_steps}"
        )
    if not response.sources:
        return False, "降级到规则回答后，期望仍保留 sources"

    source = response.sources[0]
    expected_reference = (
        f"File: {source.file}, Chunk ID: {source.chunk_id}"
    )

    if expected_reference not in response.answer:
        return False, (
            "规则回答降级后应保留正确引用，"
            f"期望包含 {expected_reference}，实际 answer={response.answer}"
        )

    return True, ""


def test_llm_mixed_citations_fall_back_to_rule_answer() -> tuple[bool, str]:  # 测试函数：验证 LLM 混入任意错误引用时，Agent 仍会降级到规则回答。
    old_generate_answer_result = agent_module.generate_answer_result

    def fake_generate_answer_result(prompt: str) -> LLMAnswerResult:  # 函数：模拟同时包含正确与错误来源引用的 LLM 回答。
        return LLMAnswerResult(
            answer=(
                "请重启 VPN 客户端，并检查虚拟网卡驱动状态。\n\n"
                "参考来源：\n"
                "- File: vpn_guide.md, Chunk ID: vpn_guide.md::chunk-6\n"
                "- File: vpn_guide.md, Chunk ID: vpn_guide.md::chunk-999"
            ),
            success=True,
            provider="stub",
        )

    agent_module.generate_answer_result = fake_generate_answer_result

    try:
        response = run_with_env(
            message="VPN 720 错误怎么办",
            env={
                "ENABLE_LLM_ANSWER": "true",
                "LLM_PROVIDER": "stub",
            },
        )
    finally:
        agent_module.generate_answer_result = old_generate_answer_result

    if "vpn_guide.md::chunk-999" in response.answer:
        return False, "LLM 混入错误 chunk，但 Agent 仍采用了该回答"

    if "llm_invalid_citation_fallback" not in response.workflow_steps:
        return False, (
            "期望 workflow_steps 包含 llm_invalid_citation_fallback，"
            f"实际为 {response.workflow_steps}"
        )

    return True, ""

def test_llm_missing_citation_falls_back_to_rule_answer() -> tuple[bool, str]:  # 测试函数：验证 LLM 未提供任何 Chunk ID 时，Agent 会降级到规则回答。
    old_generate_answer_result = agent_module.generate_answer_result

    def fake_generate_answer_result(prompt: str) -> LLMAnswerResult:  # 函数：模拟未包含来源引用的 LLM 回答。
        return LLMAnswerResult(
            answer="请先重启 VPN 客户端，并检查虚拟网卡驱动状态。",
            success=True,
            provider="stub",
        )

    agent_module.generate_answer_result = fake_generate_answer_result

    try:
        response = run_with_env(
            message="VPN 720 错误怎么办",
            env={
                "ENABLE_LLM_ANSWER": "true",
                "LLM_PROVIDER": "stub",
            },
        )
    finally:
        agent_module.generate_answer_result = old_generate_answer_result

    if response.answer == "请先重启 VPN 客户端，并检查虚拟网卡驱动状态。":
        return False, "LLM 未提供 Chunk ID，但 Agent 仍采用了该回答"

    if "llm_invalid_citation_fallback" not in response.workflow_steps:
        return False, (
            "期望 workflow_steps 包含 llm_invalid_citation_fallback，"
            f"实际为 {response.workflow_steps}"
        )

    return True, ""




def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("llm_stub_answer", test_llm_stub_answer),
        ("openai_provider_without_api_key", test_openai_provider_without_api_key),
        ("openai_provider_with_mock_client", test_openai_provider_with_mock_client),
        ("llm_answer_contains_source_citation", test_llm_answer_contains_source_citation),
        ("openai_missing_api_key_reason", test_openai_missing_api_key_reason),
        ("llm_invalid_citation_falls_back_to_rule_answer", test_llm_invalid_citation_falls_back_to_rule_answer),
        (
            "llm_mixed_citations_fall_back_to_rule_answer",
            test_llm_mixed_citations_fall_back_to_rule_answer,
        ),
        (
            "llm_missing_citation_falls_back_to_rule_answer",
            test_llm_missing_citation_falls_back_to_rule_answer,
        ),
        (
            "llm_mismatched_file_and_chunk_falls_back_to_rule_answer",
            test_llm_mismatched_file_and_chunk_falls_back_to_rule_answer,
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
