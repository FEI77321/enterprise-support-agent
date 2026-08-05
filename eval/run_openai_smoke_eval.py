# 模块职责：真实 OpenAI 冒烟评估：在已配置 API Key 的前提下验证一次端到端调用；不配置 Key 时可用于确认降级提示。

import os

from eval_path import setup_backend_path

setup_backend_path()

from app.llm_client import generate_openai_answer


def main() -> None:  # 函数：运行本文件定义的主流程或全部评估。
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        print("SKIP openai_smoke: OPENAI_API_KEY is not set.")
        print("请先在本地环境变量中配置 OPENAI_API_KEY，再运行真实 OpenAI smoke test。")
        return

    prompt = (
        "你是一个企业 IT 支持助手。"
        "请用一句话回答：VPN 720 错误通常和什么有关？"
    )

    answer = generate_openai_answer(prompt)

    if not answer:
        print("FAIL openai_smoke: answer is empty.")
        raise SystemExit(1)

    if "暂不可用" in answer:
        print(f"FAIL openai_smoke: got fallback answer: {answer}")
        raise SystemExit(1)

    print("PASS openai_smoke")
    print("Answer:")
    print(answer)


if __name__ == "__main__":
    main()
