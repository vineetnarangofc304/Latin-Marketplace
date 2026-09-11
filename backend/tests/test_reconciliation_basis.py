"""Tests for reconciliation basis toggle (orderfile vs contract)."""
import os
import pytest
import requests

def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return v.rstrip("/")

BASE_URL = _load_base()
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@fundle.ai", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def test_login():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@fundle.ai", "password": "admin123"})
    assert r.status_code == 200
    assert "token" in r.json()


def test_overview_totals(h):
    r = requests.get(f"{API}/dashboard/overview", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    # sales/settlement totals
    ts = d.get("total_sales") or d.get("totalSales") or d.get("sales_count")
    tset = d.get("total_settlement_rows") or d.get("settlement_rows")
    print("overview:", {k: d.get(k) for k in d.keys()})
    assert ts == 42550, f"expected 42550 sales, got {ts}"
    assert tset == 28537, f"expected 28537 settlement rows, got {tset}"


def test_sales_ledger_rows(h):
    r = requests.get(f"{API}/sales?limit=1", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    total = body.get("total") if isinstance(body, dict) else None
    print("sales total:", total)
    assert total and total >= 42000, f"expected ~42550 rows, got {total}"


def test_recon_orderfile_allmonths(h):
    r = requests.post(f"{API}/reconciliation/run", json={"basis": "orderfile"}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    print("orderfile all:", d)
    matched = d.get("matched", 0)
    variance = d.get("variance") or d.get("variance_count") or d.get("discrepancies")
    unmatched = d.get("unmatched", 0)
    basis = d.get("basis")
    assert basis == "orderfile"
    assert unmatched == 0, f"unmatched should be 0, got {unmatched}"
    assert 28000 <= matched <= 28400, f"matched≈28195, got {matched}"
    assert 300 <= (variance or 0) <= 400, f"variance≈342, got {variance}"


def test_recon_contract_allmonths(h):
    r = requests.post(f"{API}/reconciliation/run", json={"basis": "contract"}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    print("contract all:", d)
    assert d.get("basis") == "contract"
    variance = d.get("variance") or d.get("variance_count") or d.get("discrepancies") or 0
    assert variance > 1000, f"contract variance should be large, got {variance}"


def test_recon_orderfile_permonth(h):
    r = requests.post(f"{API}/reconciliation/run", json={"basis": "orderfile", "report_month": "2026-06"}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    print("orderfile 2026-06:", d)
    assert d.get("basis") == "orderfile"
    assert d.get("unmatched", 0) == 0, f"unmatched should be 0 with cross-month netting, got {d.get('unmatched')}"


def test_recon_runs_have_basis(h):
    r = requests.get(f"{API}/reconciliation/runs", headers=h)
    assert r.status_code == 200, r.text
    runs = r.json()
    if isinstance(runs, dict):
        runs = runs.get("runs", runs.get("items", []))
    assert len(runs) > 0, "no runs found"
    for run in runs[:5]:
        assert "basis" in run, f"run missing basis field: {run}"


def test_zzz_reset_default_orderfile(h):
    """Leave system in default orderfile all-months state."""
    r = requests.post(f"{API}/reconciliation/run", json={"basis": "orderfile"}, headers=h)
    assert r.status_code == 200
    assert r.json().get("basis") == "orderfile"
