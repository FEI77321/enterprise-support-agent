# 模块职责：大模型客户端封装：统一选择 OpenAI、DeepSeek 或本地 Stub，并将调用结果转换为稳定的 LLMAnswerResult，供 Agent 进行引用校验和规则降级。

import logging

from dataclasses import dataclass


from app.config import (
    get_deepseek_api_key,
    get_deepseek_base_url,
    get_deepseek_model,
    get_deepseek_timeout_seconds,
    get_llm_provider,
    get_openai_api_key,
    get_openai_model,
    get_openai_timeout_seconds,
)
from app.llm_retry import call_with_retry
@dataclass
class LLMAnswerResult:  # 类：封装大模型回答文本、可用状态和失败原因。
    answer: str
    success: bool
    provider: str
    error_reason: str | None = None


logger = logging.getLogger(__name__)

def generate_answer_result(prompt: str) -> LLMAnswerResult:  # 函数：负责 生成 回答 结果 相关逻辑。
    provider = get_llm_provider()

    if provider == "stub":
        logger.info("llm_provider_stub")
        return LLMAnswerResult(
            answer=generate_stub_answer(prompt),
            success=True,
            provider=provider,
        )

    if provider == "openai":
        api_key = get_openai_api_key()

        if not api_key:
            logger.info("openai_api_key_missing")
            return LLMAnswerResult(
                answer=generate_fallback_answer(),
                success=False,
                provider=provider,
                error_reason="api_key_missing",
            )

        try:
            from openai import OpenAI

            model = get_openai_model()
            timeout = get_openai_timeout_seconds()
            client = OpenAI(api_key=api_key, timeout=timeout, max_retries=0)
            logger.info("openai_call_start model=%s timeout=%s", model, timeout)

            response = call_with_retry(
                lambda: client.responses.create(
                    model=model,
                    input=prompt,
                ),
                provider=provider,
                operation_name="answer",
            )
            logger.info("openai_call_end model=%s", model)

            return LLMAnswerResult(
                answer=response.output_text,
                success=True,
                provider=provider,
            )

        except Exception as exc:
            logger.info("openai_call_failed error=%s", str(exc))
            return LLMAnswerResult(
                answer=generate_fallback_answer(),
                success=False,
                provider=provider,
                error_reason="openai_call_failed",
            )

    if provider == "deepseek":
        api_key = get_deepseek_api_key()

        if not api_key:
            logger.info("deepseek_api_key_missing")
            return LLMAnswerResult(
                answer=generate_fallback_answer(),
                success=False,
                provider=provider,
                error_reason="api_key_missing",
            )

        try:
            from openai import OpenAI

            model = get_deepseek_model()
            base_url = get_deepseek_base_url()
            timeout = get_deepseek_timeout_seconds()

            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                max_retries=0,
            )

            logger.info(
                "deepseek_call_start model=%s timeout=%s",
                model,
                timeout,
            )

            response = call_with_retry(
                lambda: client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                ),
                provider=provider,
                operation_name="answer",
            )

            answer = response.choices[0].message.content

            if not answer:
                raise ValueError("deepseek_empty_answer")

            logger.info("deepseek_call_end model=%s", model)

            return LLMAnswerResult(
                answer=answer,
                success=True,
                provider=provider,
            )

        except Exception as exc:
            logger.info("deepseek_call_failed error=%s", str(exc))
            return LLMAnswerResult(
                answer=generate_fallback_answer(),
                success=False,
                provider=provider,
                error_reason="deepseek_call_failed",
            )

        # 后面继续粘贴 DeepSeek 的完整处理代码……
    logger.info("llm_provider_unknown provider=%s", provider)
    return LLMAnswerResult(
        answer=generate_fallback_answer(),
        success=False,
        provider=provider,
        error_reason="unknown_provider",
    )


def generate_answer(prompt: str) -> str:  # 函数：负责 生成 回答 相关逻辑。
    return generate_answer_result(prompt).answer


def generate_stub_answer(prompt: str) -> str:  # 函数：负责 生成 模拟回答 回答 相关逻辑。
    return (
        "这是 LLM Client Stub 返回的占位回答。"
        "当前版本尚未接入真实大模型。"
    )

def generate_openai_answer(prompt: str) -> str:  # 函数：负责 生成 OpenAI 回答 相关逻辑。
    api_key = get_openai_api_key()

    if not api_key:
        logger.info("openai_api_key_missing")
        return generate_fallback_answer()

    try:
        from openai import OpenAI

        model = get_openai_model()
        timeout = get_openai_timeout_seconds()
        client = OpenAI(api_key=api_key, timeout=timeout, max_retries=0)
        logger.info("openai_call_start model=%s timeout=%s", model, timeout)

        response = call_with_retry(
            lambda: client.responses.create(
                model=model,
                input=prompt,
            ),
            provider="openai",
            operation_name="answer",
        )
        logger.info("openai_call_end model=%s", model)
        return response.output_text

    except Exception as exc:
        logger.info("openai_call_failed error=%s", str(exc))
        return generate_fallback_answer()

def generate_fallback_answer() -> str:  # 函数：负责 生成 fallback 回答 相关逻辑。
    return "当前大模型服务暂不可用，请稍后再试。"
