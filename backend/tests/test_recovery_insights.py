"""Phase 6 + 7 backend tests — Recovery Management & AI Insights."""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ledger-dashboard-13.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@kazo.com"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def auth():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


# ---------- Regression ----------
def test_dashboard_overview_no_period_value(auth):
    r = auth.get(f"{BASE_URL}/api/dashboard/overview?period_type=month")
    assert r.status_code == 200, r.text


# ---------- Insights ----------
def test_health_score_month(auth):
    r = auth.get(f"{BASE_URL}/api/insights/health-score", params={"period_type": "month", "period_value": "2026-04"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "health" in body and "score" in body["health"]
    h = body["health"]
    assert h["grade"] in ("A", "B", "C", "D", "F")
    assert "mapping_health" in h["components"]
    assert "leakage_health" in h["components"]
    assert "margin_health" in h["components"]
    assert "recovery_health" in h["components"]
    assert "raw" in h and "nsv" in h["raw"]


def test_health_score_quarter(auth):
    r = auth.get(f"{BASE_URL}/api/insights/health-score",
                 params={"period_type": "quarter", "period_value": "2026-Q2"})
    assert r.status_code == 200, r.text


def test_health_score_ytd(auth):
    r = auth.get(f"{BASE_URL}/api/insights/health-score",
                 params={"period_type": "ytd", "period_value": "2026"})
    assert r.status_code == 200, r.text


def test_morning_brief_executive(auth):
    r = auth.post(f"{BASE_URL}/api/insights/morning-brief",
                  json={"period_type": "month", "period_value": "2026-04", "tone": "executive"},
                  timeout=90)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "narrative" in body and len(body["narrative"]) > 20
    assert body["source"] in ("llm", "rule_based")
    assert "health" in body


def test_briefs_list(auth):
    r = auth.get(f"{BASE_URL}/api/insights/briefs?limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------- Recovery ----------
def test_recovery_summary(auth):
    r = auth.get(f"{BASE_URL}/api/recovery/summary",
                 params={"period_type": "month", "period_value": "2026-04"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "totals" in body and "total_cases" in body["totals"]
    assert "by_status" in body and "by_priority" in body
    assert "discrepancy_universe" in body
    assert "case_coverage_pct" in body


def test_recovery_auto_create_zero(auth):
    # 2026-04 currently has 0 discrepancies with recoverable > 0 → should not crash
    r = auth.post(f"{BASE_URL}/api/recovery/cases/auto-create",
                  json={"period_type": "month", "period_value": "2026-04", "min_recoverable": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "created" in body and "skipped" in body and "candidates" in body


def test_recovery_create_case_404(auth):
    r = auth.post(f"{BASE_URL}/api/recovery/cases",
                  json={"discrepancy_id": "does-not-exist-abc"})
    assert r.status_code == 404


def test_recovery_full_lifecycle(auth):
    # 1) Look for an existing discrepancy; if none, seed one directly via mongo, else skip full flow
    r = auth.get(f"{BASE_URL}/api/reconciliation/discrepancies?limit=1")
    assert r.status_code == 200
    body = r.json()

    disc_id = None
    if body.get("items"):
        disc_id = body["items"][0]["id"]

    seeded = False
    if not disc_id:
        try:
            from pymongo import MongoClient
            import uuid
            # Load backend .env if MONGO_URL not in current env
            mongo_url = os.environ.get("MONGO_URL")
            db_name = os.environ.get("DB_NAME")
            if not mongo_url or not db_name:
                try:
                    from dotenv import dotenv_values
                    vals = dotenv_values("/app/backend/.env")
                    mongo_url = mongo_url or vals.get("MONGO_URL")
                    db_name = db_name or vals.get("DB_NAME")
                except Exception:
                    pass
            if mongo_url and db_name:
                c = MongoClient(mongo_url)[db_name]
                doc = {
                    "id": f"TEST_disc_{uuid.uuid4()}",
                    "recon_run_id": "TEST_run",
                    "online_order_id": "TEST_ORDER_1",
                    "sku": "TEST_SKU",
                    "sales_id": "TEST_sales",
                    "settlement_id": "TEST_settle",
                    "severity": "high",
                    "reason": "seeded for test",
                    "match_status": "variance",
                    "recoverable": 250.0,
                    "settle_variance": 250.0,
                    "report_month": "2026-04",
                }
                c.discrepancies.insert_one(doc)
                disc_id = doc["id"]
                seeded = True
        except Exception as e:
            pytest.skip(f"No discrepancies exist and seed failed: {e}")

    if not disc_id:
        pytest.skip("No discrepancies available for full lifecycle test")

    # 2) Create case
    r = auth.post(f"{BASE_URL}/api/recovery/cases",
                  json={"discrepancy_id": disc_id, "assigned_to": "qa@kazo.com", "priority": "high",
                        "notes": "TEST_ opened by pytest"})
    assert r.status_code == 200, r.text
    case = r.json()
    assert case["status"] == "open"
    assert case["assigned_to"] == "qa@kazo.com"
    assert "recoverable_amount" in case
    case_id = case["id"]

    # 3) Duplicate should 409
    r = auth.post(f"{BASE_URL}/api/recovery/cases", json={"discrepancy_id": disc_id})
    assert r.status_code == 409

    # 4) List cases → contains
    r = auth.get(f"{BASE_URL}/api/recovery/cases?limit=500")
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()["items"]]
    assert case_id in ids

    # 5) Get case detail
    r = auth.get(f"{BASE_URL}/api/recovery/cases/{case_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["case"]["id"] == case_id
    assert "discrepancy" in body

    # 6) PATCH to in_review
    r = auth.patch(f"{BASE_URL}/api/recovery/cases/{case_id}",
                   json={"status": "in_review", "assigned_to": "qa@kazo.com"})
    assert r.status_code == 200
    assert r.json()["status"] == "in_review"

    # 7) PATCH to recovered
    r = auth.patch(f"{BASE_URL}/api/recovery/cases/{case_id}",
                   json={"status": "recovered", "recovered_amount": 100})
    assert r.status_code == 200
    updated = r.json()
    assert updated["status"] == "recovered"
    assert updated["recovered_amount"] == 100

    # 8) Notes: add + list
    r = auth.post(f"{BASE_URL}/api/recovery/cases/{case_id}/notes",
                  json={"body": "Filed ticket", "channel": "myntra_ticket", "direction": "outbound"})
    assert r.status_code == 200, r.text
    note = r.json()
    assert note["body"] == "Filed ticket"
    assert note["channel"] == "myntra_ticket"

    r = auth.get(f"{BASE_URL}/api/recovery/cases/{case_id}/notes")
    assert r.status_code == 200
    notes = r.json()
    assert any(n.get("body") == "Filed ticket" for n in notes)

    # 9) Evidence upload
    headers = {k: v for k, v in auth.headers.items() if k != "Content-Type"}
    files = {"file": ("evidence.txt", io.BytesIO(b"hello kazo evidence"), "text/plain")}
    r = requests.post(f"{BASE_URL}/api/recovery/cases/{case_id}/evidence",
                      files=files, headers=headers, data={"description": "test file"})
    assert r.status_code == 200, r.text
    ev = r.json()
    assert "data_b64" not in ev
    assert ev["filename"] == "evidence.txt"
    ev_id = ev["id"]

    # list evidence
    r = auth.get(f"{BASE_URL}/api/recovery/cases/{case_id}/evidence")
    assert r.status_code == 200
    assert any(e["id"] == ev_id for e in r.json())

    # download
    r = auth.get(f"{BASE_URL}/api/recovery/evidence/{ev_id}/download")
    assert r.status_code == 200
    assert r.content == b"hello kazo evidence"

    # delete evidence
    r = auth.delete(f"{BASE_URL}/api/recovery/evidence/{ev_id}")
    assert r.status_code == 200
    assert r.json().get("ok") is True

    # 10) Clean up case
    r = auth.delete(f"{BASE_URL}/api/recovery/cases/{case_id}")
    assert r.status_code == 200

    # Clean seeded discrepancy
    if seeded:
        try:
            from pymongo import MongoClient
            from dotenv import dotenv_values
            vals = dotenv_values("/app/backend/.env")
            MongoClient(vals["MONGO_URL"])[vals["DB_NAME"]].discrepancies.delete_one({"id": disc_id})
        except Exception:
            pass
