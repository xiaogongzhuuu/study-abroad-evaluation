import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import db, main as main_module
from app.main import app
from app.rate_limit import FixedWindowRateLimiter, rate_limiter
from app.schemas import EvaluateResponse


VALID_TIERS = [
    {
        "level": "冲刺",
        "schools": [
            {"name": "冲刺大学 A", "reason": "匹配学生背景"},
            {"name": "冲刺大学 B", "reason": "专业方向合适"},
        ],
    },
    {
        "level": "匹配",
        "schools": [
            {"name": "匹配大学 A", "reason": "录取机会适中"},
            {"name": "匹配大学 B", "reason": "课程设置匹配"},
        ],
    },
    {
        "level": "保底",
        "schools": [
            {"name": "保底大学 A", "reason": "背景高于常见要求"},
            {"name": "保底大学 B", "reason": "申请风险较低"},
        ],
    },
]


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "leads.db")
    db.init_db()
    monkeypatch.setattr("app.main.notify_new_lead", lambda _lead: None)


@pytest.fixture(autouse=True)
def isolated_rate_limits():
    rate_limiter.clear()
    yield
    rate_limiter.clear()


def test_clear_leads_requires_auth_and_confirmation(isolated_db, monkeypatch):
    monkeypatch.setattr(main_module, "ADMIN_TOKEN", "test-admin")
    db.insert_lead("test_wechat", "13800138000")
    with TestClient(app) as client:
        assert client.delete("/api/v1/leads").status_code == 401
        assert client.delete("/api/v1/leads", headers={
            "X-Admin-Token": "wrong", "X-Confirm-Clear": "clear-all-leads",
        }).status_code == 401
        assert client.delete("/api/v1/leads", headers={
            "X-Admin-Token": "test-admin",
        }).status_code == 400
        assert len(db.list_leads()) == 1
        monkeypatch.setattr(main_module, "ADMIN_TOKEN", "")
        assert client.delete("/api/v1/leads", headers={
            "X-Admin-Token": "test-admin", "X-Confirm-Clear": "clear-all-leads",
        }).status_code == 503
        assert len(db.list_leads()) == 1


def test_clear_leads_preserves_reports_and_future_submissions(isolated_db, monkeypatch):
    monkeypatch.setattr(main_module, "ADMIN_TOKEN", "test-admin")
    report_id = db.insert_report(json.dumps({"tiers": VALID_TIERS}))
    db.insert_lead("test_one", "13800138000", report_id=report_id)
    db.insert_lead("test_two", "13800138001")
    headers = {"X-Admin-Token": "test-admin", "X-Confirm-Clear": "clear-all-leads"}
    with TestClient(app) as client:
        response = client.delete("/api/v1/leads", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"deleted": 2}
        assert client.get("/api/v1/leads", headers=headers).json() == {"leads": []}
        assert db.get_report(report_id) is not None
        assert client.delete("/api/v1/leads", headers=headers).json() == {"deleted": 0}
        db.insert_lead("test_new", "13800138002", report_id=report_id)
        assert len(db.list_leads()) == 1


def test_response_requires_exactly_two_schools_per_tier():
    invalid = json.loads(json.dumps({"tiers": VALID_TIERS}))
    invalid["tiers"][0]["schools"].pop()
    with pytest.raises(ValidationError):
        EvaluateResponse.model_validate(invalid)


def test_report_is_saved_and_joined_to_lead(isolated_db):
    raw = json.dumps({"tiers": VALID_TIERS}, ensure_ascii=False)
    report_id = db.insert_report(raw)
    lead = db.insert_lead("test_wechat", "13800138000", report_id=report_id)

    assert lead["report_id"] == report_id
    assert json.loads(lead["result_json"])["tiers"][0]["level"] == "冲刺"
    assert db.list_leads()[0]["result_json"] == raw


def test_evaluate_to_lead_api_uses_report_id(isolated_db, monkeypatch):
    def fake_evaluate(_req):
        return EvaluateResponse.model_validate({"tiers": VALID_TIERS})

    monkeypatch.setattr("app.main.evaluate", fake_evaluate)
    monkeypatch.setattr("app.main.ADMIN_TOKEN", "test-admin")

    with TestClient(app) as client:
        evaluation = client.post(
            "/api/v1/evaluate",
            json={"gpa": 85, "gpa_scale": 100, "major": "计算机科学", "target_country": "德国"},
        )
        assert evaluation.status_code == 200
        report_id = evaluation.json()["report_id"]
        assert all("reason" not in school for tier in evaluation.json()["tiers"] for school in tier["schools"])
        assert evaluation.headers["cache-control"] == "no-store"

        lead = client.post(
            "/api/v1/leads",
            json={
                "wechat": "test_wechat",
                "phone": "13800138000",
                "report_id": report_id,
                "gpa": 85,
                "gpa_scale": 100,
                "target_country": "德国",
            },
        )
        assert lead.status_code == 200

        assert lead.json()["report"]["tiers"] == VALID_TIERS
        assert lead.json()["report"]["report_id"] == report_id
        saved = client.get("/api/v1/leads", headers={"X-Admin-Token": "test-admin"}).json()["leads"][0]
        assert saved["report_id"] == report_id
        assert saved["gpa"] == 85
        assert saved["gpa_scale"] == 100
        assert saved["target_country"] == "德国"
        assert json.loads(saved["result_json"])["tiers"] == VALID_TIERS


