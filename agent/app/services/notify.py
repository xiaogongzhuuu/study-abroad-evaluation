import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import httpx

from app.config import (
    NOTIFY_EMAIL_TO,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
    WECOM_WEBHOOK_URL,
)

logger = logging.getLogger(__name__)

_CN_TZ = ZoneInfo("Asia/Shanghai")


def _fmt_time(iso: str) -> str:
    """UTC 时间转北京时间，便于顾问阅读。"""
    return datetime.fromisoformat(iso).astimezone(_CN_TZ).strftime("%Y-%m-%d %H:%M")


def _lead_summary(lead: dict) -> str:
    lines = [f"微信：{lead['wechat']}", f"手机：{lead['phone']}"]
    if lead.get("gpa") is not None:
        lines.append(f"GPA：{lead['gpa']}")
    if lead.get("major"):
        lines.append(f"专业：{lead['major']}")
    if lead.get("target_country"):
        lines.append(f"目标国家：{lead['target_country']}")
    if lead.get("school_tier"):
        lines.append(f"院校档次：{lead['school_tier']}")
    if lead.get("degree"):
        lines.append(f"意向学位：{lead['degree']}")
    if lead.get("language_score") is not None:
        label = f"{lead.get('language_type')} " if lead.get("language_type") else ""
        lines.append(f"语言成绩：{label}{lead['language_score']:g}")
    lines.append(f"留资时间：{_fmt_time(lead['created_at'])}")
    return "\n".join(lines)


def send_wecom_text(text: str) -> None:
    """推一条文本消息到企微群；未配置 webhook 则跳过。"""
    if not WECOM_WEBHOOK_URL:
        return
    resp = httpx.post(
        WECOM_WEBHOOK_URL,
        json={"msgtype": "text", "text": {"content": text}},
        timeout=5,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errcode") != 0:
        logger.warning("企微推送失败：%s", data)


def send_email(subject: str, body: str) -> None:
    """发邮件给顾问；SMTP 未配置则跳过。"""
    if not (SMTP_HOST and SMTP_USER and NOTIFY_EMAIL_TO):
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = NOTIFY_EMAIL_TO
    msg.set_content(body)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as server:
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


def notify_new_lead(lead: dict) -> None:
    """留资成功后通知顾问：先企微群，再邮件。任一失败不影响留资。"""
    summary = _lead_summary(lead)
    subject = f"【选校测评】新线索：{lead['wechat']}"
    try:
        send_wecom_text("新留资线索\n" + summary)
    except Exception:
        logger.exception("企微通知失败")
    try:
        send_email(subject, summary)
    except Exception:
        logger.exception("邮件通知失败")
