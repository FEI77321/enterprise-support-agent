# 模块职责：Redis 分布式限流：通过 Lua 脚本原子地计数和设置过期时间，按客户端 IP 限制 API 请求频率。

import hashlib
import logging
from dataclasses import dataclass

from fastapi import Request
from redis.asyncio import Redis

from app.config import (
    get_rate_limit_requests,
    get_rate_limit_window_seconds,
    is_rate_limit_enabled,
    is_rate_limit_fail_open,
)
from app.redis_client import get_redis_client


logger = logging.getLogger(__name__)

_RATE_LIMIT_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""

_PROTECTED_PATHS = {"/chat", "/chat/stream"}


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0
    limit: int | None = None
    remaining: int | None = None
    reset_after_seconds: int | None = None


def requires_rate_limit(path: str) -> bool:
    """仅限制聊天入口，避免限制健康检查、工单管理和运维接口。"""
    return path in _PROTECTED_PATHS


def get_client_rate_limit_key(request: Request) -> str:
    """根据直连客户端 IP 生成脱敏 Redis 键，不信任可伪造的转发头。"""
    client_ip = request.client.host if request.client else "unknown"
    client_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:24]
    return f"rate_limit:ip:{client_hash}"


async def check_rate_limit(
    request: Request,
    redis_client: Redis | None = None,
) -> RateLimitDecision:
    """执行固定窗口限流，并在超限时返回客户端应等待的秒数。"""
    if not is_rate_limit_enabled():
        return RateLimitDecision(allowed=True)

    try:
        client = redis_client or get_redis_client()
        current_count, ttl = await client.eval(
            _RATE_LIMIT_LUA,
            1,
            get_client_rate_limit_key(request),
            get_rate_limit_window_seconds(),
        )
    except Exception:
        logger.exception("rate_limit_check_failed")
        if is_rate_limit_fail_open():
            return RateLimitDecision(allowed=True)
        raise

    limit = get_rate_limit_requests()
    reset_after_seconds = max(int(ttl), 0)
    if int(current_count) <= limit:
        return RateLimitDecision(
            allowed=True,
            limit=limit,
            remaining=max(limit - int(current_count), 0),
            reset_after_seconds=reset_after_seconds,
        )

    return RateLimitDecision(
        allowed=False,
        retry_after_seconds=max(reset_after_seconds, 1),
        limit=limit,
        remaining=0,
        reset_after_seconds=reset_after_seconds,
    )
