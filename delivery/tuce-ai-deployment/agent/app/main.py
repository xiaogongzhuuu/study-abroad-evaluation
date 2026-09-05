import hmac
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    ADMIN_TOKEN,
    EVALUATE_RATE_LIMIT,
    LEAD_RATE_LIMIT,
    RATE_LIMIT_WINDOW_SECONDS,
)
from app.db import clear_leads, get_report, init_db, insert_lead, insert_report, list_leads
from app.rate_limit import rate_limiter
from app.schemas import EvaluateRequest, EvaluateResponse, EvaluatePreviewResponse, LeadRequest, LeadResponse
from app.services.deepseek import AIError, chat
from app.services.notify import notify_new_lead
from app.services.selector import evaluate

logger = logging.getLogger(__name__)

# 字段中文名，用于把 Pydantic 校验错误翻译成可读提示
_FIELD_LABELS = {
    "gpa": "GPA",
    "gpa_scale": "GPA 计分制",
    "major": "申请专业",
    "target_country": "目标国家",
    "school_tier": "本科院校档次",
    "degree": "意向学位",
    "language_type": "语言类型",
    "language_score": "语言成绩",
    "wechat": "微信号",
    "phone": "手机号",
}


def _validation_message(exc: RequestValidationError) -> str:
    """取第一条校验错误，拼成一句中文提示返回。"""
    err = exc.errors()[0] if exc.errors() else {}
    loc = err.get("loc", ())
    field = str(loc[-1]) if loc else "参数"
    label = _FIELD_LABELS.get(field, field)
    etype = err.get("type", "")
    if etype == "background_input":
        return err["msg"]
    if etype == "missing":
        return f"请填写{label}"
    if etype == "string_pattern_mismatch":
        return f"{label}格式不正确"
    if etype in ("greater_than_equal", "less_than_equal"):
        return "GPA / 均分需大于 0 且不超过所选满分" if field == "gpa" else f"{label}填写有误"
    if etype in ("float_parsing_error", "int_parsing_error", "float_type"):
        return f"{label}格式不正确"
    if "too_short" in etype:
        return f"{label}太短"
    if "too_long" in etype:
        return f"{label}过长"
    return f"{label}填写有误"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="智能选校测评工具", version="0.1.0", lifespan=lifespan)

# 前端静态目录（相对 agent/ 上级的 web/static）
STATIC_DIR = Path(__file__).resolve().parents[2] / "web" / "static"

_RATE_LIMITS = {
    ("POST", "/api/v1/evaluate"): ("evaluate", EVALUATE_RATE_LIMIT),
    ("POST", "/api/v1/leads"): ("leads", LEAD_RATE_LIMIT),
}


def require_admin(token: str | None) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="管理后台尚未配置访问口令，请联系管理员")
    if not token or not hmac.compare_digest(token.encode(), ADMIN_TOKEN.encode()):
        raise HTTPException(status_code=401, detail="需要访问口令")


@app.middleware("http")
async def private_response_headers(request: Request, call_next):
    rule = _RATE_LIMITS.get((request.method, request.url.path))
    if rule:
        scope, limit = rule
        client = request.client.host if request.client else "unknown"
        retry_after = rate_limiter.check(scope, client, limit, RATE_LIMIT_WINDOW_SECONDS)
        if retry_after is not None:
            return JSONResponse(
                status_code=429,
                content={"detail": "操作过于频繁，请稍后再试"},
                headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
            )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """参数校验失败 → 422 + 一句中文提示。"""
    return JSONResponse(status_code=422, content={"detail": _validation_message(exc)})


@app.exception_handler(AIError)
async def ai_error_handler(request: Request, exc: AIError) -> JSONResponse:
    """AI 服务不可用 / 返回不可解析 → 502，前端提示重试。"""
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底：记录日志，前端只看到友好提示，不暴露堆栈。"""
    logger.exception("未处理异常：%s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "服务开小差了，请稍后重试"})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/ping-deepseek")
def ping_deepseek(x_admin_token: str | None = Header(default=None)) -> dict:
    """调通验证端点：让 DeepSeek 简单回一句，确认链路正常。"""
    require_admin(x_admin_token)
    reply = chat([{"role": "user", "content": "请只回复「OK」两个字"}])
    return {"reply": reply}


@app.post("/api/v1/evaluate", response_model=EvaluatePreviewResponse)
def evaluate_schools(req: EvaluateRequest) -> EvaluatePreviewResponse:
    """选校核心接口：输入 GPA+专业+目标国家，返回三档 6 校推荐。"""
    result = evaluate(req)
    report_id = insert_report(result.model_dump_json(exclude={"report_id"}))
    return EvaluatePreviewResponse.model_validate({
        "report_id": report_id,
        "tiers": [
            {"level": tier.level, "schools": [{"name": school.name} for school in tier.schools]}
            for tier in result.tiers
        ],
    })


@app.post("/api/v1/leads", response_model=LeadResponse)
def create_lead(req: LeadRequest, background_tasks: BackgroundTasks) -> LeadResponse:
    """留资闭环：保存联系方式 + 测评背景，并异步通知顾问跟进。"""
    report_id = str(req.report_id) if req.report_id else None
    report = get_report(report_id) if report_id else None
    if report_id and not report:
        raise HTTPException(status_code=400, detail="测评报告不存在或已失效，请重新测评")
    lead = insert_lead(
        req.wechat, req.phone, req.gpa, req.major, req.target_country,
        req.school_tier, req.degree, req.language_type, req.language_score,
        report_id,
        gpa_scale=req.gpa_scale,
    )
    background_tasks.add_task(notify_new_lead, lead)
    full_report = EvaluateResponse.model_validate_json(report["result_json"]) if report else None
    if full_report:
        full_report.report_id = req.report_id
    return LeadResponse(id=lead["id"], message="留资成功", report=full_report)


@app.get("/api/v1/leads")
def get_leads(x_admin_token: str | None = Header(default=None)) -> dict:
    """必须配置并提供管理口令；配置缺失时拒绝访问。"""
    require_admin(x_admin_token)
    return {"leads": list_leads()}


@app.delete("/api/v1/leads")
def delete_leads(
    x_admin_token: str | None = Header(default=None),
    x_confirm_clear: str | None = Header(default=None),
) -> dict:
    require_admin(x_admin_token)
    if x_confirm_clear != "clear-all-leads":
        raise HTTPException(status_code=400, detail="请确认清除全部历史留资")
    return {"deleted": clear_leads()}


@app.get("/admin")
def admin_page() -> RedirectResponse:
    """数据查看界面快捷入口。"""
    return RedirectResponse("/admin.html")


# 静态前端托管（放在最后，避免覆盖 /api 路由）
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
