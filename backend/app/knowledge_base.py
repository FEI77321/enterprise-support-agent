# 模块职责：本地知识库模块：加载文档、将文档切分为检索片段、根据用户问题选出最相关内容，并在没有大模型时生成可追溯的规则回答。
import re
from dataclasses import dataclass
from pathlib import Path


DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "docs"


@dataclass
class SearchResult:  # 类：表示知识库检索命中的一个文档片段及其相关信息。
    file: str
    content: str
    score: int
    chunk_id: str | None = None
    context_chunk_id: str | None = None

KEYWORDS: dict[str, list[str]] = {
    "vpn_guide.md": ["vpn", "连不上", "远程办公", "720", "691", "内网", "公司网络"],
    "reimbursement_policy.md": ["报销","出差", "申请报销", "怎么申请报销", "发票",  "费用", "打款", "审批"],
    "leave_policy.md": ["请假", "年假", "年假申请", "怎么申请", "调休", "病假", "假期"],
    "account_login_faq.md": ["账号", "登录", "密码", "验证码", "MFA", "锁定", "无法登录"],
}

QUERY_SYNONYMS: dict[str, str] = {
    "出差": "差旅",
}
CONTEXTUAL_QUERY_SYNONYMS: list[tuple[str, str, tuple[str, ...]]] = [
    ("被锁", "锁定", ("账号", "登录", "mfa", "验证码")),
]

def expand_query_synonyms(query: str) -> str:  # 函数：根据用户表达和上下文补充可检索的标准业务词。
    expanded_query = query
    normalized_query = query.lower()

    for alias, canonical_term in QUERY_SYNONYMS.items():
        if (
            alias.lower() in normalized_query
            and canonical_term.lower() not in expanded_query.lower()
        ):
            expanded_query += f" {canonical_term}"

    for alias, canonical_term, context_terms in CONTEXTUAL_QUERY_SYNONYMS:
        has_context = any(
            context.lower() in normalized_query
            for context in context_terms
        )

        if (
            alias.lower() in normalized_query
            and has_context
            and canonical_term.lower() not in expanded_query.lower()
        ):
            expanded_query += f" {canonical_term}"

    return expanded_query


def load_documents() -> dict[str, str]:  # 函数：负责 加载 documents 相关逻辑。
    documents: dict[str, str] = {}
    for path in DOCS_DIR.glob("*.md"):
        documents[path.name] = path.read_text(encoding="utf-8")
    return documents



def split_text_into_chunks(content: str) -> list[str]:  # 函数：负责 split 文本 into chunks 相关逻辑。
    return [line.strip() for line in content.splitlines() if line.strip()]

def build_parent_context_by_child_index(
    content: str,
) -> dict[int, str]:
    """建立子块下标到完整父上下文的映射。

    支持两种父块：
    1. “报销流程：” + 连续编号步骤；
    2. Markdown 标题（# / ## / ###）+ 连续普通段落或列表。
    """
    chunks = split_text_into_chunks(content)
    parent_context_by_child_index: dict[int, str] = {}

    current_section_indexes: list[int] = []
    current_section_type: str | None = None

    for index, chunk in enumerate(chunks):
        is_markdown_heading = bool(
            re.match(r"^#{1,6}\s+\S", chunk)
        )

        # 新 Markdown 标题：开始一个“标题 + 内容”的父块。
        if is_markdown_heading:
            current_section_indexes = [index]
            current_section_type = "markdown"
            continue

        # 冒号标题：开始一个“标题 + 编号步骤”的父块。
        if chunk.endswith(("：", ":")):
            current_section_indexes = [index]
            current_section_type = "numbered_list"
            continue

        is_numbered_item = bool(
            re.match(r"^\s*\d+[.、]", chunk)
        )

        if (
            current_section_type == "numbered_list"
            and is_numbered_item
        ):
            current_section_indexes.append(index)

        elif current_section_type == "markdown":
            # Markdown 标题下，普通段落和列表都归入该标题。
            current_section_indexes.append(index)

        else:
            # 不属于当前父块的内容，结束当前收集。
            current_section_indexes = []
            current_section_type = None
            continue

        parent_content = "\n".join(
            chunks[item_index]
            for item_index in current_section_indexes
        )

        # 当前父块中的标题、段落、步骤，都映射到完整父上下文。
        for item_index in current_section_indexes:
            parent_context_by_child_index[item_index] = (
                parent_content
            )

    return parent_context_by_child_index


