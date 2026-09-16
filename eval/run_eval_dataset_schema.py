"""验证分层 Eval Dataset 的清单、类别和 case ID，防止评测资产静默失效。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "datasets" / "v1"


def main() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    all_ids: set[str] = set()
    count = 0
    for dataset in manifest["datasets"]:
        payload = json.loads((ROOT / dataset["file"]).read_text(encoding="utf-8"))
        assert payload["category"] == dataset["category"], dataset["file"]
        assert payload["cases"], dataset["file"]
        for case in payload["cases"]:
            assert case["id"] not in all_ids, case["id"]
            all_ids.add(case["id"])
            count += 1
    print(f"Eval dataset schema: Passed {len(manifest['datasets'])}/{len(manifest['datasets'])} datasets, {count} cases")


if __name__ == "__main__":
    main()
