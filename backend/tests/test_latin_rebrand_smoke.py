"""Latin Quarter fork: backend smoke + rebrand + data-load verification."""
import os
import json
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@fundle.ai", "password": "admin123"}
MKT = {"email": "marketing@fundle.ai", "password": "admin123"}


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="session")
def admin_token(s):
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token")
    assert isinstance(tok, str) and tok
    return tok


@pytest.fixture(scope="session")
def ac(admin_token):
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json",
                         "Authorization": f"Bearer {admin_token}"})
    return sess


# ---------- health & auth ----------
class TestHealthAuth:
    def test_health(self, s):
        r = s.get(f"{API}/health", timeout=60)
        assert r.status_code == 200, r.text[:300]
        print("health:", r.json())

    def test_admin_login(self, s):
        r = s.post(f"{API}/auth/login", json=ADMIN, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["user"]["email"] == ADMIN["email"]
        assert d["user"].get("role") == "admin"
        assert d.get("token")

    def test_marketing_login(self, s):
        r = s.post(f"{API}/auth/login", json=MKT, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["user"]["email"] == MKT["email"]
        assert d.get("token")

    def test_bad_password_rejected(self, s):
        r = s.post(f"{API}/auth/login", json={"email": ADMIN["email"], "password": "wrong"}, timeout=60)
        assert r.status_code in (400, 401), r.status_code

    def test_legacy_kazo_admin_removed(self, s):
        r = s.post(f"{API}/auth/login", json={"email": "admin@kazo.com", "password": "admin123"}, timeout=60)
        assert r.status_code in (400, 401), f"legacy kazo admin still logs in: {r.status_code}"

    def test_protected_requires_auth(self):
        r = requests.get(f"{API}/uploads", timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_me(self, ac):
        r = ac.get(f"{API}/auth/me", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["email"] == ADMIN["email"]


# ---------- data load ----------
class TestDataLoad:
    def test_uploads_two(self, ac):
        r = ac.get(f"{API}/uploads", timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        items = d if isinstance(d, list) else d.get("items", d.get("uploads", []))
        print("uploads:", json.dumps(items, default=str)[:600])
        assert len(items) == 2, f"expected 2 uploads, got {len(items)}"
        counts = sorted(int(i.get("accepted_count") or 0) for i in items)
        assert counts == [28537, 42550], counts

    def test_sales_list_and_pagination(self, ac):
        r = ac.get(f"{API}/sales?limit=25&skip=0", timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        rows = d["items"]
        assert len(rows) == 25, len(rows)
        total = d.get("total")
        print("sales total:", total, "rows:", len(rows))
        assert total == 42550, total
        r2 = ac.get(f"{API}/sales?limit=25&skip=25", timeout=120)
        assert r2.status_code == 200
        rows2 = r2.json().get("items", [])
        assert rows and rows2 and rows[0] != rows2[0], "pagination returned identical page"

    def test_no_mongo_objectid_in_sales(self, ac):
        r = ac.get(f"{API}/sales?limit=5", timeout=120)
        assert '"_id"' not in r.text, "mongo _id leaked in /api/sales"

    def test_calculations_list(self, ac):
        r = ac.get(f"{API}/calculations?limit=25", timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        rows = d.get("items", [])
        print("calc total:", d.get("total"), "rows:", len(rows))
        assert len(rows) > 0

    def test_settlement_list(self, ac):
        r = ac.get(f"{API}/settlement?limit=25", timeout=180)
        assert r.status_code == 200, r.text[:300]
        assert len(r.json().get("items", [])) > 0


# ---------- dashboards / reports ----------
class TestDashboardsReports:
    def test_overview(self, ac):
        r = ac.get(f"{API}/dashboard/overview", timeout=180)
        assert r.status_code == 200, r.text[:300]
        print("overview:", json.dumps(r.json(), default=str)[:800])

    def test_commission_summary(self, ac):
        r = ac.get(f"{API}/dashboard/commission-summary", timeout=180)
        assert r.status_code == 200, r.text[:300]

    def test_reconciliation_summary(self, ac):
        r = ac.get(f"{API}/dashboard/reconciliation-summary", timeout=180)
        assert r.status_code == 200, r.text[:300]

    def test_reports_months_includes_202606(self, ac):
        r = ac.get(f"{API}/reports/months", timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        raw = json.dumps(d, default=str)
        print("months:", raw[:400])
        assert "2026-06" in raw, "2026-06 missing from /api/reports/months"

    def test_reports_monthly(self, ac):
        r = ac.get(f"{API}/reports/monthly?month=2026-06", timeout=180)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        print("monthly:", json.dumps(r.json(), default=str)[:600])

    def test_reports_monthly_export(self, ac):
        r = ac.get(f"{API}/reports/monthly/export?month=2026-06", timeout=240)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert len(r.content) > 1000
        cd = r.headers.get("content-disposition", "")
        print("export filename header:", cd, "bytes:", len(r.content))
        assert "kazo" not in cd.lower(), f"KAZO branding in export filename: {cd}"


# ---------- reconciliation / discrepancies / recovery ----------
class TestReconRecovery:
    def test_runs(self, ac):
        r = ac.get(f"{API}/reconciliation/runs", timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        runs = d if isinstance(d, list) else d.get("items", [])
        assert len(runs) >= 1, "no reconciliation runs"
        print("latest run:", json.dumps(runs[0], default=str)[:500])

    def test_discrepancies(self, ac):
        r = ac.get(f"{API}/reconciliation/discrepancies?limit=25", timeout=240)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        print("disc total:", d.get("total"))
        assert len(d.get("items", [])) > 0

    def test_recovery_cases(self, ac):
        r = ac.get(f"{API}/recovery/cases?limit=25", timeout=240)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        print("recovery total:", d.get("total"))
        assert len(d.get("items", d if isinstance(d, list) else [])) > 0

    def test_recovery_summary(self, ac):
        r = ac.get(f"{API}/recovery/summary", timeout=180)
        assert r.status_code == 200, r.text[:300]


# ---------- insights ----------
class TestInsights:
    def test_health_score(self, ac):
        r = ac.get(f"{API}/insights/health-score", timeout=240)
        assert r.status_code == 200, r.text[:300]
        print("health-score:", json.dumps(r.json(), default=str)[:400])

    def test_morning_brief(self, ac):
        r = ac.post(f"{API}/insights/morning-brief", json={}, timeout=300)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        d = r.json()
        raw = json.dumps(d, default=str)
        print("brief source:", d.get("source"), "len:", len(raw))
        assert d.get("source") in ("llm", "rule_based"), d.get("source")
        assert "kazo" not in raw.lower(), "KAZO appears in morning brief content"


# ---------- masters ----------
MASTER_ENDPOINTS = [
    "/masters/commission-rules",
    "/masters/fixed-fees",
    "/masters/gt-charges",
    "/masters/return-fees",
    "/masters/subcat-levels",
    "/masters/tolerance",
    "/masters/tax-rates",
    "/masters/settlement-settings",
]


class TestMasters:
    @pytest.mark.parametrize("ep", MASTER_ENDPOINTS)
    def test_master_endpoint_ok(self, ac, ep):
        r = ac.get(f"{API}{ep}", timeout=180)
        assert r.status_code == 200, f"{ep} -> {r.status_code} {r.text[:300]}"

    def test_commission_rules_count_and_brand(self, ac):
        r = ac.get(f"{API}/masters/commission-rules", timeout=180)
        assert r.status_code == 200
        d = r.json()
        rules = d if isinstance(d, list) else d.get("items", [])
        print("commission rules:", len(rules), "sample:", json.dumps(rules[:2], default=str)[:400])
        assert 150 <= len(rules) <= 160, len(rules)
        brands = {str(x.get("brand", "")).lower() for x in rules}
        assert not any("kazo" in b for b in brands), f"KAZO brand present in commission rules: {brands}"

    def test_fixed_fees_count(self, ac):
        r = ac.get(f"{API}/masters/fixed-fees", timeout=180)
        d = r.json()
        rows = d if isinstance(d, list) else d.get("items", [])
        print("fixed fees:", len(rows))
        # DB holds 272 slabs; endpoint hard-caps to_list(200) -> truncation defect
        assert len(rows) == 272, f"fixed-fees truncated: {len(rows)} of 272 returned"

    @pytest.mark.parametrize("ep", MASTER_ENDPOINTS)
    def test_no_kazo_in_master_payloads(self, ac, ep):
        r = ac.get(f"{API}{ep}", timeout=180)
        assert r.status_code == 200
        assert "kazo" not in r.text.lower(), f"KAZO string in {ep} payload"
