"""回答质量 Judge：确定性约束始终优先，外部 LLM Judge 仅作可选补充。"""

from __future__ import annotations

import json
import os
from typing import Any

from app.llm_client import generate_answer_result
from app.models import ChatResponse


def deterministic_quality(case: dict[str, Any], response: ChatResponse) -> dict[str, Any]:
    answer = response.answer or ""
    source_files = {source.file for source in response.sources}
    required_terms = case.get("expected_answer_contains", [])
    checks = {
        "response_not_empty": bool(answer.strip()),
        "expected_response_type": response.type == case.get("expected_response_type", "answer"),
        "expected_source_present": (
            case.get("expected_file") is None
            or case.get("expected_file") in source_files
        ),
        "required_terms_present": all(term in answer for term in required_terms),
        "citation_traceable": not response.sources or any(
            source.chunk_id and source.chunk_id in answer for source in response.sources
        ),
    }
    return {"checks": checks, "passed": all(checks.values())}


def judge_answer(case: dict[str, Any], response: ChatResponse, deterministic: dict[str, Any]) -> dict[str, Any]:
    """默认离线 Stub；配置 LLM_JUDGE_PROVIDER=model 时尝试结构化模型评分。"""
    provider = (os.getenv("LLM_JUDGE_PROVIDER") or "stub").lower()
    if provider == "stub":
        score = 5 if deterministic["passed"] else 1
        return {
            "provider": "deterministic_stub",
            "available": True,
            "rubric": {
                "groundedness": score,
                "answer_relevance": score,
                "citation_correctness": score,
            },
            "reason": "Offline CI uses deterministic assertions; this is not represented as an external model judgment.",
        }

    prompt = (
        "你是企业 IT 支持回答质量评审器。只输出 JSON，字段为 groundedness、answer_relevance、"
        "citation_correctness（均为 1-5 整数）和 reason。\n"
        f"用户问题：{case['query']}\n"
        f"期望来源：{case.get('expected_file')}\n"
        f"回答：{response.answer}\n"
        f"来源：{[source.model_dump() for source in response.sources]}"
    )
    result = generate_answer_result(prompt)
    if not result.success:
        return {"provider": provider, "available": False, "reason": result.error_reason or "judge_call_failed"}
    try:
        payload = json.loads(result.answer)
        rubric = {key: int(payload[key]) for key in ("groundedness", "answer_relevance", "citation_correctness")}
        if not all(1 <= value <= 5 for value in rubric.values()):
            raise ValueError("score_out_of_range")
        return {"provider": provider, "available": True, "rubric": rubric, "reason": str(payload.get("reason", ""))}
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return {"provider": provider, "available": False, "reason": f"invalid_judge_output:{exc}"}
