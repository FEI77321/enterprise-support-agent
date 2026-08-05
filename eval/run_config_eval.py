# 模块职责：配置评估：覆盖布尔与浮点环境变量的正常值、非法值和默认值，保证应用不会因部署配置格式变化而产生意外行为。

import os

from eval_path import setup_backend_path

setup_backend_path()

from app.config import get_bool_env, get_float_env


def check_bool_env(value: str | None, expected: bool) -> None:  # 函数：负责 check 布尔 环境变量 相关逻辑。
    key = "TEST_BOOL_ENV"

    old_value = os.environ.get(key)

    try:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

        actual = get_bool_env(key, default=False)
        assert actual == expected, f"value={value!r}, expected={expected}, got={actual}"

    finally:
        if old_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old_value


def check_float_env(value: str | None, default: float, expected: float) -> None:  # 函数：负责 check 浮点 环境变量 相关逻辑。
    key = "TEST_FLOAT_ENV"

    old_value = os.environ.get(key)

    try:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

        actual = get_float_env(key, default=default)
        assert actual == expected, f"value={value!r}, expected={expected}, got={actual}"

    finally:
        if old_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old_value


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    check_bool_env(None, False)
    check_bool_env("true", True)
    check_bool_env("True", True)
    check_bool_env("1", True)
    check_bool_env("yes", True)
    check_bool_env("on", True)
    check_bool_env("false", False)
    check_bool_env("0", False)
    check_bool_env("random", False)

    check_float_env(None, 20.0, 20.0)
    check_float_env("10", 20.0, 10.0)
    check_float_env("3.5", 20.0, 3.5)
    check_float_env("invalid", 20.0, 20.0)

    print("Config eval passed.")


if __name__ == "__main__":
    main()
