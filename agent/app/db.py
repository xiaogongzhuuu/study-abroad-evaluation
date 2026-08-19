import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# 数据库文件放在项目根目录 data/ 下（已被 .gitignore 忽略）
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "leads.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """初始化数据库与 leads 表（幂等）。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wechat TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    gpa REAL,
                    major TEXT,
                    target_country TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
    finally:
        conn.close()


def insert_lead(
    wechat: str,
    phone: str,
    gpa: float | None = None,
    major: str | None = None,
    target_country: str | None = None,
) -> dict:
    """插入一条留资记录，返回完整记录（含 id 与 created_at）。"""
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO leads (wechat, phone, gpa, major, target_country, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (wechat, phone, gpa, major, target_country, created_at),
            )
            return {
                "id": int(cur.lastrowid),
                "wechat": wechat,
                "phone": phone,
                "gpa": gpa,
                "major": major,
                "target_country": target_country,
                "created_at": created_at,
            }
    finally:
        conn.close()