def test_unknown_report_id_is_rejected(isolated_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/leads",
            json={
                "wechat": "test_wechat",
                "phone": "13800138000",
                "report_id": "00000000-0000-0000-0000-000000000000",
            },
        )
    assert response.status_code == 400
    assert "报告不存在" in response.json()["detail"]


@pytest.mark.parametrize("configured,provided,expected", [
    ("", "", 503), ("", "anything", 503),
    ("secret", "", 401), ("secret", "wrong", 401), ("secret", "secret", 200),
])
def test_admin_access_fails_closed(isolated_db, monkeypatch, configured, provided, expected):
    monkeypatch.setattr("app.main.ADMIN_TOKEN", configured)
    with TestClient(app) as client:
        response = client.get("/api/v1/leads", headers={"X-Admin-Token": provided})
    assert response.status_code == expected
    if expected != 200:
        assert "leads" not in response.json()


def test_ping_requires_admin_before_ai_call(isolated_db, monkeypatch):
    monkeypatch.setattr("app.main.ADMIN_TOKEN", "secret")
    def forbidden(*args, **kwargs):
        pytest.fail("未认证请求不得调用 AI")
    monkeypatch.setattr("app.main.chat", forbidden)
    with TestClient(app) as client:
        assert client.get("/api/v1/ping-deepseek").status_code == 401


def test_lead_without_report_cannot_unlock_report(isolated_db):
    db.insert_report(json.dumps({"tiers": VALID_TIERS}))
    with TestClient(app) as client:
        response = client.post("/api/v1/leads", json={"wechat": "test_user", "phone": "13800138000"})
    assert response.status_code == 200
    assert response.json()["report"] is None


@pytest.mark.parametrize("updates,message", [
    ({"gpa": 4.5, "gpa_scale": 4}, "满分 4"),
    ({"gpa": 101, "gpa_scale": 100}, "GPA"),
    ({"gpa_scale": 10}, "计分制"),
    ({"target_country": " 其他 "}, "具体"),
    ({"language_type": "雅思", "language_score": 100}, "雅思"),
    ({"language_type": "雅思", "language_score": 7.1}, "递增"),
    ({"language_type": "托福", "language_score": 100.5}, "递增"),
    ({"language_type": "托福（1–6分制）", "language_score": 100}, "1～6"),
    ({"language_type": "雅思"}, "一起填写"),
    ({"language_score": 7}, "一起填写"),
])
def test_invalid_background_never_calls_ai(isolated_db, monkeypatch, updates, message):
    def forbidden(*args, **kwargs):
        pytest.fail("无效背景不得调用 AI")
    monkeypatch.setattr("app.main.evaluate", forbidden)
    payload = {"gpa": 3.6, "major": "计算机科学", "target_country": "美国", **updates}
    with TestClient(app) as client:
        response = client.post("/api/v1/evaluate", json=payload)
    assert response.status_code == 422
    assert message in response.json()["detail"]


@pytest.mark.parametrize("updates", [
    {"gpa": 4.2, "gpa_scale": 5},
    {"gpa": 85, "gpa_scale": 100},
    {"language_type": "雅思", "language_score": 7.5},
    {"language_type": "托福", "language_score": 100},
    {"language_type": "托福（1–6分制）", "language_score": 5.5},
    {"language_type": "雅思", "language_score": 0},
    {"language_type": " ", "language_score": None},
])
def test_valid_scales_reach_model_without_conversion(monkeypatch, updates):
    from app.schemas import EvaluateRequest
    from app.services import selector
    payload = {"gpa": 3.6, "major": "计算机科学", "target_country": "德国", **updates}
    req = EvaluateRequest.model_validate(payload)
    captured = []
    def fake_chat(messages, **kwargs):
        captured.extend(messages)
        return json.dumps({"tiers": VALID_TIERS})
    monkeypatch.setattr(selector, "chat", fake_chat)
    result = selector.evaluate(req)
    assert len(result.tiers) == 3
    assert f"{req.gpa:g}（满分 {req.gpa_scale}）" in captured[1]["content"]
    assert "德国" in captured[1]["content"]
    if req.language_type:
        assert req.language_type in captured[1]["content"]


