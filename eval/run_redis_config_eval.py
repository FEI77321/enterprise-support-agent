# 模块职责：Redis 配置评估：验证默认关闭策略、环境变量覆盖和关闭状态下的健康检查契约。

import asyncio
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import get_redis_url, is_redis_enabled  # noqa: E402
from app.redis_client import get_redis_health_status  # noqa: E402


def test_config_overrides() -> None:
    previous_enabled = os.environ.get("REDIS_ENABLED")
    previous_url = os.environ.get("REDIS_URL")
    try:
        os.environ["REDIS_ENABLED"] = "true"
        os.environ["REDIS_URL"] = "redis://example.test:6380/3"
        assert is_redis_enabled() is True
        assert get_redis_url() == "redis://example.test:6380/3"
    finally:
        if previous_enabled is None:
            os.environ.pop("REDIS_ENABLED", None)
        else:
            os.environ["REDIS_ENABLED"] = previous_enabled
        if previous_url is None:
            os.environ.pop("REDIS_URL", None)
        else:
            os.environ["REDIS_URL"] = previous_url


def test_disabled_health_contract() -> None:
    previous_enabled = os.environ.get("REDIS_ENABLED")
    try:
        os.environ["REDIS_ENABLED"] = "false"
        assert asyncio.run(get_redis_health_status()) == {"status": "disabled"}
    finally:
        if previous_enabled is None:
            os.environ.pop("REDIS_ENABLED", None)
        else:
            os.environ["REDIS_ENABLED"] = previous_enabled


def main() -> None:
    tests = [test_config_overrides, test_disabled_health_contract]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Passed: {len(tests)}/{len(tests)}")


if __name__ == "__main__":
    main()
