# 模块职责：定义不同工具的操作风险等级，判断某个工具执行前是否必须经过用户确认。

from pydantic import BaseModel


class ToolActionPolicy(BaseModel):  # 类：描述一个工具是否需要用户确认，以及需要确认的原因。
    requires_confirmation: bool
    reason: str | None = None


def get_tool_action_policy(tool_name: str) -> ToolActionPolicy:  # 函数：根据工具名称返回该工具的执行确认策略。
    if tool_name == "delete_ticket":
        return ToolActionPolicy(
            requires_confirmation=True,
            reason="删除工单会永久移除数据，需要用户确认。",
        )

    return ToolActionPolicy(
        requires_confirmation=False,
    )