# 模块职责：人工案例评估：加载人工定义的问题和预期结果，运行完整问答链路，判定命中情况并生成可阅读的评估报告。

import json
from pathlib import Path
import os

from eval_path import PROJECT_ROOT, setup_backend_path


REPORT_PATH = Path(__file__).resolve().parent / "eval_report.md"
setup_backend_path()

from app.agent import handle_message


TEST_CASES_FILE = PROJECT_ROOT / "eval" / "test_cases.json"


def load_test_cases() -> list[dict]:  # 函数：负责 加载 测试 cases 相关逻辑。
    return json.loads(TEST_CASES_FILE.read_text(encoding="utf-8"))


def evaluate_case(case: dict) -> tuple[bool, str, str, bool]:  # 函数：负责 evaluate 案例 相关逻辑。
    message = case["input"]["message"]
    expected = case["expected"]
    case_env = case.get("env", {})

    old_env = {}
    for key, value in case_env.items():
        old_env[key] = os.environ.get(key)
        os.environ[key] = value

    try:
        response = handle_message(message)
    finally:
        for key, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

    actual_summary = summarize_response(response)
    ticket_created = response.ticket is not None and response.type == "ticket_created"

    if response.type != expected["response_type"]:
        return False, (
            f"expected type {expected['response_type']}, got {response.type}; "
            f"actual: {actual_summary}"
        ), actual_summary, ticket_created

    if "answer_contains" in expected:
        answer = response.answer or ""
        if expected["answer_contains"] not in answer:
            return False, (
                f"expected answer to contain {expected['answer_contains']}, "
                f"got {answer}; actual: {actual_summary}"
            ), actual_summary, ticket_created


    if "workflow_contains" in expected:
        missing_steps = [
            step
            for step in expected["workflow_contains"]
            if step not in response.workflow_steps
        ]

        if missing_steps:
            return False, (
                f"期望 workflow 包含 {missing_steps}， "
                f"实际 workflow_steps={response.workflow_steps}; actual: {actual_summary}"
            ), actual_summary, ticket_created


    if "source" in expected:
        source_files = [source.file for source in response.sources]
        if expected["source"] not in source_files:
            return False, (
                f"expected source {expected['source']}, got {source_files}; "
                f"actual: {actual_summary}"
            ), actual_summary, ticket_created

    if "chunk_id" in expected:
        chunk_ids = [source.chunk_id for source in response.sources]
        if expected["chunk_id"] not in chunk_ids:
            return False, (
                f"expected chunk_id {expected['chunk_id']}, got {chunk_ids}; "
                f"actual: {actual_summary}"
            ), actual_summary, ticket_created

    if "priority" in expected:
        if response.ticket is None:
            return False, "expected ticket, got None", actual_summary, ticket_created
        if response.ticket.priority != expected["priority"]:
            return False, (
                f"expected priority {expected['priority']}, got {response.ticket.priority}; "
                f"actual: {actual_summary}"
            ), actual_summary, ticket_created

    return True, "", actual_summary, ticket_created

def summarize_response(response) -> str:  # 函数：负责 汇总 响应 相关逻辑。
    sources = [
        {
            "file": source.file,
            "score": source.score,
            "chunk_id": source.chunk_id,
        }
        for source in response.sources
    ]

    ticket_id = response.ticket.ticket_id if response.ticket else None

    return (
        f"type={response.type}, "
        f"sources={sources}, "
        f"ticket_id={ticket_id},"
        f"workflow_steps={response.workflow_steps}"
    )



def build_expected_summary(expected: dict) -> str:  # 函数：负责 构建 expected 摘要 相关逻辑。
    summary = [f"response_type={expected['response_type']}"]

    if "source" in expected:
        summary.append(f"source={expected['source']}")

    if "chunk_id" in expected:
        summary.append(f"chunk_id={expected['chunk_id']}")

    if "priority" in expected:
        summary.append(f"priority={expected['priority']}")

    if "workflow_contains" in expected:
        workflow = " -> ".join(expected["workflow_contains"])
        summary.append(f"workflow contains: {workflow}")

    if "answer_contains" in expected:
        summary.append(f"answer contains: {expected['answer_contains']}")

    return "; ".join(summary)


