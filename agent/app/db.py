import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# 数据库文件放在项目根目录 data/ 下（已被 .gitignore 忽略）
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "leads.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """初始化数据库与 leads 表（幂等），并为旧库补缺失列。"""
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            _migrate(conn)
    finally:
        conn.close()


# 后续新增的选填列：建表语句不动，用 ALTER TABLE 补齐（兼容旧库）
_EXTRA_COLUMNS = {
    "school_tier": "TEXT",
    "degree": "TEXT",
    "language_type": "TEXT",
    "language_score": "REAL",
    "result_json": "TEXT",
    "report_id": "TEXT",
}


def _migrate(conn: sqlite3.Connection) -> None:
    """为已存在的旧表补上缺失的列（幂等）。"""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(leads)")}
    for col, col_type in _EXTRA_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {col} {col_type}")


def insert_lead(
    wechat: str,
    phone: str,
    gpa: float | None = None,
    major: str | None = None,
    target_country: str | None = None,
    school_tier: str | None = None,
    degree: str | None = None,
    language_type: str | None = None,
    language_score: float | None = None,
    report_id: str | None = None,
) -> dict:
    """插入一条留资记录，返回完整记录（含 id 与 created_at）。"""
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO leads (
                    wechat, phone, gpa, major, target_country,
                    school_tier, degree, language_type, language_score,
                    report_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    wechat, phone, gpa, major, target_country,
                    school_tier, degree, language_type, language_score,
                    report_id, created_at,
                ),
            )
            report = get_report(report_id, conn=conn) if report_id else None
            return {
                "id": int(cur.lastrowid),
                "wechat": wechat,
                "phone": phone,
                "gpa": gpa,
                "major": major,
                "target_country": target_country,
                "school_tier": school_tier,
                "degree": degree,
                "language_type": language_type,
                "language_score": language_score,
                "report_id": report_id,
                "result_json": report["result_json"] if report else None,
                "created_at": created_at,
            }
    finally:
        conn.close()


def list_leads() -> list[dict]:
    """按留资时间倒序返回全部线索（数据查看界面用）。"""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT leads.*, reports.result_json AS report_result_json
            FROM leads
            LEFT JOIN reports ON reports.id = leads.report_id
            ORDER BY leads.id DESC
            """
        ).fetchall()
        result = []
        for row in rows:
            lead = dict(row)
            report_result = lead.pop("report_result_json")
            lead["result_json"] = report_result or lead.get("result_json")
            result.append(lead)
        return result
    finally:
        conn.close()


def insert_report(result_json: str) -> str:
    """保存服务端生成的测评报告，返回不可猜测的关联 ID。"""
    report_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO reports (id, result_json, created_at) VALUES (?, ?, ?)",
                (report_id, result_json, created_at),
            )
    finally:
        conn.close()
    return report_id


def get_report(report_id: str, conn: sqlite3.Connection | None = None) -> dict | None:
    """按 ID 读取服务端报告；不存在时返回 None。"""
    owns_conn = conn is None
    active_conn = conn or _connect()
    try:
        row = active_conn.execute(
            "SELECT id, result_json, created_at FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        if owns_conn:
            active_conn.close()
