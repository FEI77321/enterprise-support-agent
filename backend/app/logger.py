# 模块职责：日志初始化模块：配置项目统一的日志等级、时间格式和输出格式，让 API、Agent 与工具执行过程可以被追踪。

import logging

from app.observability import RequestIdFilter


def configure_logging() -> None:  # 函数：负责 configure logging 相关逻辑。
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname)s "
            "request_id=%(request_id)s "
            "[%(name)s] %(message)s"
        ),
    )

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if not any(
            isinstance(log_filter, RequestIdFilter)
            for log_filter in handler.filters
        ):
            handler.addFilter(RequestIdFilter())
