"""受控 Query Rewrite：只做白名单别名归一化，并保护精确业务实体。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class QueryRewriteDecision:
    triggered: bool
    original_query: str
    effective_query: str
    reason: str
    protected_entities: list[str]

    def to_public_dict(self) -> dict[str, object]:
        return asdict(self)


_PROTECTED_ENTITY = re.compile(r"\bTICKET-\d{8}-\d{4}\b|\b(?:VPN\s*)?(?:691|720)\b", re.IGNORECASE)
_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("内网打不开", "内网上不去", "内网连不上"), "VPN 远程访问 无法连接"),
    (("vpn连不上", "VPN 连不上", "vpn连接失败"), "VPN 无法连接 排查"),
    (("报销咋整", "报销怎么弄", "报销如何操作"), "报销申请流程 发票 审批"),
    (("账号登不上", "账号不行", "登录不了"), "账号 登录 密码 MFA"),
)


def rewrite_query(query: str) -> QueryRewriteDecision:
    """返回原始/有效查询和理由，禁止以黑盒方式改写工单 ID、错误码。"""
    protected = _PROTECTED_ENTITY.findall(query)
    if protected:
        return QueryRewriteDecision(False, query, query, "protected_entity", protected)

    normalized = query.strip()
    lowered = normalized.lower()
    for aliases, replacement in _ALIASES:
        if any(alias.lower() in lowered for alias in aliases):
            return QueryRewriteDecision(True, query, replacement, "alias_normalization", [])
    return QueryRewriteDecision(False, query, query, "no_safe_rewrite", [])
