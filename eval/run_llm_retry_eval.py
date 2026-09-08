# 模块职责：LLM 重试评估：验证临时错误指数退避重试、不可重试错误快速失败及最大尝试次数。

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.llm_retry import call_with_retry  # noqa: E402


class HttpError(Exception):
    """模拟带 HTTP 状态码的外部服务错误。"""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"http_{status_code}")


class APITimeoutError(Exception):
    """模拟 OpenAI SDK 的超时错误类型。"""


def with_retry_settings(callback):
    """为单个测试临时设置重试参数，结束后还原环境变量。"""
    names = (
        "LLM_RETRY_MAX_ATTEMPTS",
        "LLM_RETRY_BASE_DELAY_SECONDS",
        "LLM_RETRY_MAX_DELAY_SECONDS",
    )
    previous_values = {name: os.environ.get(name) for name in names}
    os.environ.update(
        {
            "LLM_RETRY_MAX_ATTEMPTS": "3",
            "LLM_RETRY_BASE_DELAY_SECONDS": "0.25",
            "LLM_RETRY_MAX_DELAY_SECONDS": "1",
        }
    )
    try:
        callback()
    finally:
        for name, value in previous_values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_retriable_error_uses_exponential_backoff() -> None:
    calls = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TimeoutError("temporary_timeout")
        return "success"

    def verify() -> None:
        result = call_with_retry(
            operation,
            provider="test",
            operation_name="retry_success",
            sleep_function=delays.append,
        )
        assert result == "success"
        assert calls == 3
        assert delays == [0.25, 0.5]

    with_retry_settings(verify)


def test_client_error_is_not_retried() -> None:
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise HttpError(401)

    def verify() -> None:
        try:
            call_with_retry(operation, provider="test", operation_name="auth")
        except HttpError:
            pass
        else:
            raise AssertionError("401 应直接抛出")
        assert calls == 1

    with_retry_settings(verify)


def test_retries_stop_at_max_attempts() -> None:
    calls = 0
    delays: list[float] = []

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise ConnectionError("temporary_connection_error")

    def verify() -> None:
        try:
            call_with_retry(
                operation,
                provider="test",
                operation_name="retry_exhausted",
                sleep_function=delays.append,
            )
        except ConnectionError:
            pass
        else:
            raise AssertionError("重试耗尽后应抛出最后一次错误")
        assert calls == 3
        assert delays == [0.25, 0.5]

    with_retry_settings(verify)


def test_sdk_timeout_error_is_retried() -> None:
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise APITimeoutError("sdk_timeout")
        return "success"

    def verify() -> None:
        assert call_with_retry(
            operation,
            provider="test",
            operation_name="sdk_timeout",
            sleep_function=lambda _delay: None,
        ) == "success"
        assert calls == 2

    with_retry_settings(verify)


def main() -> None:
    tests = [
        test_retriable_error_uses_exponential_backoff,
        test_client_error_is_not_retried,
        test_retries_stop_at_max_attempts,
        test_sdk_timeout_error_is_retried,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Passed: {len(tests)}/{len(tests)}")


if __name__ == "__main__":
    main()
