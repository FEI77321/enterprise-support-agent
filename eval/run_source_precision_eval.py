# 模块职责：验证规则回答的 sources 只保留实际用于回答的首条证据。

from eval_path import setup_backend_path

setup_backend_path()

from app.agent import handle_message


def main() -> None:
    response = handle_message("超过五千的费用还需要谁审批")

    expected_chunk_id = (
        "reimbursement_policy.md::chunk-11"
    )

    actual_chunk_ids = [
        source.chunk_id
        for source in response.sources
    ]

    if actual_chunk_ids != [expected_chunk_id]:
        print("FAIL rag_015: sources 包含重复或无关证据")
        print(f"期望：[{expected_chunk_id}]")
        print(f"实际：{actual_chunk_ids}")
        raise SystemExit(1)

    print("PASS rag_015: sources 只保留实际回答证据")


if __name__ == "__main__":
    main()