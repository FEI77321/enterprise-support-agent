"""生产化 Agent 能力聚合回归：Dataset、Rewrite、安全、HITL 与 Trace。"""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    ("run_eval_dataset_schema.py", "Eval dataset schema: Passed 16/16 datasets, 108 cases"),
    ("run_query_rewrite_eval.py", "Controlled query rewrite eval: Passed 8/8"),
    ("run_safety_injection_eval.py", "Prompt injection boundary eval: Passed 8/8"),
    ("run_hitl_contract_eval.py", "Human-in-the-loop contract: Passed 6/6"),
    ("run_trace_trajectory_eval.py", "Trace trajectory eval: Passed 4/4"),
    ("run_authorization_contract_eval.py", "RBAC and approval contract: Passed 6/6"),
    ("run_tool_reliability_eval.py", "Tool reliability contract: Passed 7/7"),
    ("run_agentops_metrics_eval.py", "AgentOps metrics and timeline: Passed 5/5"),
    ("run_memory_contract_eval.py", "Long-term memory contract: Passed 7/7"),
    ("run_bad_case_lifecycle_eval.py", "Bad Case lifecycle and dataset feedback: Passed 10/10"),
    ("run_context_compression_eval.py", "Context compression contract: Passed 8/8"),
    ("run_prompt_registry_eval.py", "Prompt Registry contract: Passed 7/7"),
    ("run_prompt_regression_eval.py", "Prompt regression gate: Passed baseline 26/26, candidate 26/26, release_allowed=true"),
    ("run_bad_case_fixture_replay.py", "Controlled Bad Case fixture replay: Passed 12/12"),
    ("run_answer_quality_eval.py", "Answer quality eval with Judge and Eval Trace: Passed 26/26; manual calibration samples=4"),
    ("run_context_strategy_comparison_eval.py", "Context strategy comparison: Passed 5/5 (full vs fixed window vs rolling summary)"),
    ("run_query_rewrite_gain_eval.py", "Query rewrite gain experiment: Passed 6/6"),
    ("run_agent_performance_baseline.py", "Agent end-to-end performance baseline: Passed 4/4"),
)


def main() -> None:
    child_env = os.environ.copy()
    # Windows consoles may otherwise emit GBK while the aggregator decodes UTF-8.
    # Keep every nested evaluator deterministic locally and in CI.
    child_env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    for script, expected in SCRIPTS:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "eval" / script)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_env,
        )
        if result.returncode != 0 or expected not in result.stdout:
            raise RuntimeError(f"{script} failed:\n{result.stdout}\n{result.stderr}")
        print(result.stdout.strip())
    print(f"Agent production capability suite: Passed {len(SCRIPTS)}/{len(SCRIPTS)}")


if __name__ == "__main__":
    main()
