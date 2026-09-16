"""验证 Query Rewrite 只执行白名单改写且保护精确业务实体。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.query_rewrite import rewrite_query


def main() -> None:
    cases = json.loads((PROJECT_ROOT / "eval" / "datasets" / "v1" / "query_rewrite_cases.json").read_text(encoding="utf-8"))["cases"]
    for case in cases:
        decision = rewrite_query(case["input"])
        assert decision.triggered is case["triggered"], case
        if "effective_query" in case:
            assert decision.effective_query == case["effective_query"], case
        if "reason" in case:
            assert decision.reason == case["reason"], case
    print(f"Controlled query rewrite eval: Passed {len(cases)}/{len(cases)}")


if __name__ == "__main__":
    main()