def test_duplicate_ai_schools_are_rejected(monkeypatch):
    from app.schemas import EvaluateRequest
    from app.services import selector
    from app.services.deepseek import AIError
    tiers = json.loads(json.dumps(VALID_TIERS))
    tiers[1]["schools"][0]["name"] = "  冲刺大学 A  "
    monkeypatch.setattr(selector, "chat", lambda *args, **kwargs: json.dumps({"tiers": tiers}))
    with pytest.raises(AIError, match="重复院校"):
        selector.evaluate(EvaluateRequest(gpa=3.6, major="计算机", target_country="美国"))


def test_blank_ai_school_is_rejected():
    tiers = json.loads(json.dumps(VALID_TIERS))
    tiers[0]["schools"][0]["name"] = "   "
    with pytest.raises(ValidationError):
        EvaluateResponse.model_validate({"tiers": tiers})


def test_lead_language_validation_matches_evaluation(isolated_db):
    with TestClient(app) as client:
        response = client.post("/api/v1/leads", json={
            "wechat": "test_user", "phone": "13800138000", "language_score": 6.5,
        })
    assert response.status_code == 422
    assert "一起填写" in response.json()["detail"]
    assert db.list_leads() == []


def test_migration_preserves_existing_gpa_without_inventing_scale(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / "legacy.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY AUTOINCREMENT, wechat TEXT NOT NULL, phone TEXT NOT NULL, gpa REAL, major TEXT, target_country TEXT, created_at TEXT NOT NULL)")
        connection.execute("INSERT INTO leads (wechat,phone,gpa,created_at) VALUES ('test','13800138000',3.7,'2026-08-01T00:00:00+00:00')")
    db.init_db()
    db.init_db()
    lead = db.list_leads()[0]
    assert lead["gpa"] == 3.7
    assert lead["gpa_scale"] is None


def test_notification_includes_scale_without_sending():
    from app.services.notify import _lead_summary
    message = _lead_summary({"wechat": "test", "phone": "13800138000", "gpa": 85, "gpa_scale": 100, "created_at": "2026-08-01T00:00:00+00:00"})
    assert "85 / 100" in message


def test_rate_limiter_expires_old_events_at_window_boundary():
    limiter = FixedWindowRateLimiter()
    assert limiter.check("evaluate", "client", 2, 60, now=100) is None
    assert limiter.check("evaluate", "client", 2, 60, now=110) is None
    assert limiter.check("evaluate", "client", 2, 60, now=120) == 40
    assert limiter.check("evaluate", "client", 2, 60, now=160) is None


def test_evaluate_rate_limit_prevents_extra_ai_call(isolated_db, monkeypatch):
    calls = 0

    def fake_evaluate(_req):
        nonlocal calls
        calls += 1
        return EvaluateResponse.model_validate({"tiers": VALID_TIERS})

    monkeypatch.setattr("app.main.evaluate", fake_evaluate)
    monkeypatch.setitem(main_module._RATE_LIMITS, ("POST", "/api/v1/evaluate"), ("evaluate", 1))
    payload = {"gpa": 3.6, "major": "计算机科学", "target_country": "美国"}
    with TestClient(app) as client:
        assert client.post("/api/v1/evaluate", json=payload).status_code == 200
        limited = client.post("/api/v1/evaluate", json=payload)
    assert limited.status_code == 429
    assert limited.json() == {"detail": "操作过于频繁，请稍后再试"}
    assert int(limited.headers["Retry-After"]) >= 1
    assert limited.headers["Cache-Control"] == "no-store"
    assert calls == 1


def test_evaluate_and_lead_limits_are_independent(isolated_db, monkeypatch):
    monkeypatch.setitem(main_module._RATE_LIMITS, ("POST", "/api/v1/evaluate"), ("evaluate", 1))
    monkeypatch.setitem(main_module._RATE_LIMITS, ("POST", "/api/v1/leads"), ("leads", 1))
    with TestClient(app) as client:
        assert client.post("/api/v1/evaluate", json={}).status_code == 422
        assert client.post("/api/v1/evaluate", json={}).status_code == 429
        assert client.post("/api/v1/leads", json={}).status_code == 422
        assert client.post("/api/v1/leads", json={}).status_code == 429


def test_zero_limit_disables_rate_limiting(isolated_db, monkeypatch):
    monkeypatch.setitem(main_module._RATE_LIMITS, ("POST", "/api/v1/evaluate"), ("evaluate", 0))
    with TestClient(app) as client:
        assert client.post("/api/v1/evaluate", json={}).status_code == 422
        assert client.post("/api/v1/evaluate", json={}).status_code == 422
