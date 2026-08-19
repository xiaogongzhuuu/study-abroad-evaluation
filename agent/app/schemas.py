from pydantic import BaseModel, Field


class EvaluateRequest(BaseModel):
    """选校测评输入。"""

    gpa: float = Field(..., ge=0, le=5, description="GPA（4 分制或 5 分制，由模型自行判断）")
    major: str = Field(..., min_length=1, description="申请专业")
    target_country: str = Field(..., min_length=1, description="目标国家")


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

    wechat: str = Field(..., min_length=1, description="微信号")
    phone: str = Field(..., min_length=1, description="手机号")
    gpa: float | None = Field(None, ge=0, le=5, description="测评时的 GPA")
    major: str | None = Field(None, description="申请专业")
    target_country: str | None = Field(None, description="目标国家")


class LeadResponse(BaseModel):
    id: int = Field(..., description="留资记录 id")
    message: str = Field(..., description="处理结果")
