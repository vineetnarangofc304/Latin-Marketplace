"""KAZO Marketplace Finance — Backend API tests."""
import os
import io
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ledger-dashboard-13.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@kazo.com"
ADMIN_PASSWORD = "admin123"
SAMPLES = "/app/samples"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def token(client):
    r = client.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data and data["user"]["email"] == ADMIN_EMAIL
    return data["token"]


@pytest.fixture(scope="session")
def auth(client, token):
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# ---------- Health & Auth ----------
def test_health():
    r = requests.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_invalid():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert r.status_code == 401


def test_auth_me(auth):
    r = auth.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == ADMIN_EMAIL


# ---------- Masters ----------
def test_masters_commission_rules(auth):
    r = auth.get(f"{BASE_URL}/api/masters/commission-rules")
    assert r.status_code == 200
    rules = r.json()
    assert isinstance(rules, list) and len(rules) > 0
    assert "commission_pct" in rules[0]


def test_masters_fixed_fees(auth):
    r = auth.get(f"{BASE_URL}/api/masters/fixed-fees")
    assert r.status_code == 200 and len(r.json()) > 0


def test_masters_gt_charges(auth):
    r = auth.get(f"{BASE_URL}/api/masters/gt-charges")
    assert r.status_code == 200 and len(r.json()) > 0


def test_masters_return_fees(auth):
    r = auth.get(f"{BASE_URL}/api/masters/return-fees")
    assert r.status_code == 200 and len(r.json()) > 0


def test_masters_subcat_levels(auth):
    r = auth.get(f"{BASE_URL}/api/masters/subcat-levels")
    assert r.status_code == 200 and len(r.json()) > 0


def test_masters_tolerance_get_set(auth):
    r = auth.get(f"{BASE_URL}/api/masters/tolerance")
    assert r.status_code == 200
    t = r.json()
    r2 = auth.post(f"{BASE_URL}/api/masters/tolerance", json={
        "absolute_inr": t.get("absolute_inr", 1.0),
        "percentage": t.get("percentage", 0.5),
        "materiality_inr": t.get("materiality_inr", 100.0),
    })
    assert r2.status_code == 200


def test_commission_rule_edit_persistence(auth):
    rules = auth.get(f"{BASE_URL}/api/masters/commission-rules").json()
    rule = rules[0]
    original_pct = rule["commission_pct"]
    rule["commission_pct"] = round(original_pct + 0.001, 4)
    r = auth.post(f"{BASE_URL}/api/masters/commission-rules", json=rule)
    assert r.status_code == 200
    assert abs(r.json()["commission_pct"] - rule["commission_pct"]) < 1e-6
    # Revert
    rule["commission_pct"] = original_pct
    auth.post(f"{BASE_URL}/api/masters/commission-rules", json=rule)


# ---------- Uploads & pipeline ----------
def test_uploads_list_and_pipeline(auth):
    """Verify uploads exist / else upload sample, then verify sales, calc, recon, dashboard."""
    r = auth.get(f"{BASE_URL}/api/uploads")
    assert r.status_code == 200
    uploads = r.json()
    sales_uploads = [u for u in uploads if u["type"] == "sales"]
    settle_uploads = [u for u in uploads if u["type"] == "settlement"]

    # If no sales upload yet, upload sample
    if not sales_uploads:
        with open(f"{SAMPLES}/sale_data.xlsx", "rb") as f:
            files = {"file": ("sale_data.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            headers = {k: v for k, v in auth.headers.items() if k != "Content-Type"}
            r = requests.post(f"{BASE_URL}/api/uploads/sales", files=files, headers=headers, timeout=180)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["accepted_count"] > 0
        sales_upload_id = body["upload_id"]
    else:
        sales_upload_id = sales_uploads[0]["id"]
        assert sales_uploads[0]["accepted_count"] > 0

    if not settle_uploads:
        with open(f"{SAMPLES}/synthetic_settlement.xlsx", "rb") as f:
            files = {"file": ("synthetic_settlement.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            headers = {k: v for k, v in auth.headers.items() if k != "Content-Type"}
            r = requests.post(f"{BASE_URL}/api/uploads/settlement", files=files, headers=headers, timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["accepted_count"] > 0

    # Sales listing
    r = auth.get(f"{BASE_URL}/api/sales?limit=5")
    assert r.status_code == 200
    sd = r.json()
    assert sd["total"] > 0 and len(sd["items"]) > 0

    # Ensure calculations exist (may need to run)
    calcs = auth.get(f"{BASE_URL}/api/calculations?limit=1").json()
    if calcs["total"] == 0:
        r = auth.post(f"{BASE_URL}/api/calculations/run", json={})
        assert r.status_code == 200, r.text
        assert r.json()["processed"] >= 0
        # Give some time for insert
        time.sleep(1)
        calcs = auth.get(f"{BASE_URL}/api/calculations?limit=1").json()
    assert calcs["total"] > 0, "Calculations should be present after run"

    # Dashboard overview
    r = auth.get(f"{BASE_URL}/api/dashboard/overview")
    assert r.status_code == 200
    ov = r.json()
    assert ov["total_sales"] > 0
    assert ov["total_calculations"] > 0

    # Commission summary
    r = auth.get(f"{BASE_URL}/api/dashboard/commission-summary")
    assert r.status_code == 200
    cs = r.json()
    assert cs["kpi"]
    assert cs["kpi"]["total_nsv"] > 0
    assert cs["kpi"]["expected_commission"] > 0


def test_run_reconciliation(auth):
    r = auth.post(f"{BASE_URL}/api/reconciliation/run", json={})
    assert r.status_code == 200, r.text
    run = r.json()
    assert "matched" in run and "variance" in run and "unmatched" in run
    total = run["matched"] + run["variance"] + run["unmatched"]
    assert total > 0


def test_recon_runs_list(auth):
    r = auth.get(f"{BASE_URL}/api/reconciliation/runs")
    assert r.status_code == 200
    runs = r.json()
    assert len(runs) > 0
    assert "matched" in runs[0]


def test_discrepancies_list(auth):
    r = auth.get(f"{BASE_URL}/api/reconciliation/discrepancies?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 0
    if body["items"]:
        d = body["items"][0]
        assert d["severity"] in ("critical", "high", "medium", "low")
        assert d["match_status"] in ("variance", "unmatched")


def test_recon_summary(auth):
    r = auth.get(f"{BASE_URL}/api/dashboard/reconciliation-summary")
    assert r.status_code == 200
    body = r.json()
    assert "total_discrepancies" in body
    assert "by_severity" in body
