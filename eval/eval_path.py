# 模块职责：评估脚本公共初始化模块：确保从项目根目录直接运行任意 eval 脚本时，Python 都优先导入当前项目的 backend/app，而不是外部同名包。

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"


def setup_backend_path() -> None:  # 函数：负责 setup backend 路径 相关逻辑。
    backend_path = str(BACKEND_DIR)

    if backend_path in sys.path:
        sys.path.remove(backend_path)

    sys.path.insert(0, backend_path)
