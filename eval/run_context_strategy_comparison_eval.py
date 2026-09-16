"""长会话 Context 三策略对比：全量历史、固定窗口、滚动摘要的事实保留与预算证据。"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from eval_path import setup_backend_path

setup_backend_path()

from app.context_compression import compose_context
from app.conversation_memory import add_turn
from app.eval_trace_store import complete_eval_run, create_eval_run, get_eval_run, record_eval_case


FACTS = ("TICKET-20260916-0001", "VPN 691", "MacBook")


def main() -> None:
    with TemporaryDirectory() as directory:
        database = Path(directory) / "context-strategy.db"
        session_id = "context-strategy-comparison"
        add_turn(session_id, "user", "我的 MacBook 访问 VPN 报 VPN 691，工单 TICKET-20260916-0001 已创建，请记住这些信息。", database)
        add_turn(session_id, "assistant", "已记录工单与错误码，下一步检查账号与网络配置。", database)
        for index in range(1, 10):
            add_turn(session_id, "user", f"第 {index} 轮补充：" + "请描述一个不会影响早期工单事实的普通排障背景。" * 12, database)
            add_turn(session_id, "assistant", f"第 {index} 轮处理：" + "已给出可执行但不改变早期工单事实的建议。" * 12, database)

        run_id = create_eval_run(
            suite_name="context_strategy_comparison",
            dataset_version="context-strategy-v1",
            judge_provider="deterministic",
            database_path=database,
        )
        results: dict[str, dict] = {}
        for strategy in ("full_history", "fixed_window", "rolling_summary"):
            package = compose_context(
                session_id=session_id,
                sources=[], active_memories=[], database_path=database, strategy=strategy,
            )
            text = package.history_text
            retained = all(fact in text for fact in FACTS)
            result = {
                "strategy": strategy,
                "fact_retained": retained,
                "task_completion_proxy": retained,
                "original_estimated_tokens": package.decision["original_estimated_tokens"],
                "emitted_estimated_tokens": package.decision["emitted_estimated_tokens"],
                "estimated_reduction_ratio": package.decision["estimated_reduction_ratio"],
                "within_budget": package.decision["emitted_estimated_tokens"] <= package.decision["total_budget_tokens"],
            }
            results[strategy] = result
            record_eval_case(
                eval_run_id=run_id, case_id=f"context-long-session-001:{strategy}", prompt_version="support-agent-v2.0",
                status="passed" if retained else "failed", deterministic=result,
                judge={"provider": "deterministic", "answer_quality_proxy": "fact_retention"},
                human={"status": "manual_review_pending"}, trace={"context": package.decision},
                database_path=database,
            )
        checks = [
            results["full_history"]["fact_retained"],
            not results["fixed_window"]["fact_retained"],
            results["rolling_summary"]["fact_retained"],
            results["rolling_summary"]["within_budget"],
            results["rolling_summary"]["emitted_estimated_tokens"] < results["full_history"]["emitted_estimated_tokens"],
        ]
        summary = {"strategies": results, "checks": len(checks), "passed": sum(checks)}
        complete_eval_run(run_id, status="passed" if all(checks) else "failed", summary=summary, database_path=database)
        stored = get_eval_run(run_id, database)
        assert stored is not None and len(stored["cases"]) == 3
        if not all(checks):
            raise SystemExit(f"Context strategy comparison failed: {results}")
    print("Context strategy comparison: Passed 5/5 (full vs fixed window vs rolling summary)")


if __name__ == "__main__":
    main()
