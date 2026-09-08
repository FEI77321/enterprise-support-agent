# 模块职责：展示单条 Agent 最终回答及其来源，供人工质量评分。

import argparse
import json
from pathlib import Path

from eval_path import setup_backend_path

setup_backend_path()

from app.agent import handle_message


CASES_PATH = Path(__file__).resolve().with_name(
    "answer_quality_cases.json"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "case_id",
        help="要审阅的样本 ID，例如 rag_001",
    )
    args = parser.parse_args()

    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    case = next(
        (
            item
            for item in data["cases"]
            if item["id"] == args.case_id
        ),
        None,
    )

    if case is None:
        raise ValueError(f"找不到样本：{args.case_id}")

    response = handle_message(case["query"])

    print(f"ID: {case['id']}")
    print(f"问题: {case['query']}")
    print(f"回答类型: {response.type}")
    print()
    print("最终回答:")
    print(response.answer)
    print()
    print("来源:")

    for source in response.sources:
        print(f"- File: {source.file}")
        print(f"  Chunk ID: {source.chunk_id}")
        print(f"  Snippet: {source.snippet}")

    print()
    print("人工填写位置:")
    print(
        "manual_scores = "
        f"{case['manual_scores']}"
    )


if __name__ == "__main__":
    main()
