# 模块职责：本地知识库模块：加载文档、将文档切分为检索片段、根据用户问题选出最相关内容，并在没有大模型时生成可追溯的规则回答。

from dataclasses import dataclass
from pathlib import Path


DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "docs"


@dataclass
class SearchResult:  # 类：表示知识库检索命中的一个文档片段及其相关信息。
    file: str
    content: str
    score: int
    chunk_id: str | None = None


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


def search_knowledge_base(query: str, top_k: int = 3) -> list[SearchResult]:  # 函数：负责 检索 知识 库 相关逻辑。
    documents = load_documents()
    normalized_query = expand_query_synonyms(query).lower()
    results: list[SearchResult] = []

    for file, content in documents.items():
        document_score = 0

        for keyword in KEYWORDS.get(file, []):
            if keyword.lower() in normalized_query:
                document_score += 3

        if document_score == 0:
            continue

        chunks = split_text_into_chunks(content)
        best_chunk = ""
        best_chunk_score = 0
        best_chunk_index = 0

        for index, chunk in enumerate(chunks):

            if chunk.startswith("#"):
                continue

            if "优先级" in chunk:
                continue

            chunk_score = 0
            for keyword in KEYWORDS.get(file, []):
                keyword_lower = keyword.lower()
                query_lower = normalized_query
                chunk_lower = chunk.lower()

                if keyword_lower in query_lower and keyword_lower in chunk_lower:
                    if keyword_lower.isdigit():
                        chunk_score += 8
                    else:
                        chunk_score += 5

            if chunk_score > best_chunk_score:
                best_chunk = chunk
                best_chunk_score = chunk_score
                best_chunk_index = index

        if not best_chunk and chunks:
            for index, chunk in enumerate(chunks):
                if chunk.startswith("#"):
                    continue
                if "优先级" in chunk:
                    continue

                best_chunk = chunk
                best_chunk_index = index
                break

        results.append(
            SearchResult(
                file=file,
                content=best_chunk,
                score=document_score,
                chunk_id=f"{file}::chunk-{best_chunk_index + 1}",
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

    if best.chunk_id:
        reference += f", Chunk ID: {best.chunk_id}"

    return (
        f"根据《{best.file}》中的相关内容，可以参考以下处理方式：\n\n"
        f"{context}\n\n"
        f"参考来源：\n"
        f"- {reference}"
    )

