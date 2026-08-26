import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import db
from app.main import app
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
    monkeypatch.setattr("app.main.ADMIN_TOKEN", "")

    with TestClient(app) as client:
        evaluation = client.post(
            "/api/v1/evaluate",
            json={"gpa": 3.6, "major": "计算机科学", "target_country": "美国"},
        )
        assert evaluation.status_code == 200
        report_id = evaluation.json()["report_id"]

        lead = client.post(
            "/api/v1/leads",
            json={
                "wechat": "test_wechat",
                "phone": "13800138000",
                "report_id": report_id,
            },
        )
        assert lead.status_code == 200

        saved = client.get("/api/v1/leads").json()["leads"][0]
        assert saved["report_id"] == report_id
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
