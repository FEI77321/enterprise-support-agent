# 模块职责：Redis 连接生命周期管理：在启用时建立单例异步连接，供后续限流、会话和缓存能力复用。

import logging

from redis.asyncio import Redis

from app.config import (
    get_redis_connect_timeout_seconds,
    get_redis_socket_timeout_seconds,
    get_redis_url,
    is_redis_enabled,
)


logger = logging.getLogger(__name__)
_redis_client: Redis | None = None


async def initialize_redis_connection() -> None:
    """应用启动时在启用 Redis 的情况下建立一次连接。"""
    global _redis_client

    if not is_redis_enabled():
        logger.info("redis_disabled")
        return

    if _redis_client is not None:
        return

    client = Redis.from_url(
        get_redis_url(),
        decode_responses=True,
        socket_connect_timeout=get_redis_connect_timeout_seconds(),
        socket_timeout=get_redis_socket_timeout_seconds(),
    )
    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        logger.exception("redis_connection_failed")
        raise RuntimeError("Redis is enabled but unavailable") from exc

    _redis_client = client
    logger.info("redis_connection_ready")


def get_redis_client() -> Redis:
    """返回已初始化的客户端，供请求处理器和后续中间件使用。"""
    if _redis_client is None:
        raise RuntimeError("Redis client is not initialized")
    return _redis_client


async def get_redis_health_status() -> dict[str, str]:
    """返回不暴露连接细节的简要健康状态。"""
    if not is_redis_enabled():
        return {"status": "disabled"}

    if _redis_client is None:
        return {"status": "unavailable"}

    try:
        await _redis_client.ping()
    except Exception:
        logger.exception("redis_health_check_failed")
        return {"status": "unavailable"}

    return {"status": "ok"}


async def close_redis_connection() -> None:
    """应用正常停止时关闭共享客户端。"""
    global _redis_client

    if _redis_client is None:
        return

    await _redis_client.aclose()
    _redis_client = None
    logger.info("redis_connection_closed")
