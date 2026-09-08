# 模块职责：环境变量配置读取模块：把字符串形式的环境变量安全转换为布尔值、浮点数以及 OpenAI、DeepSeek 等模型配置，避免配置错误散落在业务代码中。

import os
from pathlib import Path


def get_bool_env(name: str, default: bool = False) -> bool:  # 函数：负责 获取 布尔 环境变量 相关逻辑。
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}

def is_llm_answer_enabled() -> bool:  # 函数：负责 is 大模型 回答 enabled 相关逻辑。
    return get_bool_env("ENABLE_LLM_ANSWER", default=False)


def is_ingested_knowledge_experiment_enabled() -> bool:
    """是否启用 RAG 2.0 SQLite 检索实验入口，默认严格关闭。"""

    return get_bool_env(
        "INGESTED_KNOWLEDGE_EXPERIMENT_ENABLED",
        default=False,
    )


def get_ingested_knowledge_database_path() -> Path:
    """读取实验检索数据库位置，默认复用项目 SQLite 数据库。"""

    default_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "enterprise_support_agent.db"
    )
    configured_path = os.getenv(
        "INGESTED_KNOWLEDGE_DATABASE_PATH",
        str(default_path),
    )
    return Path(configured_path)


def get_llm_provider() -> str:  # 函数：负责 获取 大模型 Provider 相关逻辑。
    return os.getenv("LLM_PROVIDER", "stub").lower()


def get_openai_api_key() -> str | None:  # 函数：负责 获取 OpenAI API key 相关逻辑。
    return os.getenv("OPENAI_API_KEY")


def get_openai_model() -> str:  # 函数：负责 获取 OpenAI 数据模型 相关逻辑。
    return os.getenv("OPENAI_MODEL", "gpt-5")


def get_float_env(name: str, default: float) -> float:  # 函数：负责 获取 浮点 环境变量 相关逻辑。
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return float(value)
    except ValueError:
        return default


def is_redis_enabled() -> bool:
    """判断是否启用依赖 Redis 的可选能力。"""
    return get_bool_env("REDIS_ENABLED", default=False)


def get_redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")


def get_redis_connect_timeout_seconds() -> float:
    return get_float_env("REDIS_CONNECT_TIMEOUT_SECONDS", default=2.0)


def get_redis_socket_timeout_seconds() -> float:
    return get_float_env("REDIS_SOCKET_TIMEOUT_SECONDS", default=2.0)


def get_int_env(name: str, default: int, minimum: int = 1) -> int:
    """读取正整数环境变量；缺失、格式错误或小于下限时使用默认值。"""
    value = os.getenv(name)
    if value is None:
        return default

    try:
        parsed_value = int(value)
    except ValueError:
        return default

    return parsed_value if parsed_value >= minimum else default


def is_rate_limit_enabled() -> bool:
    """判断是否启用 Redis 分布式限流。"""
    return get_bool_env("RATE_LIMIT_ENABLED", default=False)


def get_rate_limit_requests() -> int:
    """返回每个时间窗口允许的最大请求数。"""
    return get_int_env("RATE_LIMIT_REQUESTS", default=60)


def get_rate_limit_window_seconds() -> int:
    """返回限流时间窗口长度，单位为秒。"""
    return get_int_env("RATE_LIMIT_WINDOW_SECONDS", default=60)


def is_rate_limit_fail_open() -> bool:
    """Redis 短暂不可用时，是否放行请求以优先保证服务可用性。"""
    return get_bool_env("RATE_LIMIT_FAIL_OPEN", default=True)


def get_llm_retry_max_attempts() -> int:
    """返回一次外部 LLM 调用最多尝试次数，包含首次调用。"""
    return get_int_env("LLM_RETRY_MAX_ATTEMPTS", default=3)


def get_llm_retry_base_delay_seconds() -> float:
    """返回 LLM 重试的初始等待时间，单位为秒。"""
    return get_float_env("LLM_RETRY_BASE_DELAY_SECONDS", default=0.5)


def get_llm_retry_max_delay_seconds() -> float:
    """返回 LLM 重试等待时间的最大值，单位为秒。"""
    return get_float_env("LLM_RETRY_MAX_DELAY_SECONDS", default=4.0)


def get_openai_timeout_seconds() -> float:  # 函数：负责 获取 OpenAI timeout seconds 相关逻辑。
    return get_float_env("OPENAI_TIMEOUT_SECONDS", default=20.0)


def get_deepseek_api_key() -> str | None:  # 函数：获取 DeepSeek API Key。
    return os.getenv("DEEPSEEK_API_KEY")


def get_deepseek_model() -> str:  # 函数：获取 DeepSeek 模型名称。
    return os.getenv(
        "DEEPSEEK_MODEL",
        "deepseek-v4-flash",
    )


def get_deepseek_base_url() -> str:  # 函数：获取 DeepSeek OpenAI 兼容接口地址。
    return os.getenv(
        "DEEPSEEK_BASE_URL",
        "https://api.deepseek.com",
    )


def get_deepseek_timeout_seconds() -> float:  # 函数：获取 DeepSeek 调用超时时间。
    return get_float_env(
        "DEEPSEEK_TIMEOUT_SECONDS",
        default=20.0,
    )

def get_agent_engine() -> str:  # 函数：获取 Agent 编排引擎：rules=if/else 版，langgraph=状态图版。
    return os.getenv("AGENT_ENGINE", "rules").lower()
