"""验证 Prompt Injection 规则和主 Agent 阻断行为。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
os.environ["TRACE_PERSISTENCE_ENABLED"] = "false"

from app.agent import handle_message
from app.safety_guard import assess_user_input


def main() -> None:
    cases = json.loads((PROJECT_ROOT / "eval" / "datasets" / "v1" / "safety_cases.json").read_text(encoding="utf-8"))["cases"]
    for case in cases:
        decision = assess_user_input(case["input"])
        assert decision.action == case["action"], case
        if case["action"] == "block":
            assert case["attack_type"] in decision.attack_types, case
            response = handle_message(case["input"], request_id=case["id"])
            assert response.type == "clarify" and response.workflow_steps == ["input_guard_blocked"], case
    print(f"Prompt injection boundary eval: Passed {len(cases)}/{len(cases)}")


if __name__ == "__main__":
    main()