def _character_bigrams(text: str) -> set[str]:
    """把文本规范化后拆成连续的两个字符，用于轻量中文词面匹配。"""
    normalized_text = re.sub(
        r"[\W_]+",
        "",
        text.lower(),
    )

    if not normalized_text:
        return set()

    if len(normalized_text) == 1:
        return {normalized_text}

    return {
        normalized_text[index:index + 2]
        for index in range(len(normalized_text) - 1)
    }


def _asks_for_first_step(query: str) -> bool:
    """判断用户是否在询问排障的第一步。"""
    return any(
        marker in query
        for marker in ("先", "首先", "第一步")
    )

def _asks_for_troubleshooting(query: str) -> bool:
    """判断用户是否在描述故障并询问排查方式。"""
    return any(
        marker in query
        for marker in (
            "连不上",
            "访问不了",
            "无法",
            "打不开",
            "故障",
            "异常",
        )
    )

def _asks_for_priority(query: str) -> bool:
    """判断用户是否在询问事件或工单优先级。"""
    return "优先级" in query


def _is_troubleshooting_chunk(chunk: str) -> bool:
    """判断 chunk 是否提供了排障入口或排查说明。"""
    return (
        "排查" in chunk
        or "无法连接" in chunk
    )



def search_knowledge_base(
    query: str,
    top_k: int = 3,
) -> list[SearchResult]:
    """按文档路由、按 chunk 精排，返回全局 Top-k。"""
    documents = load_documents()
    normalized_query = expand_query_synonyms(query).lower()
    query_bigrams = _character_bigrams(normalized_query)
    results: list[SearchResult] = []

    for file, content in documents.items():
        document_keywords = KEYWORDS.get(file, [])

        # 第 1 阶段：仍用已有领域关键词确定候选文档。
        # 这能维持无关问题不误召回的边界。
        is_candidate_document = any(
            keyword.lower() in normalized_query
            for keyword in document_keywords
        )

        if not is_candidate_document:
            continue

        chunks = split_text_into_chunks(content)
        parent_context_by_child_index = (
            build_parent_context_by_child_index(content)
        )

        for index, chunk in enumerate(chunks):
            if chunk.startswith("#"):
                continue

            chunk_lower = chunk.lower()
            chunk_bigrams = _character_bigrams(chunk_lower)

            # 第 2 阶段：问题词和 chunk 词的重合越多，分数越高。
            chunk_score = len(query_bigrams & chunk_bigrams)* 2

            # 错误码、VPN、MFA 等领域关键词仍保留额外权重。
            for keyword in document_keywords:
                keyword_lower = keyword.lower()

                if (
                    keyword_lower in normalized_query
                    and keyword_lower in chunk_lower
                ):
                    if keyword_lower.isdigit():
                        chunk_score += 10
                    else:
                        chunk_score += 1

            # “先检查什么”这类通用首步意图，优先匹配编号 1 的步骤。
            if (
                _asks_for_first_step(normalized_query)
                and re.match(r"^\s*1[.、]", chunk)
            ):
                chunk_score += 14
            # 故障型问题优先返回排障入口，避免被“优先级”等背景说明抢到前面。
            if (
                _asks_for_troubleshooting(normalized_query)
                and _is_troubleshooting_chunk(chunk)
                ):
                chunk_score += 8
            # 用户明确问优先级时，优先返回包含优先级的规则。
            if (
                _asks_for_priority(normalized_query)
                and "优先级" in chunk
            ):
                chunk_score += 8

            if chunk_score == 0:
                continue

            parent_context = parent_context_by_child_index.get(index)

            parent_start_index = next(
                (
                    item_index
                    for item_index in range(index, -1, -1)
                    if chunks[item_index].endswith(("：", ":"))
                ),
                index,
            )


            results.append(
                SearchResult(
                    file=file,
                    content=parent_context or chunk,
                    score=chunk_score,
                    chunk_id=f"{file}::chunk-{index + 1}",
                    context_chunk_id=(
                        f"{file}::parent-chunk-{parent_start_index + 1}"
                        if parent_context
                        else f"{file}::chunk-{index + 1}"
                    ),
                )
            )

    results.sort(key=lambda item: item.score, reverse=True)
    return results[:top_k]



def build_answer(query: str, results: list[SearchResult]) -> str:  # 函数：负责 构建 回答 相关逻辑。
    if not results:
        return ""

    best = results[0]
    context = best.content.strip()

    reference = f"File: {best.file}"

    reference_chunk_id = (
            best.context_chunk_id
            or best.chunk_id
    )

    if reference_chunk_id:
        reference += f", Chunk ID: {reference_chunk_id}"

    return (
        f"根据《{best.file}》中的相关内容，可以参考以下处理方式：\n\n"
        f"{context}\n\n"
        f"参考来源：\n"
        f"- {reference}"
    )

