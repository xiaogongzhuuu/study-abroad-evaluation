import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import init_db, insert_lead
from app.schemas import EvaluateRequest, EvaluateResponse, LeadRequest, LeadResponse
from app.services.deepseek import AIError, chat
from app.services.notify import notify_new_lead
from app.services.selector import evaluate

logger = logging.getLogger(__name__)

# 字段中文名，用于把 Pydantic 校验错误翻译成可读提示
_FIELD_LABELS = {
    "gpa": "GPA",
    "major": "申请专业",
    "target_country": "目标国家",
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
    if etype == "missing":
        return f"请填写{label}"
    if etype == "string_pattern_mismatch":
        return f"{label}格式不正确"
    if etype in ("greater_than_equal", "less_than_equal"):
        return f"{label}需为 0~5 之间的数字" if field == "gpa" else f"{label}填写有误"
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
def ping_deepseek() -> dict:
    """调通验证端点：让 DeepSeek 简单回一句，确认链路正常。"""
    reply = chat([{"role": "user", "content": "请只回复「OK」两个字"}])
    return {"reply": reply}


@app.post("/api/v1/evaluate", response_model=EvaluateResponse)
def evaluate_schools(req: EvaluateRequest) -> EvaluateResponse:
    """选校核心接口：输入 GPA+专业+目标国家，返回三档 6 校推荐。"""
    return evaluate(req)


@app.post("/api/v1/leads", response_model=LeadResponse)
def create_lead(req: LeadRequest, background_tasks: BackgroundTasks) -> LeadResponse:
    """留资闭环：保存联系方式 + 测评背景，并异步通知顾问跟进。"""
    lead = insert_lead(
        req.wechat, req.phone, req.gpa, req.major, req.target_country
    )
    background_tasks.add_task(notify_new_lead, lead)
    return LeadResponse(id=lead["id"], message="留资成功")


# 静态前端托管（放在最后，避免覆盖 /api 路由）
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
