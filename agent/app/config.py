import os
from pathlib import Path

from dotenv import load_dotenv

# 按文件位置加载 agent/.env，避免依赖启动目录（从其他目录启动会静默丢配置）
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 通知推送配置（留空则跳过对应通知）
WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL", "")

# 数据查看界面访问口令（留空则 /api/v1/leads 开放访问，公网部署务必设置）
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
NOTIFY_EMAIL_TO = os.getenv("NOTIFY_EMAIL_TO", "")
