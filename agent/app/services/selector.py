import json

from pydantic import ValidationError

from app.schemas import EvaluateRequest, EvaluateResponse
from app.services.deepseek import AIError, chat

# 模型偶尔会输出英文档位，归一化为中文（前端按中文档位配色）
_LEVEL_ALIAS = {
    "reach": "冲刺",
    "match": "匹配",
    "safety": "保底",
    "safe": "保底",
}

_SYSTEM_PROMPT = """你是一位资深的留学选校顾问，擅长根据学生背景推荐海外院校。

请根据学生的 GPA、申请专业、目标国家以及其提供的其他背景信息（如本科院校档次、意向学位、语言成绩），推荐 6 所学校，分为三档：
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


def _extra_context(req: EvaluateRequest) -> str:
    """把已填写的选填背景拼进提示词，未填的维度不参与推荐。"""
    parts = []
    if req.school_tier:
        parts.append(f"本科院校档次 {req.school_tier}")
    if req.degree:
        parts.append(f"意向学位 {req.degree}")
    if req.language_score is not None:
        label = f"{req.language_type} " if req.language_type else ""
        parts.append(f"语言成绩 {label}{req.language_score:g}")
    if not parts:
        return ""
    return "其他背景：" + "，".join(parts) + "。"


def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    """调用 DeepSeek 生成三档选校推荐，解析为结构化响应。

    返回内容无法解析或缺少档位时抛 AIError（上层统一转 502），
    避免裸 500 直接暴露给前端。
    """
    user_prompt = (
        f"学生背景：GPA {req.gpa}，申请专业 {req.major}，目标国家 {req.target_country}。"
        f"{_extra_context(req)}"
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
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIError("AI 返回内容格式异常，请重试") from exc
    try:
        resp = EvaluateResponse.model_validate(data)
    except ValidationError as exc:
        raise AIError("AI 返回内容不完整，请重试") from exc
    if len(resp.tiers) != 3:
        raise AIError("AI 返回档位缺失，请重试")
    return _normalize_levels(resp)


# 前端按此顺序展示；同时用于校验三档齐全、无重复
_LEVEL_ORDER = ["冲刺", "匹配", "保底"]


def _normalize_levels(resp: EvaluateResponse) -> EvaluateResponse:
    """把模型偶尔输出的英文档位归一化为中文，并校验三档齐全后按固定顺序排序。

    模型偶发输出重复档位（如两个「冲刺」）或未知档位时抛 AIError，
    避免前端渲染出重复/缺失的档位卡片。
    """
    for tier in resp.tiers:
        tier.level = _LEVEL_ALIAS.get(tier.level.strip().lower(), tier.level.strip())
    levels = [tier.level for tier in resp.tiers]
    if set(levels) != set(_LEVEL_ORDER):
        raise AIError("AI 返回档位缺失，请重试")
    order = {level: i for i, level in enumerate(_LEVEL_ORDER)}
    resp.tiers.sort(key=lambda tier: order[tier.level])
    return resp
