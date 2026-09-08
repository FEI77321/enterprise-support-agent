# 模块职责：验证父块识别支持 Markdown 标题与普通段落。

from eval_path import setup_backend_path

setup_backend_path()

from app.knowledge_base import (
    build_parent_context_by_child_index,
)


def test_markdown_heading_with_paragraphs() -> tuple[bool, str]:
    """Markdown 标题后的连续普通段落应归入同一个父块。"""
    content = """## VPN 排查

先确认当前网络可以访问外网。

再检查 VPN 客户端是否为最新版本。

## 其他说明

如仍无法连接，请联系 IT 支持。
"""

    context_by_child_index = (
        build_parent_context_by_child_index(content)
    )

    expected_context = (
        "## VPN 排查\n"
        "先确认当前网络可以访问外网。\n"
        "再检查 VPN 客户端是否为最新版本。"
    )

    # split_text_into_chunks() 会得到：
    # 0=标题，1=第一段，2=第二段，3=下一个标题，4=其他说明。
    actual_context = context_by_child_index.get(1)

    if actual_context != expected_context:
        return (
            False,
            f"期望：{expected_context!r}；实际：{actual_context!r}",
        )

    return True, ""


def main() -> None:
    ok, reason = test_markdown_heading_with_paragraphs()

    if not ok:
        print(f"FAIL markdown_heading_with_paragraphs: {reason}")
        raise SystemExit(1)

    print(
        "PASS markdown_heading_with_paragraphs: "
        "Markdown 标题与普通段落正确组成父块"
    )


if __name__ == "__main__":
    main()