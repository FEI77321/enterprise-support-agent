"""离线端到端性能基线：RAG、工具查询、审批准备与长会话 Context；明确不包含真实 LLM/网络。"""

from __future__ import annotations

import os
from pathlib import Path
from statistics import quantiles
from tempfile import TemporaryDirectory
from time import perf_counter

from eval_path import setup_backend_path

setup_backend_path()

from app.agent import handle_message
from app.conversation_memory import add_turn, clear_memory
from app.eval_trace_store import complete_eval_run, create_eval_run, get_eval_run, record_eval_case
from app.models import ChatResponse
from app.tool_call_agent import handle_tool_call_demo_auto
from app.trace_store import get_trace, persist_trace


ITERATIONS = 8


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    index = max(0, int(len(ordered) * ratio + 0.9999) - 1)
    return round(ordered[index], 3)


def main() -> None:
    with TemporaryDirectory() as directory:
        trace_database = Path(directory) / "performance-trace.db"
        eval_database = Path(directory) / "performance-eval.db"
        old_trace_db = os.environ.get("TRACE_DATABASE_PATH")
        old_trace_enabled = os.environ.get("TRACE_PERSISTENCE_ENABLED")
        old_llm = os.environ.get("ENABLE_LLM_ANSWER")
        old_tool = os.environ.get("TOOL_CALL_PROVIDER")
        os.environ.update({
            "TRACE_DATABASE_PATH": str(trace_database), "TRACE_PERSISTENCE_ENABLED": "true",
            "ENABLE_LLM_ANSWER": "false", "TOOL_CALL_PROVIDER": "mock",
        })
        session_id = "performance-long-session"
        try:
            clear_memory(session_id)
            for index in range(10):
                add_turn(session_id, "user", f"第 {index} 轮：" + "VPN 排障背景。" * 40)
                add_turn(session_id, "assistant", f"第 {index} 轮：" + "已给出排障建议。" * 40)
            run_id = create_eval_run(
                suite_name="agent_performance_baseline", dataset_version="performance-baseline-v1",
                judge_provider="not_applicable", database_path=eval_database,
            )
            scenarios = {
                "rag_stub": lambda request_id: handle_message("VPN 720 错误怎么办", request_id=request_id),
                "tool_query": lambda request_id: handle_message("查询 TICKET-20260916-0001", request_id=request_id),
                "long_context": lambda request_id: handle_message("前面那个 VPN 问题现在怎么处理", request_id=request_id, session_id=session_id),
            }
            samples: dict[str, list[float]] = {name: [] for name in (*scenarios, "approval_prepare")}
            trace_complete = True
            for scenario, invoke in scenarios.items():
                for index in range(ITERATIONS):
                    request_id = f"perf-{scenario}-{index}"
                    started = perf_counter()
                    response = invoke(request_id)
                    elapsed = (perf_counter() - started) * 1000
                    samples[scenario].append(elapsed)
                    trace = get_trace(request_id, trace_database)
                    trace_complete = trace_complete and trace is not None and any(span["span_type"] == "timing" for span in trace["spans"])
                    record_eval_case(
                        eval_run_id=run_id, case_id=f"{scenario}-{index}", prompt_version=str(response.prompt.get("version", "unresolved")),
                        request_id=request_id, status="passed", deterministic={"elapsed_ms": round(elapsed, 3), "timing": response.timing},
                        judge={"provider": "not_applicable"}, human={"status": "not_required"},
                        trace={"trace_id": response.trace_id, "scenario": scenario}, database_path=eval_database,
                    )
            for index in range(ITERATIONS):
                request_id = f"perf-approval-{index}"
                started = perf_counter()
                tool_response = handle_tool_call_demo_auto("删除工单 TICKET-20260916-0001", session_id=f"approval-{index}")
                elapsed = (perf_counter() - started) * 1000
                samples["approval_prepare"].append(elapsed)
                response = ChatResponse(
                    request_id=request_id, type="clarify", answer=tool_response.answer,
                    workflow_steps=tool_response.workflow_steps, harness_trace=tool_response.harness_trace,
                    context=tool_response.context, prompt={"version": "tool-planner-mock", "channel": "offline"},
                    timing={"total_ms": round(elapsed, 3), "approval_prepare_ms": round(elapsed, 3)},
                )
                persist_trace(response, original_message="删除工单 TICKET-20260916-0001", effective_query="删除工单 TICKET-20260916-0001", engine="tool_call", database_path=trace_database)
                trace = get_trace(request_id, trace_database)
                trace_complete = trace_complete and trace is not None and any(span["span_name"] == "timing:approval_prepare_ms" for span in trace["spans"])
                record_eval_case(
                    eval_run_id=run_id, case_id=f"approval_prepare-{index}", prompt_version="tool-planner-mock", request_id=request_id, status="passed",
                    deterministic={"elapsed_ms": round(elapsed, 3), "confirmation_required": tool_response.requires_confirmation},
                    judge={"provider": "not_applicable"}, human={"status": "not_required"},
                    trace={"trace_id": request_id, "scenario": "approval_prepare"}, database_path=eval_database,
                )
            summary = {
                "scope": "offline local baseline; LLM generation, remote API, embedding service, network transport and human approval wait are excluded",
                "iterations_per_scenario": ITERATIONS,
                "scenarios": {name: {"p50_ms": percentile(values, 0.5), "p95_ms": percentile(values, 0.95)} for name, values in samples.items()},
                "trace_complete": trace_complete,
            }
            complete_eval_run(run_id, status="passed" if trace_complete else "failed", summary=summary, database_path=eval_database)
            stored = get_eval_run(run_id, eval_database)
            assert stored is not None and len(stored["cases"]) == ITERATIONS * 4 and trace_complete
        finally:
            clear_memory(session_id)
            for key, value in (("TRACE_DATABASE_PATH", old_trace_db), ("TRACE_PERSISTENCE_ENABLED", old_trace_enabled), ("ENABLE_LLM_ANSWER", old_llm), ("TOOL_CALL_PROVIDER", old_tool)):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    print(f"Agent end-to-end performance baseline: Passed 4/4; {summary}")


if __name__ == "__main__":
    main()
