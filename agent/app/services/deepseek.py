from openai import OpenAI

from app.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


def get_client() -> OpenAI:
    """创建 DeepSeek 客户端（兼容 OpenAI SDK）。"""
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    response_format: dict | None = None,
) -> str:
    """调用 DeepSeek 对话接口，返回助手回复文本。

    response_format 传入 {"type": "json_object"} 时要求模型返回 JSON。
    """
    client = get_client()
    kwargs: dict = {
        "model": model or DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""
