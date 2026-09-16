"""生成可直接用于简历与面试复盘的离线证据摘要。

该入口只调用项目已有的离线回归；它不访问外部模型、不启动 API 服务，
也不将 RAG 2.0 的 isolated synthetic 结果伪装成主 Agent 的线上指标。

运行方式（项目根目录）：
    .\\backend\\.venv\\Scripts\\python.exe .\\eval\\run_resume_evidence_eval.py
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns

from run_synthetic_ingestion_evidence_coverage_eval import (
    CORPUS_ROOT,
    ingest_synthetic_corpus,
    load_json,
)
from run_synthetic_lexical_retrieval_eval import (
    DOCUMENT_AWARE_LEXICAL,
    GOLDEN_CASES_PATH,
    MANIFEST_PATH,
    build_active_child_chunks,
    retrieve,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = PROJECT_ROOT / "eval"
LATENCY_ROUNDS = 20


@dataclass(frozen=True)
class Suite:
    """一组可独立复现的离线验证。"""

    label: str
    script_name: str
    expected_output: str


SUITES = (
    Suite(
        "主链路 RAG 黄金集",
        "run_rag_golden_eval.py",
        "RAG golden eval: Passed 31/31",
    ),
    Suite(
        "文档摄入契约",
        "run_knowledge_ingestion_contract_eval.py",
        "Knowledge ingestion contract: Passed 5/5",
    ),
    Suite(
        "来源回链契约",
        "run_knowledge_source_reference_contract_eval.py",
        "Knowledge source reference contract: Passed 3/3",
    ),
    Suite(
        "检索可见性契约",
        "run_ingested_knowledge_retrieval_contract_eval.py",
        "Ingested knowledge retrieval contract: Passed 3/3",
    ),
    Suite(
        "Feature Flag 契约",
        "run_ingested_knowledge_feature_flag_contract_eval.py",
        "Ingested knowledge feature flag contract: Passed 2/2",
    ),
    Suite(
        "Agent Harness 契约",
        "run_agent_harness_contract_eval.py",
        "Agent Harness contract: Passed 8/8",
    ),
    Suite(
        "MCP stdio 协议回归",
        "run_mcp_server_eval.py",
        "MCP stdio protocol contract: Passed 5/5",
    ),
)


def percentile(values: list[float], ratio: float) -> float:
    """返回 nearest-rank 百分位，避免引入额外统计依赖。"""

    if not values:
        raise ValueError("percentile requires at least one value")

    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * ratio) - 1)
    return ordered[index]


def run_suite(suite: Suite) -> None:
    """执行一组既有离线测试并验证其稳定的摘要输出。"""

    result = subprocess.run(
        [sys.executable, str(EVAL_ROOT / suite.script_name)],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{suite.label} failed with exit code {result.returncode}:\n"
            f"{result.stdout}"
        )

    if suite.expected_output not in result.stdout:
        raise AssertionError(
            f"{suite.label} completed but its expected evidence line was missing:\n"
            f"expected={suite.expected_output}\n"
            f"actual={result.stdout}"
        )

    print(f"PASS {suite.label}: {suite.expected_output}")


def sample_isolated_retrieval_latency() -> dict[str, float | int]:
    """采样纯检索函数时间，不包含解析、摄入、索引构建或模型调用。"""

    manifest = load_json(MANIFEST_PATH)
    golden_suite = load_json(GOLDEN_CASES_PATH)
    ingested_documents = ingest_synthetic_corpus(manifest)
    active_child_chunks = build_active_child_chunks(
        manifest=manifest,
        ingested_documents=ingested_documents,
    )
    answer_cases = [
        case
        for case in golden_suite["cases"]
        if case["expected_action"] == "answer"
    ]

    # 预热只用于排除首次 Python 路径与数据结构初始化的扰动，不计入样本。
    for case in answer_cases:
        retrieve(
            query=case["query"],
            active_child_chunks=active_child_chunks,
            strategy=DOCUMENT_AWARE_LEXICAL,
        )

    samples_ms: list[float] = []
    for _ in range(LATENCY_ROUNDS):
        for case in answer_cases:
            started = perf_counter_ns()
            results = retrieve(
                query=case["query"],
                active_child_chunks=active_child_chunks,
                strategy=DOCUMENT_AWARE_LEXICAL,
            )
            elapsed_ms = (perf_counter_ns() - started) / 1_000_000
            if len(results) > 3:
                raise AssertionError("top_k=3 returned more than three results")
            samples_ms.append(elapsed_ms)

    return {
        "document_count": len(manifest["documents"]),
        "active_child_chunk_count": len(active_child_chunks),
        "answer_case_count": len(answer_cases),
        "sample_count": len(samples_ms),
        "p50_ms": percentile(samples_ms, 0.50),
        "p95_ms": percentile(samples_ms, 0.95),
        "max_ms": max(samples_ms),
    }


def main() -> None:
    print("Resume evidence evaluation")
    print("Scope: offline, reproducible checks; no external LLM/API calls.")
    print()

    for suite in SUITES:
        run_suite(suite)

    latency = sample_isolated_retrieval_latency()
    print()
    print(f"Evidence suites: Passed {len(SUITES)}/{len(SUITES)}")
    print(
        "Isolated synthetic retrieval latency "
        f"({latency['document_count']} docs, "
        f"{latency['active_child_chunk_count']} active child chunks, "
        f"{latency['answer_case_count']} answer cases, "
        f"{latency['sample_count']} retrieval-only samples):"
    )
    print(f"  P50: {latency['p50_ms']:.4f} ms")
    print(f"  P95: {latency['p95_ms']:.4f} ms")
    print(f"  Max: {latency['max_ms']:.4f} ms")
    print(
        "Boundary: this is an in-memory lexical microbenchmark; it excludes "
        "PDF parsing, database IO, embedding/reranking, API transport and LLM latency."
    )


if __name__ == "__main__":
    main()
