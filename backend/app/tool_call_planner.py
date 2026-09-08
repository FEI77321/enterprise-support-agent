# 模块职责：工具调用规划模块：根据用户问题生成 JSON 格式的工具选择结果；支持本地 Mock、OpenAI 和 DeepSeek 进行真实规划。
import logging
import json
import re


TICKET_ID_PATTERN = re.compile(r"TICKET-\d{8}-\d{4}")

CURRENT_MESSAGE_MARKER = "当前用户消息："
from app.config import (
    get_deepseek_api_key,
    get_deepseek_base_url,
    get_deepseek_model,
    get_deepseek_timeout_seconds,
)
from app.llm_retry import call_with_retry
logger = logging.getLogger(__name__)
def _get_current_message(planner_input: str) -> str:  # 函数：从包含历史对话的规划输入中提取当前用户消息。
    if CURRENT_MESSAGE_MARKER not in planner_input:
        return planner_input

    return planner_input.rsplit(CURRENT_MESSAGE_MARKER, maxsplit=1)[1].strip()


def plan_tool_call_with_mock_llm(message: str) -> str:  # 函数：负责 plan 工具 调用 带 模拟 大模型 相关逻辑。
    current_message = _get_current_message(message)
    current_ticket_match = TICKET_ID_PATTERN.search(current_message)
    ticket_match = current_ticket_match or TICKET_ID_PATTERN.search(message)

    if ticket_match and (
            "删除工单" in current_message
            or "删掉工单" in current_message
            or "移除工单" in current_message
    ):
        return json.dumps(
            {
                "tool_name": "delete_ticket",
                "arguments": {
                    "ticket_id": ticket_match.group(0),
                },
            },
            ensure_ascii=False,
        )

    if ticket_match:
        return json.dumps(
            {
                "tool_name": "query_ticket_status",
                "arguments": {
                    "ticket_id": ticket_match.group(0),
                },
            },
            ensure_ascii=False,
        )

    if "创建工单" in message or "新建工单" in message:
        return json.dumps(
            {
                "tool_name": "create_ticket",
                "arguments": {
                    "message": message,
                },
            },
            ensure_ascii=False,
        )

    if "知识库" in message or "怎么" in message or "如何" in message:
        return json.dumps(
            {
                "tool_name": "search_knowledge_base",
                "arguments": {
                    "query": message,
                    "top_k": 3,
                },
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "tool_name": None,
            "arguments": {},
        },
        ensure_ascii=False,
    )


import os

from app.tool_prompt_builder import build_tool_selection_prompt
from app.tool_registry import list_openai_tools


def plan_tool_call_with_openai(message: str) -> str:  # 函数：负责 plan 工具 调用 带 OpenAI 相关逻辑。
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if not api_key:
        return json.dumps(
            {
                "tool_name": None,
                "arguments": {},
            },
            ensure_ascii=False,
        )

    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    timeout_seconds = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "10"))

    tools = list_openai_tools()
    prompt = build_tool_selection_prompt(message, tools)

    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        timeout=timeout_seconds,
        max_retries=0,
    )

    response = call_with_retry(
        lambda: client.responses.create(
            model=model,
            input=prompt,
        ),
        provider="openai",
        operation_name="tool_plan",
    )

    return response.output_text

def plan_tool_call_with_deepseek(message: str) -> str:  # 函数：调用 DeepSeek，根据用户消息选择并返回工具调用 JSON。
    api_key = get_deepseek_api_key()

    if not api_key:
        return json.dumps(
            {
                "tool_name": None,
                "arguments": {},
            },
            ensure_ascii=False,
        )

    model = get_deepseek_model()
    base_url = get_deepseek_base_url()
    timeout = get_deepseek_timeout_seconds()
    tools = list_openai_tools()
    prompt = build_tool_selection_prompt(message, tools)

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
        )

        logger.info(
            "deepseek_tool_plan_start model=%s timeout=%s",
            model,
            timeout,
        )

        response = call_with_retry(
            lambda: client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            ),
            provider="deepseek",
            operation_name="tool_plan",
        )

        llm_output = response.choices[0].message.content

        if not llm_output:
            raise ValueError("deepseek_empty_tool_plan")

        logger.info("deepseek_tool_plan_end model=%s", model)
        return llm_output

    except Exception as exc:
        logger.info("deepseek_tool_plan_failed error=%s", str(exc))
        return json.dumps(
            {
                "tool_name": None,
                "arguments": {},
            },
            ensure_ascii=False,
        )


def _to_native_tools(tools: list[dict]) -> list[dict]:  # 函数：把内部平铺 schema 转换为 OpenAI 原生 function calling 格式。
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool["parameters"],
            },
        }
        for tool in tools
    ]


def plan_tool_call_with_deepseek_native(message: str) -> str:  # 函数：原生 function calling：通过 tools 参数让 DeepSeek 返回结构化 tool_calls。
    api_key = get_deepseek_api_key()

    if not api_key:
        return json.dumps(
            {
                "tool_name": None,
                "arguments": {},
            },
            ensure_ascii=False,
        )

    model = get_deepseek_model()
    base_url = get_deepseek_base_url()
    timeout = get_deepseek_timeout_seconds()
    tools = _to_native_tools(list_openai_tools())


    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
        )

        logger.info("deepseek_native_tool_plan_start model=%s", model)

        response = call_with_retry(
            lambda: client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个企业 IT 支持助手。请根据用户消息选择合适的工具：用户提到 TICKET- 工单号时调用 query_ticket_status；用户想查知识库时调用 search_knowledge_base；用户想创建工单时调用 create_ticket；用户想删除工单时调用 delete_ticket。",
                    },
                    {
                        "role": "user",
                        "content": message,
                    }
                ],
                tools=tools,
                tool_choice="auto",
            ),
            provider="deepseek",
            operation_name="tool_plan_native",
        )

        choice = response.choices[0].message
        tool_calls = choice.tool_calls or []

        if not tool_calls:
            logger.info("deepseek_native_tool_plan_end no_tool_call")
            return json.dumps(
                {"tool_name": None, "arguments": {}},
                ensure_ascii=False,
            )

        tool_call = tool_calls[0]
        function_name = tool_call.function.name
        arguments_text = tool_call.function.arguments or "{}"

        logger.info("deepseek_native_tool_plan_end tool_name=%s", function_name)
        return json.dumps(
            {
                "tool_name": function_name,
                "arguments": json.loads(arguments_text),
            },
            ensure_ascii=False,
        )

    except Exception as exc:
        logger.info("deepseek_native_tool_plan_failed error=%s", str(exc))
        return json.dumps(
            {
                "tool_name": None,
                "arguments": {},
            },
            ensure_ascii=False,
        )
