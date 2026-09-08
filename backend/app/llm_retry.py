# 模块职责：外部 LLM 调用重试：识别临时网络和服务端错误，以指数退避方式重试并记录每次尝试。

import logging
from collections.abc import Callable
from time import sleep
from typing import TypeVar

from app.config import (
    get_llm_retry_base_delay_seconds,
    get_llm_retry_max_attempts,
    get_llm_retry_max_delay_seconds,
)


logger = logging.getLogger(__name__)
ResultType = TypeVar("ResultType")


def is_retriable_llm_error(error: Exception) -> bool:
    """仅将网络超时、429 和 5xx 认定为可通过重试恢复的临时错误。"""
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True

    if type(error).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectTimeout",
        "ReadTimeout",
        "TimeoutException",
        "NetworkError",
    }:
        return True

    status_code = getattr(error, "status_code", None)
    return status_code == 429 or (isinstance(status_code, int) and status_code >= 500)


def call_with_retry(
    operation: Callable[[], ResultType],
    *,
    provider: str,
    operation_name: str,
    sleep_function: Callable[[float], None] = sleep,
) -> ResultType:
    """调用外部 LLM；仅对临时错误执行有限次指数退避重试。"""
    max_attempts = get_llm_retry_max_attempts()
    base_delay_seconds = max(get_llm_retry_base_delay_seconds(), 0.0)
    max_delay_seconds = max(get_llm_retry_max_delay_seconds(), base_delay_seconds)

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(
                "llm_call_attempt provider=%s operation=%s attempt=%s max_attempts=%s",
                provider,
                operation_name,
                attempt,
                max_attempts,
            )
            return operation()
        except Exception as exc:
            should_retry = (
                attempt < max_attempts and is_retriable_llm_error(exc)
            )
            if not should_retry:
                logger.warning(
                    "llm_call_failed provider=%s operation=%s attempt=%s "
                    "retriable=%s error_type=%s",
                    provider,
                    operation_name,
                    attempt,
                    is_retriable_llm_error(exc),
                    type(exc).__name__,
                )
                raise

            delay_seconds = min(
                base_delay_seconds * (2 ** (attempt - 1)),
                max_delay_seconds,
            )
            logger.warning(
                "llm_call_retry provider=%s operation=%s attempt=%s "
                "next_attempt=%s delay_seconds=%s error_type=%s",
                provider,
                operation_name,
                attempt,
                attempt + 1,
                delay_seconds,
                type(exc).__name__,
            )
            sleep_function(delay_seconds)

    raise RuntimeError("LLM 重试循环意外结束")