def write_eval_report(
    passed: int,
    total: int,
    failures: list[dict],
    case_results: list[dict],
) -> None:  # 函数：负责 写入 评估 报告 相关逻辑。

    lines = [
        "# Enterprise Support Agent 评测报告",
        "",
        "本报告由 `eval/run_manual_eval.py` 自动生成，用于记录端到端 Agent 工作流评测结果。",
        "",
        "## 评测结论",
        "",
        f"端到端评测结果：`Passed: {passed}/{total}`",
        "",
    ]

    if not failures:
        lines.extend(
            [
                "结论：全部端到端 case 已通过，当前 Agent 主流程可以作为稳定版本继续迭代。",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"结论：存在 {len(failures)} 个失败 case，需要优先定位并修复。",
                "",
            ]
        )

    lines.extend(
        [
            "## 一键评测入口",
            "",
            "如需同时运行配置评测、工具评测、LLM 质量评测、API smoke test 和端到端评测，执行：",
            "",
            "```powershell",
            ".\\backend\\.venv\\Scripts\\python.exe eval\\run_all_eval.py",
            "```",
            "",
            "完整评测通过时，终端会输出：",
            "",
            "```text",
            "Config eval passed.",
            "Tool eval: Passed 7/7",
            "LLM quality eval: Passed 3/3",
            "API smoke eval: Passed 4/4",
            f"Manual eval: Passed {passed}/{total}",
            "Eval suites passed: 5/5",
            "```",
            "",
            "## 端到端评测范围",
            "",
            "端到端评测直接调用 `handle_message()`，覆盖用户消息进入 Agent 后的完整处理流程：",
            "",
            "- 用户输入解析",
            "- 工单号提取",
            "- Markdown 知识库检索",
            "- ChromaDB 向量检索 fallback",
            "- 低置信度澄清追问",
            "- 自动创建工单",
            "- 工单状态查询",
            "- LLM Stub 分支",
            "- `workflow_steps` 执行轨迹记录",
            "",
            "## Case 汇总",
            "",
            "| Case | 状态 | 输入 | 期望检查 | 创建工单 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )

    for case_result in case_results:
        expected_summary = build_expected_summary(case_result["expected"])
        ticket_created = "是" if case_result["ticket_created"] else "否"
        lines.append(
            "| {id} | {status} | {message} | {expected} | {ticket_created} |".format(
                id=case_result["id"],
                status=case_result["status"],
                message=case_result["message"],
                expected=expected_summary,
                ticket_created=ticket_created,
            )
        )

    lines.extend(
        [
            "",
            "## Workflow 验证",
            "",
            "评测不仅检查最终响应类型，还会检查 `workflow_steps`，确保 Agent 的内部执行路径符合预期。",
            "",
            "典型路径示例：",
            "",
            "```text",
            "知识库直接回答:",
            "extract_ticket_id -> search_knowledge_base -> rule_answer -> knowledge_answer",
            "",
            "向量检索追问:",
            "extract_ticket_id -> search_knowledge_base -> search_vector_store -> vector_clarify",
            "",
            "创建工单:",
            "extract_ticket_id -> search_knowledge_base -> search_vector_store -> create_ticket -> ticket_created",
            "",
            "查询不存在工单:",
            "extract_ticket_id -> query_ticket_status -> ticket_not_found",
            "",
            "LLM Stub 回答:",
            "extract_ticket_id -> search_knowledge_base -> rule_answer -> llm_answer -> knowledge_answer",
            "```",
            "",
            "## 详细结果",
            "",
        ]
    )

    for case_result in case_results:
        lines.append(f"### {case_result['id']} {case_result['status']}")
        lines.append("")
        lines.append(f"- Input: {case_result['message']}")
        lines.append(
            f"- Expected: {json.dumps(case_result['expected'], ensure_ascii=False)}"
        )
        lines.append(
            f"- Env: {json.dumps(case_result['env'], ensure_ascii=False)}"
        )
        lines.append(f"- Actual: {case_result['actual']}")
        lines.append(f"- Ticket created: {case_result['ticket_created']}")

        if case_result["reason"]:
            lines.append(f"- Reason: {case_result['reason']}")

        lines.append("")

    if failures:
        lines.append("## 失败 Case")
        lines.append("")

        for failure in failures:
            lines.append(f"### {failure['id']}")
            lines.append("")
            lines.append(f"- Message: {failure['message']}")
            lines.append(f"- Reason: {failure['reason']}")
            lines.append("")

    lines.extend(
        [
            "## 面试讲法",
            "",
            "```text",
            "我没有只做功能演示，而是把评测分成配置评测、工具评测、LLM 质量评测、API smoke test 和端到端评测五层。",
            "端到端评测会直接调用 Agent 的 handle_message()，检查响应类型、知识库来源、chunk_id、工单优先级和 workflow_steps。",
            "LLM 质量评测会验证开启 LLM Stub 后是否进入 llm_answer 分支，同时保留 sources 和正确 workflow；也会验证 OpenAI provider 缺少 API Key 时的 fallback，以及 mock OpenAI SDK 调用链路。",
            "API smoke test 会通过 FastAPI TestClient 验证 /health、/version、/chat 正常响应和参数校验，确认 HTTP 接口层没有退化。",
            "这样每次改动后都可以通过 run_all_eval.py 一键回归，确认配置层、工具层、LLM 链路、HTTP 接口层和 Agent 工作流都没有退化。",
            "```",
            "",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    cases = load_test_cases()
    passed = 0
    failures: list[dict] = []
    case_results: list[dict] = []

    for case in cases:
        ok, reason,actual_summary, ticket_created = evaluate_case(case)
        status = "PASS" if ok else "FAIL"
        print(f"{status} {case['id']}: {case['input']['message']}")

        if ok:
            passed += 1
        else:
            print(f"  Reason: {reason}")
            failures.append(
                {
                    "id": case["id"],
                    "message": case["input"]["message"],
                    "reason": reason,
                }
            )
        case_results.append(
            {
                "id": case["id"],
                "status": status,
                "message": case["input"]["message"],
                "expected": case["expected"],
                "actual": actual_summary,
                "ticket_created": ticket_created,
                "reason": reason,
                "env": case.get("env", {}),
            }
        )

    print()
    print(f"Passed: {passed}/{len(cases)}")

    write_eval_report(passed, len(cases), failures, case_results)
    print(f"Eval report written to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
