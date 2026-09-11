"""Tests for Ad Spend + P&L integration and Breakage Claims (iteration 7)."""
import io
import os
import pytest
import requests
import openpyxl

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://latin-quarter-mp.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login('admin@fundle.ai', 'admin123')}"}


@pytest.fixture(scope="module")
def viewer_headers():
    return {"Authorization": f"Bearer {_login('marketing@fundle.ai', 'admin123')}"}


# ---------- Ad Spend ----------
class TestAdSpend:
    def test_template_download(self, admin_headers):
        r = requests.get(f"{API}/ad-spend/template", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers.get("content-type", "")
        assert len(r.content) > 100

    def test_list_ad_spend_has_existing_uploads(self, admin_headers):
        r = requests.get(f"{API}/ad-spend", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "total_spend" in data
        months = {i["report_month"]: i["amount"] for i in data["items"]}
        # per agent-to-agent context: 2026-05 = 42000, 2026-06 = 50000 already uploaded
        assert "2026-06" in months, f"expected 2026-06 in {months}"
        assert months["2026-06"] == 50000

    def test_upload_ad_spend_roundtrip(self, admin_headers):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Month", "Amount"])
        ws.append(["2026-06", 50000])
        ws.append(["2026-05", 42000])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        files = {"file": ("adspend.xlsx", buf.getvalue(),
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = requests.post(f"{API}/ad-spend/upload", headers=admin_headers, files=files, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["accepted_count"] == 2
        assert j["total_months"] >= 2

    def test_upload_ad_spend_viewer_forbidden(self, viewer_headers):
        buf = io.BytesIO(b"Month,Amount\n2026-06,50000\n")
        files = {"file": ("a.csv", buf.getvalue(), "text/csv")}
        r = requests.post(f"{API}/ad-spend/upload", headers=viewer_headers, files=files, timeout=30)
        assert r.status_code == 403


# ---------- P&L integration ----------
class TestPnLIntegration:
    def test_summary_contains_new_fields(self, admin_headers):
        r = requests.get(f"{API}/pnl/summary", headers=admin_headers, timeout=60)
        assert r.status_code == 200
        d = r.json()
        for k in ("ad_spend", "net_contribution", "contribution_margin_pct", "net_pnl", "net_nsv"):
            assert k in d, f"missing {k} in {list(d.keys())}"
        # net_contribution should equal net_pnl - ad_spend (within 1)
        assert abs(d["net_contribution"] - (d["net_pnl"] - d["ad_spend"])) < 1

    def test_monthly_has_ad_spend(self, admin_headers):
        r = requests.get(f"{API}/pnl/monthly", headers=admin_headers, timeout=60)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0
        for row in rows:
            assert "ad_spend" in row and "net_contribution" in row
        june = next((x for x in rows if x["month"] == "2026-06"), None)
        assert june is not None, f"2026-06 not in months {[r['month'] for r in rows]}"
        assert june["ad_spend"] == 50000, f"expected 50000, got {june['ad_spend']}"

    def test_sku_has_ad_spend_and_identity(self, admin_headers):
        r = requests.get(f"{API}/pnl/sku?limit=100", headers=admin_headers, timeout=60)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) > 0
        for row in items[:20]:
            assert "ad_spend" in row and "net_contribution" in row
            # SKU-level identity: net_pnl == settlement - product_cost (ad_spend not deducted at SKU net_pnl level)
            assert abs(row["net_pnl"] - (row["settlement"] - row["product_cost"])) < 1, row


# ---------- Breakage Claims ----------
class TestClaims:
    def test_list_breakage(self, admin_headers):
        r = requests.get(f"{API}/claims/breakage?limit=5", headers=admin_headers, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "summary" in d and "total" in d
        assert d["summary"]["total_cases"] == d["total"]

    def test_scan_viewer_forbidden(self, viewer_headers):
        r = requests.post(f"{API}/claims/breakage/scan", headers=viewer_headers,
                          json={"materiality": 200}, timeout=60)
        assert r.status_code == 403

    def test_list_open_status_filter(self, admin_headers):
        r = requests.get(f"{API}/claims/breakage?status=open&limit=3", headers=admin_headers, timeout=60)
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["status"] == "open"

    def test_email_body_present(self, admin_headers):
        r = requests.get(f"{API}/claims/breakage?limit=1", headers=admin_headers, timeout=60)
        items = r.json()["items"]
        if not items:
            pytest.skip("no claims present")
        it = items[0]
        for k in ("email_to", "email_subject", "email_body", "claim_amount", "sku", "online_order_id"):
            assert k in it, f"missing {k}"
        assert "Inventory Breakage" in it["email_subject"]
        assert it["online_order_id"] in it["email_subject"] or str(it["online_order_id"]) in it["email_body"]

    def test_patch_status_admin(self, admin_headers):
        r = requests.get(f"{API}/claims/breakage?status=open&limit=1", headers=admin_headers, timeout=60)
        items = r.json()["items"]
        if not items:
            pytest.skip("no open claims")
        cid = items[0]["id"]
        # mark emailed
        r = requests.patch(f"{API}/claims/breakage/{cid}", headers=admin_headers,
                           json={"status": "emailed"}, timeout=30)
        assert r.status_code == 200
        # verify
        r = requests.get(f"{API}/claims/breakage?search={items[0]['sku']}&limit=50",
                         headers=admin_headers, timeout=30)
        found = next((x for x in r.json()["items"] if x["id"] == cid), None)
        assert found and found["status"] == "emailed"
        # restore
        requests.patch(f"{API}/claims/breakage/{cid}", headers=admin_headers,
                       json={"status": "open"}, timeout=30)

    def test_patch_status_viewer_forbidden(self, viewer_headers, admin_headers):
        r = requests.get(f"{API}/claims/breakage?limit=1", headers=admin_headers, timeout=30)
        items = r.json()["items"]
        if not items:
            pytest.skip("no claims")
        cid = items[0]["id"]
        r = requests.patch(f"{API}/claims/breakage/{cid}", headers=viewer_headers,
                           json={"status": "resolved"}, timeout=30)
        assert r.status_code == 403

    def test_patch_invalid_status(self, admin_headers):
        r = requests.get(f"{API}/claims/breakage?limit=1", headers=admin_headers, timeout=30)
        items = r.json()["items"]
        if not items:
            pytest.skip("no claims")
        cid = items[0]["id"]
        r = requests.patch(f"{API}/claims/breakage/{cid}", headers=admin_headers,
                           json={"status": "bogus"}, timeout=30)
        assert r.status_code == 400
