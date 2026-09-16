"""受控白名单 Query Rewrite 的主检索增益与精确实体不退化实验。"""

from __future__ import annotations

from pathlib import Path
import re
from tempfile import TemporaryDirectory

from eval_path import setup_backend_path

setup_backend_path()

from app.eval_trace_store import complete_eval_run, create_eval_run, get_eval_run, record_eval_case
from app.knowledge_base import search_knowledge_base
from app.query_rewrite import rewrite_query


CASES = (
    ("rewrite-gain-001", "内网打不开", "vpn_guide.md", True),
    ("rewrite-gain-002", "内网上不去", "vpn_guide.md", True),
    ("rewrite-gain-003", "报销咋整", "reimbursement_policy.md", True),
    ("rewrite-gain-004", "登录不了", "account_login_faq.md", True),
    ("rewrite-protected-005", "查询 TICKET-20240101-0001", None, False),
    ("rewrite-protected-006", "VPN 720 错误", "vpn_guide.md", False),
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = PROJECT_ROOT / "eval" / "fixtures" / "query_rewrite_gain_corpus_v1.json"


def _search(query: str, corpus: dict) -> list[dict]:
    tokens = set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", query.lower()))
    scored = []
    for document in corpus["documents"]:
        document_tokens = set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", document["text"].lower()))
        score = len(tokens & document_tokens)
        if score:
            scored.append({**document, "score": score})
    return sorted(scored, key=lambda item: (-item["score"], item["file"]))[:3]


def score(results: list[dict], expected_file: str | None) -> tuple[float, float, float]:
    if expected_file is None:
        return (1.0 if not results else 0.0, 1.0 if not results else 0.0, 1.0 if not results else 0.0)
    rank = next((index for index, item in enumerate(results[:3], start=1) if item["file"] == expected_file), None)
    if rank is None:
        return 0.0, 0.0, 0.0
    return 1.0, 1 / rank, 1 / __import__("math").log2(rank + 1)


def main() -> None:
    corpus = __import__("json").loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert corpus["scope"] == "controlled_alias_retrieval_fixture"
    with TemporaryDirectory() as directory:
        database = Path(directory) / "rewrite-gain.db"
        run_id = create_eval_run(
            suite_name="query_rewrite_gain", dataset_version="query-rewrite-gain-v1",
            judge_provider="deterministic", database_path=database,
        )
        raw_metrics: list[tuple[float, float, float]] = []
        rewritten_metrics: list[tuple[float, float, float]] = []
        production_raw_metrics: list[tuple[float, float, float]] = []
        production_rewritten_metrics: list[tuple[float, float, float]] = []
        protected_ok = True
        for case_id, query, expected_file, should_rewrite in CASES:
            decision = rewrite_query(query)
            raw_results = _search(query, corpus)
            effective_results = _search(decision.effective_query, corpus)
            production_raw_results = [{"file": item.file} for item in search_knowledge_base(query)]
            production_effective_results = [{"file": item.file} for item in search_knowledge_base(decision.effective_query)]
            raw = score(raw_results, expected_file)
            effective = score(effective_results, expected_file)
            production_raw = score(production_raw_results, expected_file)
            production_effective = score(production_effective_results, expected_file)
            raw_metrics.append(raw)
            rewritten_metrics.append(effective)
            production_raw_metrics.append(production_raw)
            production_rewritten_metrics.append(production_effective)
            if not should_rewrite:
                protected_ok = protected_ok and not decision.triggered and decision.effective_query == query and raw == effective
            result = {
                "original_query": query, "effective_query": decision.effective_query,
                "rewrite_triggered": decision.triggered, "raw": {"recall_at_3": raw[0], "mrr_at_3": raw[1], "ndcg_at_3": raw[2]},
                "rewritten": {"recall_at_3": effective[0], "mrr_at_3": effective[1], "ndcg_at_3": effective[2]},
                "expected_file": expected_file,
                "project_kb_raw": {"recall_at_3": production_raw[0], "mrr_at_3": production_raw[1], "ndcg_at_3": production_raw[2]},
                "project_kb_rewritten": {"recall_at_3": production_effective[0], "mrr_at_3": production_effective[1], "ndcg_at_3": production_effective[2]},
            }
            record_eval_case(
                eval_run_id=run_id, case_id=case_id, prompt_version="not_applicable", status="passed",
                deterministic=result, judge={"provider": "not_applicable"}, human={"status": "not_required"},
                trace={"query_rewrite": decision.to_public_dict(), "raw_top3": [item["file"] for item in raw_results[:3]], "effective_top3": [item["file"] for item in effective_results[:3]], "project_kb_raw_top3": [item["file"] for item in production_raw_results[:3]], "project_kb_rewritten_top3": [item["file"] for item in production_effective_results[:3]]},
                database_path=database,
            )
        avg = lambda values, index: round(sum(item[index] for item in values) / len(values), 4)
        summary = {
            "case_count": len(CASES),
            "scope": corpus["scope"],
            "raw": {"recall_at_3": avg(raw_metrics, 0), "mrr_at_3": avg(raw_metrics, 1), "ndcg_at_3": avg(raw_metrics, 2)},
            "rewritten": {"recall_at_3": avg(rewritten_metrics, 0), "mrr_at_3": avg(rewritten_metrics, 1), "ndcg_at_3": avg(rewritten_metrics, 2)},
            "project_knowledge_base_raw": {"recall_at_3": avg(production_raw_metrics, 0), "mrr_at_3": avg(production_raw_metrics, 1), "ndcg_at_3": avg(production_raw_metrics, 2)},
            "project_knowledge_base_rewritten": {"recall_at_3": avg(production_rewritten_metrics, 0), "mrr_at_3": avg(production_rewritten_metrics, 1), "ndcg_at_3": avg(production_rewritten_metrics, 2)},
            "protected_entities_unchanged": protected_ok,
        }
        no_regression = all(summary["rewritten"][key] >= summary["raw"][key] for key in summary["raw"])
        project_no_regression = all(summary["project_knowledge_base_rewritten"][key] >= summary["project_knowledge_base_raw"][key] for key in summary["project_knowledge_base_raw"])
        complete_eval_run(run_id, status="passed" if no_regression and project_no_regression and protected_ok else "failed", summary=summary, database_path=database)
        stored = get_eval_run(run_id, database)
        assert stored is not None and len(stored["cases"]) == len(CASES)
        if not no_regression or not project_no_regression or not protected_ok:
            raise SystemExit(f"Query rewrite gain experiment failed: {summary}")
    print(f"Query rewrite gain experiment: Passed {len(CASES)}/{len(CASES)}; raw={summary['raw']}; rewritten={summary['rewritten']}; protected=true")


if __name__ == "__main__":
    main()
