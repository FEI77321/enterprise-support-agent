# 模块职责：Redis 限流评估：验证固定窗口计数、超限等待时间和客户端 IP 脱敏键。

import asyncio
import os
import sys
from pathlib import Path

from starlette.requests import Request


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.rate_limiter import check_rate_limit, get_client_rate_limit_key  # noqa: E402


class FakeRedis:
    """使用内存计数模拟 Redis Lua 脚本返回值，避免评估依赖外部服务。"""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def eval(self, _script: str, _numkeys: int, key: str, _window: int):
        self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[key], 30]


def create_request(path: str = "/chat"):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "client": ("203.0.113.10", 12345),
        }
    )


def test_fixed_window_limit() -> None:
    previous_values = {
        name: os.environ.get(name)
        for name in ("RATE_LIMIT_ENABLED", "RATE_LIMIT_REQUESTS")
    }
    try:
        os.environ["RATE_LIMIT_ENABLED"] = "true"
        os.environ["RATE_LIMIT_REQUESTS"] = "2"
        redis_client = FakeRedis()
        request = create_request()
        decisions = [
            asyncio.run(check_rate_limit(request, redis_client))
            for _ in range(3)
        ]
        assert [decision.allowed for decision in decisions] == [True, True, False]
        assert decisions[0].remaining == 1
        assert decisions[1].remaining == 0
        assert decisions[-1].remaining == 0
        assert decisions[-1].retry_after_seconds == 30
    finally:
        for name, value in previous_values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_client_key_is_desensitized() -> None:
    key = get_client_rate_limit_key(create_request())
    assert key.startswith("rate_limit:ip:")
    assert "testclient" not in key


def main() -> None:
    tests = [test_fixed_window_limit, test_client_key_is_desensitized]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Passed: {len(tests)}/{len(tests)}")


if __name__ == "__main__":
    main()
