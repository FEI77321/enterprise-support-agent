"""将已纳入回归的 Bad Case 导出成版本化 Eval Dataset JSON。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.bad_case_store import export_regression_dataset


def write_dataset(output_path: Path, database_path: Path | None = None) -> dict:
    dataset = export_regression_dataset(database_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=None)
    args = parser.parse_args()
    dataset = write_dataset(args.output, args.database)
    print(f"Bad Case dataset export: Wrote {dataset['case_count']} regression cases to {args.output}")


if __name__ == "__main__":
    main()
