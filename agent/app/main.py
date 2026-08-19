from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.db import init_db, insert_lead
from app.schemas import EvaluateRequest, EvaluateResponse, LeadRequest, LeadResponse
from app.services.deepseek import chat
from app.services.notify import notify_new_lead
from app.services.selector import evaluate


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
