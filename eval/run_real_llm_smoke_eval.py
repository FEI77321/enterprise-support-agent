# 模块职责：真实 LLM 冒烟评测：显式开启后调用 DeepSeek，验证真实模型、引用校验和 Agent 回答链路能够协同工作。

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from eval_path import setup_backend_path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
setup_backend_path()

from app.agent import handle_message


def test_deepseek_knowledge_answer() -> tuple[bool, str]:  # 测试函数：验证 DeepSeek 能基于 VPN 知识来源生成并通过引用校验的回答。
    response = handle_message("VPN 720 错误怎么办")

    if response.type != "answer":
        return False, f"期望 response.type=answer，实际为 {response.type}"

    if not response.answer:
        return False, "期望 DeepSeek 返回非空回答"

    if not response.sources:
        return False, "期望保留知识库 sources"

    if "llm_answer" not in response.workflow_steps:
        return False, (
            "期望 workflow_steps 包含 llm_answer，"
            f"实际为 {response.workflow_steps}"
        )

    fallback_steps = {
        "llm_fallback_to_rule_answer",
        "llm_invalid_citation_fallback",
    }
    used_fallback_steps = fallback_steps.intersection(
        response.workflow_steps
    )

    if used_fallback_steps:
        return False, (
            "真实 LLM 不应在本次冒烟评测中降级，"
            f"实际触发了 {sorted(used_fallback_steps)}"
        )

    valid_references = {
        f"File: {source.file}, Chunk ID: {source.chunk_id}"
        for source in response.sources
        if source.chunk_id
    }

    if not any(
        reference in response.answer
        for reference in valid_references
    ):
        return False, (
            "LLM 回答中未找到当前检索来源的正确引用，"
            f"允许引用为 {sorted(valid_references)}"
        )

    return True, ""


def main() -> None:  # 函数：在显式允许后执行真实 DeepSeek 冒烟评测。
    if os.getenv("RUN_REAL_LLM_EVAL", "").lower() != "true":
        print(
            "SKIP real LLM smoke eval: "
            "请设置 RUN_REAL_LLM_EVAL=true 后再运行。"
        )
        return

    tests = [
        test_deepseek_knowledge_answer,
    ]

    passed_count = 0

    for test in tests:
        passed, reason = test()

        if passed:
            print(f"PASS {test.__name__}")
            passed_count += 1
        else:
            print(f"FAIL {test.__name__}: {reason}")

    print(
        f"\nReal LLM smoke eval: "
        f"Passed {passed_count}/{len(tests)}"
    )

    if passed_count != len(tests):
        sys.exit(1)


if __name__ == "__main__":
    main()