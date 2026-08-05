# 模块职责：RAG 黄金集评估：读取预设检索用例，验证知识库检索的首条来源、证据块和最低分数是否符合预期。

import json
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.knowledge_base import search_knowledge_base
from app.vector_store import search_vector_store


CASES_PATH = Path(__file__).resolve().with_name("rag_eval_cases.json")
REPORT_PATH = Path(__file__).resolve().with_name(
    "rag_golden_report.md"
)



def evaluate_case(case: dict) -> tuple[bool, str]:  # 函数：执行单条 RAG 黄金用例，并返回是否通过及失败原因。
    query = case["query"]
    expected_file = case["expected_file"]
    retrieval_mode = case.get("retrieval_mode", "keyword")

    if retrieval_mode == "keyword":
        results = search_knowledge_base(query)
    elif retrieval_mode == "vector":
        results = search_vector_store(query)
    else:
        return False, f"不支持的 retrieval_mode：{retrieval_mode}"

    if expected_file is None:
        if results:
            actual = [
                (item.file, item.score, item.chunk_id)
                for item in results
            ]
            return False, f"期望无检索结果，实际为 {actual}"
        return True, ""

    if not results:
        return False, "期望有检索结果，实际为空"

    first = results[0]

    if first.file != expected_file:
        return (
            False,
            f"期望首条文件为 {expected_file}，实际为 {first.file}",
        )

    expected_chunk_id = case.get("expected_chunk_id")
    if expected_chunk_id and first.chunk_id != expected_chunk_id:
        return (
            False,
            f"期望 chunk_id 为 {expected_chunk_id}，实际为 {first.chunk_id}",
        )

    min_score = case.get("min_score")
    if min_score is not None and first.score < min_score:
        return (
            False,
            f"期望分数至少为 {min_score}，实际为 {first.score}",
        )

    return True, ""

def write_rag_golden_report(
    results: list[dict],
) -> None:  # 函数：把 RAG 黄金集评测结果写入 Markdown 报告。
    passed = sum(1 for item in results if item["passed"])
    total = len(results)

    lines = [
        "# RAG Golden Eval Report",
        "",
        f"Passed: {passed}/{total}",
        "",
        "| ID | Query | Mode | Expected File | Result | Reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for item in results:
        status = "PASS" if item["passed"] else "FAIL"
        reason = item["reason"] or "-"
        expected_file = item["expected_file"] or "无结果"

        lines.append(
            f"| {item['id']} | {item['query']} | "
            f"{item['retrieval_mode']} | {expected_file} | "
            f"{status} | {reason} |"
        )

    REPORT_PATH.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main() -> None:  # 函数：加载 RAG 黄金集并输出整体评估结果。
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    report_results: list[dict] = []
    passed = 0

    for case in cases:
        ok, reason = evaluate_case(case)
        report_results.append(
            {
                "id": case["id"],
                "query": case["query"],
                "retrieval_mode": case.get(
                    "retrieval_mode",
                    "keyword",
                ),
                "expected_file": case["expected_file"],
                "passed": ok,
                "reason": reason,
            }
        )
        case_id = case["id"]
        query = case["query"]

        print(f"{'PASS' if ok else 'FAIL'} {case_id}: {query}")

        if ok:
            passed += 1
        else:
            print(f"  Reason: {reason}")
    write_rag_golden_report(report_results)
    print(f"RAG golden report written to: {REPORT_PATH}")
    print()
    print(f"RAG golden eval: Passed {passed}/{len(cases)}")

    if passed != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()