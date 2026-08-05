# 模块职责：验证 FastAPI 应用启动时会执行数据库初始化逻辑。

from unittest.mock import patch

from eval_path import setup_backend_path


setup_backend_path()

from fastapi.testclient import TestClient

import app.main as main_module


def test_api_startup_initializes_database() -> tuple[bool, str]:  # 测试函数：验证进入 FastAPI 生命周期时会调用 initialize_database。
    with patch(
        "app.main.initialize_database",
    ) as mocked_initialize_database:
        with TestClient(main_module.app) as client:
            response = client.get("/health")

        if response.status_code != 200:
            return False, f"期望健康检查状态码 200，实际为 {response.status_code}"

        if mocked_initialize_database.call_count != 1:
            return False, (
                "期望服务启动时调用 initialize_database 1 次，"
                f"实际调用 {mocked_initialize_database.call_count} 次"
            )

    return True, ""


def main() -> None:  # 函数：运行本文件中的 FastAPI 服务启动评估。
    tests = [
        (
            "api_startup_initializes_database",
            test_api_startup_initializes_database,
        ),
    ]

    passed = 0

    for name, test_func in tests:
        ok, reason = test_func()
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}")

        if ok:
            passed += 1
        else:
            print(f"  Reason: {reason}")

    print()
    print(f"Passed: {passed}/{len(tests)}")

    if passed != len(tests):
        raise SystemExit(1)


if __name__ == "__main__":
    main()