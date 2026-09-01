"""Backend tests for Return Velocity feature (iteration 7).

Covers:
  - GET /api/dashboard/return-velocity structure + magnitudes
  - by_sub_category ordering by fixed_fee_leakage desc
  - empty state (no data)
  - /api/calculations order_type filter
  - regressions on existing dashboards
"""
import os
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://ledger-dashboard-13.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
PERIOD = ("month", "2026-04")


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@kazo.com", "password": "admin123"},
                      timeout=30)
    assert r.status_code == 200, r.text
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="session")
def client(token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ---------- Return Velocity ----------

class TestReturnVelocity:
    def test_structure_and_magnitudes(self, client):
        r = client.get(f"{API}/dashboard/return-velocity",
                       params={"period_type": "month", "period_value": "2026-04", "top": 12},
                       timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "overall" in data and "by_sub_category" in data
        o = data["overall"]
        for k in ["sales_orders", "return_dto_orders", "return_orders", "rto_orders",
                  "internal_cancel_orders", "velocity_pct", "total_fixed_fee_leakage"]:
            assert k in o, f"missing key {k}"

        # Magnitudes (allow small tolerance)
        assert abs(o["sales_orders"] - 12246) <= 50, o
        assert abs(o["return_dto_orders"] - 5443) <= 50, o
        assert abs(o["return_orders"] - 92) <= 20, o
        assert abs(o["rto_orders"] - 3705) <= 50, o
        assert abs(o["internal_cancel_orders"] - 128) <= 20, o
        assert abs(o["velocity_pct"] - 0.444) < 0.02, o["velocity_pct"]
        assert abs(o["total_fixed_fee_leakage"] - 285046) < 5000, o["total_fixed_fee_leakage"]

    def test_by_sub_category_sorted_and_dresses_top(self, client):
        r = client.get(f"{API}/dashboard/return-velocity",
                       params={"period_type": "month", "period_value": "2026-04", "top": 12})
        assert r.status_code == 200
        rows = r.json()["by_sub_category"]
        assert len(rows) > 0
        # descending by fixed_fee_leakage
        leakages = [row["fixed_fee_leakage"] for row in rows]
        assert leakages == sorted(leakages, reverse=True), leakages
        # each row has required keys
        for k in ["sub_category", "orders", "return_dto_orders", "return_orders",
                  "rto_orders", "fixed_fee_leakage", "sales_nsv", "velocity_pct"]:
            assert k in rows[0], f"missing {k} in row"
        # Top row: Dresses
        top = rows[0]
        assert top["sub_category"].lower() == "dresses", top["sub_category"]
        assert abs(top["velocity_pct"] - 0.586) < 0.05, top["velocity_pct"]
        assert abs(top["fixed_fee_leakage"] - 88599) < 3000, top["fixed_fee_leakage"]

    def test_empty_state(self, client):
        r = client.get(f"{API}/dashboard/return-velocity",
                       params={"period_type": "month", "period_value": "2099-12"})
        assert r.status_code == 200
        d = r.json()
        assert d["overall"]["sales_orders"] == 0
        assert d["by_sub_category"] == []


# ---------- /api/calculations order_type filter ----------

class TestCalculationsOrderTypeFilter:
    def test_return_dto_total(self, client):
        r = client.get(f"{API}/calculations",
                       params={"order_type": "return_dto",
                               "period_type": "month", "period_value": "2026-04",
                               "limit": 1})
        assert r.status_code == 200
        total = r.json()["total"]
        assert abs(total - 5443) <= 50, total

    def test_sales_total(self, client):
        r = client.get(f"{API}/calculations",
                       params={"order_type": "sales",
                               "period_type": "month", "period_value": "2026-04",
                               "limit": 1})
        assert r.status_code == 200
        total = r.json()["total"]
        assert abs(total - 12246) <= 50, total

    def test_dresses_return_dto_matches_velocity_row(self, client):
        # cross-check: total for Dresses+return_dto == the row's return_dto_orders
        rv = client.get(f"{API}/dashboard/return-velocity",
                        params={"period_type": "month", "period_value": "2026-04", "top": 12}).json()
        dresses = next(r for r in rv["by_sub_category"] if r["sub_category"].lower() == "dresses")
        r = client.get(f"{API}/calculations",
                       params={"order_type": "return_dto", "period_type": "month",
                               "period_value": "2026-04", "sub_category": dresses["sub_category"],
                               "limit": 1})
        assert r.status_code == 200
        assert r.json()["total"] == dresses["return_dto_orders"]


# ---------- Regression ----------

class TestRegression:
    def test_overview(self, client):
        r = client.get(f"{API}/dashboard/overview",
                       params={"period_type": "month", "period_value": "2026-04"})
        assert r.status_code == 200

    def test_commission_summary(self, client):
        r = client.get(f"{API}/dashboard/commission-summary",
                       params={"period_type": "month", "period_value": "2026-04"})
        assert r.status_code == 200

    def test_recon_summary(self, client):
        r = client.get(f"{API}/dashboard/reconciliation-summary",
                       params={"period_type": "month", "period_value": "2026-04"})
        assert r.status_code == 200

    def test_health_score(self, client):
        r = client.get(f"{API}/insights/health-score",
                       params={"period_type": "month", "period_value": "2026-04"})
        assert r.status_code == 200
