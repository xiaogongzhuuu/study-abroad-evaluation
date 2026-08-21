from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

# 输入约束：自动去首尾空格 + 长度上限
Major = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Country = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Wechat = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=64)]
# 中国大陆手机号：1 开头共 11 位
Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^1[3-9]\d{9}$")]


def _strip_optional(data, keys: tuple[str, ...]) -> None:
    """选填字段空字符串按未填处理，非空则去首尾空格。"""
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, str):
                data[key] = value.strip() or None


class EvaluateRequest(BaseModel):
    """选校测评输入：三项必填 + 四项选填背景（填了才参与推荐）。"""

    gpa: float = Field(..., ge=0.01, le=5, description="GPA（4 分制或 5 分制，由模型自行判断）")
    major: Major = Field(..., description="申请专业")
    target_country: Country = Field(..., description="目标国家")
    school_tier: str | None = Field(None, max_length=20, description="本科院校档次（选填）")
    degree: str | None = Field(None, max_length=10, description="意向学位（选填）")
    language_type: str | None = Field(None, max_length=20, description="语言成绩类型（选填）")
    language_score: float | None = Field(None, ge=0.5, le=200, description="语言成绩分数（选填）")

    @model_validator(mode="before")
    @classmethod
    def _normalize_optional(cls, data):
        _strip_optional(data, ("school_tier", "degree", "language_type"))
        return data


class School(BaseModel):
    name: str = Field(..., description="学校名称")
    reason: str = Field(..., description="推荐理由")


class Tier(BaseModel):
    level: str = Field(..., description="档位：冲刺 / 匹配 / 保底")
    schools: list[School] = Field(..., description="该档位学校列表（每档 2 所）")


class EvaluateResponse(BaseModel):
    tiers: list[Tier] = Field(..., description="三档推荐结果")


class LeadRequest(BaseModel):
    """留资输入：联系方式 + 测评背景。"""

    wechat: Wechat = Field(..., description="微信号")
    phone: Phone = Field(..., description="手机号")
    gpa: float | None = Field(None, ge=0.01, le=5, description="测评时的 GPA")
    major: str | None = Field(None, max_length=50, description="申请专业")
    target_country: str | None = Field(None, max_length=30, description="目标国家")
    school_tier: str | None = Field(None, max_length=20, description="本科院校档次")
    degree: str | None = Field(None, max_length=10, description="意向学位")
    language_type: str | None = Field(None, max_length=20, description="语言成绩类型")
    language_score: float | None = Field(None, ge=0.5, le=200, description="语言成绩分数")

    @model_validator(mode="before")
    @classmethod
    def _normalize_optional(cls, data):
        _strip_optional(data, ("major", "target_country", "school_tier", "degree", "language_type"))
        return data


class LeadResponse(BaseModel):
    id: int = Field(..., description="留资记录 id")
    message: str = Field(..., description="处理结果")
