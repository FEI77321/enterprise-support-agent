"""输入安全边界：用可解释、可回归的规则拦截常见 Prompt Injection。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SafetyDecision:
    action: str
    risk_level: str
    attack_types: list[str]
    reason: str

    def to_public_dict(self) -> dict[str, object]:
        return asdict(self)


_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("instruction_override", (r"忽略.{0,12}(之前|前面|系统|规则|指令|提示)", r"ignore\s+(all\s+)?previous", r"disregard\s+(the\s+)?(system|previous)")),
    ("prompt_exfiltration", (r"(系统|开发者|system|developer).{0,10}(提示|prompt|指令|message)", r"show\s+(me\s+)?(your|the)\s+(system|developer)")),
    ("privilege_escalation", (r"(我是|以)管理员", r"绕过.{0,8}(权限|审批|确认)", r"bypass.{0,12}(permission|approval)")),
    ("bulk_destructive_request", (r"删除.{0,8}(全部|所有).{0,8}(工单|数据|记录)", r"delete.{0,12}(all|every)")),
)


def assess_user_input(message: str) -> SafetyDecision:
    """识别高风险输入。规则命中即拒绝，避免由模型自行决定安全边界。"""
    matched: list[str] = []
    for attack_type, patterns in _PATTERNS:
        if any(re.search(pattern, message, flags=re.IGNORECASE) for pattern in patterns):
            matched.append(attack_type)

    if matched:
        return SafetyDecision(
            action="block",
            risk_level="high",
            attack_types=matched,
            reason="检测到可能改变系统边界、获取内部提示或绕过审批的输入。",
        )
    return SafetyDecision(
        action="allow",
        risk_level="low",
        attack_types=[],
        reason="未命中已知高风险输入规则。",
    )
