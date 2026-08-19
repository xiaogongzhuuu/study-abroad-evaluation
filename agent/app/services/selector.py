import json

from app.schemas import EvaluateRequest, EvaluateResponse
from app.services.deepseek import chat

_SYSTEM_PROMPT = """你是一位资深的留学选校顾问，擅长根据学生背景推荐海外院校。

请根据学生的 GPA、申请专业和目标国家，推荐 6 所学校，分为三档：
- 冲刺（reach）：录取有一定难度的学校，2 所
- 匹配（match）：与学生背景较匹配的学校，2 所
- 保底（safety）：录取把握较大的学校，2 所

要求：
1. 学校必须是真实存在的正规院校，并符合目标国家。
2. 推荐理由要具体、有针对性，结合该学生的 GPA 和专业说明，40 字以内。
3. 严格按以下 JSON 格式输出，不要输出任何其他文字或 Markdown 代码块：

{
  "tiers": [
    {"level": "冲刺", "schools": [{"name": "学校名", "reason": "理由"}, {"name": "学校名", "reason": "理由"}]},
    {"level": "匹配", "schools": [{"name": "学校名", "reason": "理由"}, {"name": "学校名", "reason": "理由"}]},
    {"level": "保底", "schools": [{"name": "学校名", "reason": "理由"}, {"name": "学校名", "reason": "理由"}]}
  ]
}"""


def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    """调用 DeepSeek 生成三档选校推荐，解析为结构化响应。"""
    user_prompt = (
        f"学生背景：GPA {req.gpa}，申请专业 {req.major}，目标国家 {req.target_country}。"
        f"请返回三档共 6 所学校的推荐 JSON。"
    )
    raw = chat(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.5,
        response_format={"type": "json_object"},
    )
    data = json.loads(raw)
    return EvaluateResponse.model_validate(data)
