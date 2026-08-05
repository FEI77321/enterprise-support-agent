# 模块职责：问答提示词评估：检查知识库提示词是否包含来源约束等关键要求，防止提示词修改后丢失回答规范。

from eval_path import setup_backend_path


setup_backend_path()

from app.models import Source
from app.prompt_builder import build_prompt


def test_prompt_contains_source_instruction() -> tuple[bool, str]:  # 测试函数：验证 提示词 包含 来源 instruction 场景。
    sources = [
        Source(
            file="vpn_guide.md",
            snippet="VPN 720 错误通常和虚拟网卡驱动异常有关。",
            score=6,
            chunk_id="vpn_guide.md::chunk-6",
        )
    ]

    prompt = build_prompt("VPN 720 错误怎么办", sources)

    required_texts = [
        "参考来源",
        "File",
        "Chunk ID",
        "vpn_guide.md",
        "vpn_guide.md::chunk-6",
        "不要编造",
        "当前知识库信息不足",
    ]

    for text in required_texts:
        if text not in prompt:
            return False, f"prompt 缺少必要文本：{text}"

    return True, ""


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    tests = [
        ("prompt_contains_source_instruction", test_prompt_contains_source_instruction),
    ]

    passed = 0

    for name, test_func in tests:
        ok, reason = test_func()
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}")

        if ok:
            passed += 1
        else:
            print(f"  Reason: {reason}")

    print()
    print(f"Passed: {passed}/{len(tests)}")

    if passed != len(tests):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
