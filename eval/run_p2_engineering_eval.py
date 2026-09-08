# 模块职责：P2 工程化聚合评估：在离线、可复现配置下验证追踪、Redis 配置、限流、重试、SSE 和 Agent 回归。

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = PROJECT_ROOT / "backend" / ".venv" / "Scripts" / "python.exe"

P2_EVAL_SCRIPTS = [
    "eval/run_redis_config_eval.py",
    "eval/run_rate_limit_eval.py",
    "eval/run_llm_retry_eval.py",
    "eval/run_api_smoke_eval.py",
    "eval/run_sse_eval.py",
    "eval/run_langgraph_parity_eval.py",
]


def run_eval(script: str) -> bool:
    print("=" * 60)
    print(f"Running {script}")
    print("=" * 60)

    environment = os.environ.copy()
    environment.update(
        {
            "ENABLE_LLM_ANSWER": "false",
            "LLM_PROVIDER": "stub",
            "TOOL_CALL_PROVIDER": "mock",
        }
    )
    result = subprocess.run(
        [str(PYTHON), script],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
    )
    return result.returncode == 0


def main() -> None:
    passed = sum(run_eval(script) for script in P2_EVAL_SCRIPTS)
    print()
    print("=" * 60)
    print(f"P2 engineering eval passed: {passed}/{len(P2_EVAL_SCRIPTS)}")
    print("=" * 60)
    if passed != len(P2_EVAL_SCRIPTS):
        sys.exit(1)


if __name__ == "__main__":
    main()
