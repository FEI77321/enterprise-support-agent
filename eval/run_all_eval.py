# 模块职责：总评估入口：按固定顺序调用各项独立评估脚本，汇总每项退出状态，快速确认整个项目的核心能力是否回归。

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = PROJECT_ROOT / "backend" / ".venv" / "Scripts" / "python.exe"


EVAL_SCRIPTS = [
    "eval/run_config_eval.py",
    "eval/run_redis_config_eval.py",
    "eval/run_rate_limit_eval.py",
    "eval/run_llm_retry_eval.py",
    "eval/run_tool_eval.py",
    "eval/run_tool_action_policy_eval.py",
    "eval/run_tool_confirmation_eval.py",
    "eval/run_tool_prompt_eval.py",
    "eval/run_prompt_eval.py",
    "eval/run_tool_call_parser_eval.py",
    "eval/run_tool_call_executor_eval.py",
    "eval/run_tool_call_agent_eval.py",
    "eval/run_tool_call_planner_eval.py",
    "eval/run_tool_call_schema_consistency_eval.py",
    "eval/run_openai_tool_call_planner_eval.py",
    "eval/run_tool_call_api_eval.py",
    "eval/run_tool_call_auto_eval.py",
    "eval/run_llm_quality_eval.py",
    "eval/run_api_smoke_eval.py",
    "eval/run_sse_eval.py",
    "eval/run_api_startup_eval.py",
    "eval/run_manual_eval.py",
    "eval/run_conversation_memory_eval.py",
    "eval/run_tool_call_memory_api_eval.py",
    "eval/run_database_eval.py",
    "eval/run_ticket_repository_eval.py",
    "eval/run_ticket_migration_eval.py",
    "eval/run_retrieval_quality_eval.py",
    "eval/run_chat_irrelevant_eval.py",
    "eval/run_routing_threshold_eval.py",
    "eval/run_rag_golden_eval.py",
    "eval/run_parent_chunk_eval.py",
    "eval/run_rag_answer_completeness_eval.py",
    "eval/run_parent_chunk_source_eval.py",
    "eval/run_parent_chunk_source_eval.py",
    "eval/run_langgraph_parity_eval.py",
    "eval/run_parent_context_structure_eval.py",
    "eval/run_answer_quality_auto_eval.py",
    "eval/run_langgraph_parity_eval.py",
    "eval/run_api_contract_eval.py",
    "eval/run_mcp_server_eval.py",
]


def run_eval(script: str) -> bool:  # 函数：负责 运行 评估 相关逻辑。
    print("=" * 60)
    print(f"Running {script}")
    print("=" * 60)

    result = subprocess.run(
        [str(PYTHON), script],
        cwd=PROJECT_ROOT,
        text=True,
    )

    return result.returncode == 0


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    passed = 0

    for script in EVAL_SCRIPTS:
        ok = run_eval(script)

        if ok:
            passed += 1

    print()
    print("=" * 60)
    print(f"Eval suites passed: {passed}/{len(EVAL_SCRIPTS)}")
    print("=" * 60)

    if passed != len(EVAL_SCRIPTS):
        sys.exit(1)


if __name__ == "__main__":
    main()
