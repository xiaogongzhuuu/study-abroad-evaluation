import time

from openai import AuthenticationError, OpenAI

from app.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

# 单次请求超时（秒）；DeepSeek 选校生成较慢，放宽到 60s
_TIMEOUT = 60.0
# 失败重试次数（共 1 + 2 次尝试），间隔 1s、2s 递增
_MAX_RETRIES = 2


class AIError(Exception):
    """AI 服务不可用或返回内容无法解析，统一由上层转 502。"""


def get_client() -> OpenAI:
    """创建 DeepSeek 客户端（兼容 OpenAI SDK）。

    max_retries=0：重试逻辑在 chat() 里自行控制，避免 SDK 内部再叠加。
    """
    return OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        timeout=_TIMEOUT,
        max_retries=0,
    )


def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    response_format: dict | None = None,
) -> str:
    """调用 DeepSeek 对话接口，返回助手回复文本。

    response_format 传入 {"type": "json_object"} 时要求模型返回 JSON。
    超时/连接/服务端错误自动重试；认证错误直接抛出；重试耗尽抛 AIError。
    """
    client = get_client()
    kwargs: dict = {
        "model": model or DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except AuthenticationError as exc:
            raise AIError("AI 服务认证失败，请联系管理员") from exc
        except Exception as exc:
            last_exc = exc
            if attempt == _MAX_RETRIES:
                break
            time.sleep(attempt + 1)
    raise AIError("AI 服务暂时不可用，请稍后重试") from last_exc
