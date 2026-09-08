# 模块职责：工具调用解析与校验模块：检查模型输出是否为合法 JSON、工具名是否存在、参数是否符合工具 schema，并将失败原因结构化返回。

import json
from typing import Any
from app.tool_registry import TOOL_REGISTRY
from pydantic import BaseModel


class ToolCallParseResult(BaseModel):  # 类：封装工具调用 JSON 的解析和参数校验结果。
    success: bool
    tool_name: str | None = None
    arguments: dict[str, Any] = {}
    error_type: str | None = None
    error: str | None = None


def _get_required_parameters(tool_name: str) -> set[str]:  # 函数：负责 获取 必填 parameters 相关逻辑。
    tool = TOOL_REGISTRY[tool_name]

    return {
        parameter_name
        for parameter_name in tool.parameters.keys()
        if parameter_name != "top_k"
    }


def validate_tool_arguments(
    result: ToolCallParseResult,
) -> ToolCallParseResult:  # 函数：负责 校验 工具 参数 相关逻辑。
    if not result.success:
        return result

    if result.tool_name is None:
        return result

    if result.tool_name not in TOOL_REGISTRY:
        return validate_tool_call(result)

    required_parameters = _get_required_parameters(result.tool_name)
    missing_arguments = required_parameters - set(result.arguments.keys())

    if missing_arguments:
        return ToolCallParseResult(
            success=False,
            tool_name=result.tool_name,
            arguments=result.arguments,
            error_type="missing_arguments",
            error=f"Missing required arguments: {sorted(missing_arguments)}",
        )

    return result


def validate_tool_call(
    result: ToolCallParseResult,
) -> ToolCallParseResult:  # 函数：负责 校验 工具 调用 相关逻辑。
    if not result.success:
        return result

    if result.tool_name is None:
        return result

    if result.tool_name not in TOOL_REGISTRY:
        return ToolCallParseResult(
            success=False,
            tool_name=result.tool_name,
            arguments=result.arguments,
            error_type="unknown_tool",
            error=f"Unknown tool: {result.tool_name}",
        )

    return result

def parse_and_validate_tool_call(text: str) -> ToolCallParseResult:  # 函数：负责 解析 and 校验 工具 调用 相关逻辑。
    result = parse_tool_call(text)
    result = validate_tool_call(result)
    return validate_tool_arguments(result)


def parse_tool_call(text: str) -> ToolCallParseResult:  # 函数：负责 解析 工具 调用 相关逻辑。
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return ToolCallParseResult(
            success=False,
            error_type="invalid_json",
            error=str(exc),
        )

    if not isinstance(data, dict):
        return ToolCallParseResult(
            success=False,
            error_type="invalid_shape",
            error="tool call output must be a JSON object",
        )

    tool_name = data.get("tool_name")

    # 部分模型会把 JSON null 误输出为字符串 "null"；按无工具调用处理。
    if isinstance(tool_name, str) and tool_name.strip().lower() == "null":
        tool_name = None

    if tool_name is not None and not isinstance(tool_name, str):
        return ToolCallParseResult(
            success=False,
            error_type="invalid_tool_name",
            error="tool_name must be a string or null",
        )

    arguments = data.get("arguments", {})

    if not isinstance(arguments, dict):
        return ToolCallParseResult(
            success=False,
            error_type="invalid_arguments",
            error="arguments must be an object",
        )

    return ToolCallParseResult(
        success=True,
        tool_name=tool_name,
        arguments=arguments,
    )
