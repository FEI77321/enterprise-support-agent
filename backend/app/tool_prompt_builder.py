# 模块职责：工具选择提示词模块：将可用工具及其参数说明转换为给大模型阅读的指令，要求模型只输出符合约定的工具调用 JSON。

import json


def build_tool_selection_prompt(
    user_message: str,
    tools: list[dict[str, object]],
) -> str:  # 函数：负责 构建 工具 选择 提示词 相关逻辑。
    tools_json = json.dumps(tools, ensure_ascii=False, indent=2)

    return (
        "你是企业 IT 支持 Agent 的工具选择器。\n"
        "你的任务是根据用户问题，从可用工具中选择最合适的工具。\n\n"
        "选择规则：\n"
        "1. 如果用户提供了工单号，并询问工单状态，选择 query_ticket_status。\n"
        "2. 如果用户描述了无法通过知识库直接解决的 IT 故障，选择 create_ticket。\n"
        "3. 如果用户问题适合先查企业知识库，选择 search_knowledge_base。\n"
        "4. 如果关键词检索不足或语义表达不明确，可以选择 search_vector_store。\n"
        "5. 如果不需要调用工具，tool_name 返回 null。\n\n"
        "输出要求：\n"
        "请只输出 JSON，不要输出 Markdown 或解释文字。\n"
        "JSON 格式如下：\n"
        "{\n"
        '  "tool_name": "工具名或 null",\n'
        '  "arguments": {}\n'
        "}\n\n"
        "用户问题：\n"
        f"{user_message}\n\n"
        "可用工具 schema：\n"
        f"{tools_json}"
    )
