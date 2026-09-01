from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

# 输入约束：自动去首尾空格 + 长度上限
Major = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Country = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Wechat = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=64)]
# 中国大陆手机号：1 开头共 11 位
Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^1[3-9]\d{9}$")]
GpaScale = Literal[4, 5, 100]
LanguageType = Literal["雅思", "托福", "托福（1–6分制）"]
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _validate_background(gpa, gpa_scale, language_type, language_score, target_country):
    def invalid(message):
        raise PydanticCustomError("background_input", message)

    if gpa is not None:
        if gpa_scale is None and gpa > 5:
            invalid("请填写 GPA 计分制")
        if gpa_scale is not None and gpa > gpa_scale:
            invalid(f"GPA / 均分不能超过所选满分 {gpa_scale}")
    if target_country and target_country.strip() == "其他":
        invalid("请填写具体的目标国家或地区")
    if bool(language_type) != (language_score is not None):
        invalid("语言类型和成绩需一起填写")
    if language_score is not None:
        minimum, maximum, step = {
            "雅思": (0, 9, 0.5),
            "托福": (0, 120, 1),
            "托福（1–6分制）": (1, 6, 0.5),
        }[language_type]
        if not minimum <= language_score <= maximum or language_score % step != 0:
            invalid(f"{language_type}成绩需为 {minimum}～{maximum}，以 {step:g} 分递增")


def _strip_optional(data, keys: tuple[str, ...]) -> None:
    """选填字段空字符串按未填处理，非空则去首尾空格。"""
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, str):
                data[key] = value.strip() or None


class EvaluateRequest(BaseModel):
    """选校测评输入：三项必填 + 四项选填背景（填了才参与推荐）。"""

    gpa: float = Field(..., ge=0.01, le=100, description="按原始计分制填写的 GPA / 均分")
    gpa_scale: GpaScale = Field(4, description="满分值；旧 API 请求未提供时按 4 分制处理")
    major: Major = Field(..., description="申请专业")
    target_country: Country = Field(..., description="目标国家")
    school_tier: str | None = Field(None, max_length=20, description="本科院校档次（选填）")
    degree: str | None = Field(None, max_length=10, description="意向学位（选填）")
    language_type: LanguageType | None = Field(None, description="语言成绩类型（选填）")
    language_score: float | None = Field(None, ge=0, le=120, description="语言成绩分数（选填）")

    @model_validator(mode="before")
    @classmethod
    def _normalize_optional(cls, data):
        _strip_optional(data, ("school_tier", "degree", "language_type"))
        return data

    @model_validator(mode="after")
    def _check_background(self):
        _validate_background(self.gpa, self.gpa_scale, self.language_type, self.language_score, self.target_country)
        return self


class School(BaseModel):
    name: NonBlank = Field(..., description="学校名称")
    reason: NonBlank = Field(..., description="推荐理由")


class Tier(BaseModel):
    level: str = Field(..., description="档位：冲刺 / 匹配 / 保底")
    schools: list[School] = Field(..., min_length=2, max_length=2, description="该档位学校列表（每档 2 所）")


class EvaluateResponse(BaseModel):
    tiers: list[Tier] = Field(..., description="三档推荐结果")
    report_id: UUID | None = Field(None, description="服务端保存的报告 ID，留资时用于关联")


class PreviewSchool(BaseModel):
    name: str


class PreviewTier(BaseModel):
    level: str
    schools: list[PreviewSchool]


class EvaluatePreviewResponse(BaseModel):
    tiers: list[PreviewTier]
    report_id: UUID


class LeadRequest(BaseModel):
    """留资输入：联系方式 + 测评背景。"""

    wechat: Wechat = Field(..., description="微信号")
    phone: Phone = Field(..., description="手机号")
    gpa: float | None = Field(None, ge=0.01, le=100, description="测评时的 GPA / 均分")
    gpa_scale: GpaScale | None = Field(None, description="成绩满分值；历史记录可缺省")
    major: str | None = Field(None, max_length=50, description="申请专业")
    target_country: str | None = Field(None, max_length=30, description="目标国家")
    school_tier: str | None = Field(None, max_length=20, description="本科院校档次")
    degree: str | None = Field(None, max_length=10, description="意向学位")
    language_type: LanguageType | None = Field(None, description="语言成绩类型")
    language_score: float | None = Field(None, ge=0, le=120, description="语言成绩分数")
    report_id: UUID | None = Field(None, description="测评接口返回的报告 ID")

    @model_validator(mode="before")
    @classmethod
    def _normalize_optional(cls, data):
        _strip_optional(data, ("major", "target_country", "school_tier", "degree", "language_type"))
        return data

    @model_validator(mode="after")
    def _check_background(self):
        _validate_background(self.gpa, self.gpa_scale, self.language_type, self.language_score, self.target_country)
        return self


class LeadResponse(BaseModel):
    id: int = Field(..., description="留资记录 id")
    message: str = Field(..., description="处理结果")
    report: EvaluateResponse | None = None
