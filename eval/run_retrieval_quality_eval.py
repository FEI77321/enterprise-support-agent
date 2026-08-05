# 模块职责：检索质量评估：验证知识库检索是否能命中正确来源、保留可追溯 chunk_id，并避免无关问题误命中知识库。

from eval_path import setup_backend_path

setup_backend_path()

from app.knowledge_base import (
    SearchResult,
    build_answer,
    search_knowledge_base,
)


def test_rule_answer_contains_traceable_reference() -> tuple[bool, str]:  # 测试函数：验证规则回答包含可追溯的 File 和 Chunk ID。
    result = SearchResult(
        file="vpn_guide.md",
        content="请检查虚拟网卡驱动状态。",
        score=6,
        chunk_id="vpn_guide.md::chunk-6",
    )

    answer = build_answer(
        "VPN 720 错误怎么办",
        [result],
    )

    expected_reference = (
        "File: vpn_guide.md, "
        "Chunk ID: vpn_guide.md::chunk-6"
    )

    if "参考来源" not in answer:
        return False, f"规则回答缺少参考来源标题，实际 answer={answer}"

    if expected_reference not in answer:
        return False, (
            f"规则回答缺少正确引用 {expected_reference}，"
            f"实际 answer={answer}"
        )

    return True, ""

def test_vpn_720_hits_vpn_guide() -> tuple[bool, str]:  # 测试函数：验证 VPN 720 问题优先命中 VPN 文档。
    results = search_knowledge_base("VPN 720 错误怎么办")

    if not results:
        return False, "期望有检索结果，实际为空"

    first = results[0]
    if first.file != "vpn_guide.md":
        return False, f"期望第一条来源为 vpn_guide.md，实际为 {first.file}"

    return True, ""


def test_search_result_has_traceable_chunk_id() -> tuple[bool, str]:  # 测试函数：验证检索结果包含 file 和可追溯 chunk_id。
    results = search_knowledge_base("VPN 720 错误怎么办")

    if not results:
        return False, "期望有检索结果，实际为空"

    first = results[0]
    if not first.file:
        return False, "期望 SearchResult.file 不为空"

    if not first.chunk_id:
        return False, "期望 SearchResult.chunk_id 不为空"

    if not first.chunk_id.startswith(f"{first.file}::chunk-"):
        return False, f"期望 chunk_id 可追溯到 file，实际为 {first.chunk_id}"

    return True, ""


def test_irrelevant_question_does_not_hit_knowledge_base() -> tuple[bool, str]:  # 测试函数：验证无关问题不会命中知识库。
    results = search_knowledge_base("今天午饭吃什么？")

    if results:
        summary = [(item.file, item.score, item.chunk_id) for item in results]
        return False, f"期望无关问题不命中知识库，实际为 {summary}"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("vpn_720_hits_vpn_guide", test_vpn_720_hits_vpn_guide),
        ("search_result_has_traceable_chunk_id", test_search_result_has_traceable_chunk_id),
        ("irrelevant_question_does_not_hit_knowledge_base", test_irrelevant_question_does_not_hit_knowledge_base),
        (
            "rule_answer_contains_traceable_reference",
            test_rule_answer_contains_traceable_reference,
        ),
    ]

    passed = 0
    for name, test_func in tests:
        ok, reason = test_func()
        print(f"{'PASS' if ok else 'FAIL'} {name}")
        if ok:
            passed += 1
        else:
            print(f"  Reason: {reason}")

    print()
    print(f"Retrieval quality eval: Passed {passed}/{len(tests)}")

    if passed != len(tests):
        raise SystemExit(1)


if __name__ == "__main__":
    main()