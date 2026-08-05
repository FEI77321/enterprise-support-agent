# 模块职责：日志初始化模块：配置项目统一的日志等级、时间格式和输出格式，让 API、Agent 与工具执行过程可以被追踪。

import logging


def configure_logging() -> None:  # 函数：负责 configure logging 相关逻辑。
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
