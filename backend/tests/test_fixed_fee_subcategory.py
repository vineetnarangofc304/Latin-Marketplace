"""Regression tests for the fixed-fee slab sub-category matching bug.

Bug: _match_fixed_fee matched only by AISP price band, so a 'Tops' order could
match the 'Dresses' slab. Fix filters by sub_category first.
"""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing")
BASE_URL = base_url.rstrip("/")

REPORTED_ORDER_ID = "100137423450"
REPORTED_SKU = "LTQRTOPS119573072"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def token(client):
    r = client.post(f"{BASE_URL}/api/auth/login",
                    json={"email": "admin@fundle.ai", "password": "admin123"})
    if r.status_code != 200:
        pytest.fail(f"Login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        pytest.fail(f"No token in login response: {r.text[:300]}")
    return tok


@pytest.fixture(scope="module")
def auth(client, token):
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# ---------------- Health / smoke ----------------
class TestSmoke:
    def test_calculations_list_returns_rows(self, auth):
        r = auth.get(f"{BASE_URL}/api/calculations", params={"limit": 5})
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["total"] > 0
        assert isinstance(data["items"], list) and len(data["items"]) > 0
        assert "breakdown" in data["items"][0]

    def test_no_mongo_id_leak(self, auth):
        r = auth.get(f"{BASE_URL}/api/calculations", params={"limit": 5})
        for item in r.json()["items"]:
            assert "_id" not in item


# ---------------- Primary bug fix: reported order ----------------
class TestReportedOrder:
    @pytest.fixture(scope="class")
    def reported_calc(self, auth):
        r = auth.get(f"{BASE_URL}/api/calculations",
                     params={"search": REPORTED_ORDER_ID, "limit": 50})
        assert r.status_code == 200, r.text[:300]
        items = r.json()["items"]
        assert items, f"No calculation found for order {REPORTED_ORDER_ID}"
        match = [i for i in items if i.get("sku") == REPORTED_SKU] or items
        return match[0]

    def test_reported_order_subcategory_is_tops(self, reported_calc):
        assert reported_calc["breakdown"]["sub_category"].strip().lower() == "tops"

    def test_reported_order_fixed_fee_slab_label_is_tops(self, reported_calc):
        slab = reported_calc["breakdown"]["fixed_fee_slab"]
        assert slab["label"] == "Tops", f"Expected 'Tops' slab, got {slab}"

    def test_reported_order_fixed_fee_value(self, reported_calc):
        slab = reported_calc["breakdown"]["fixed_fee_slab"]
        assert float(slab["fixed_fee"]) == 52.0, f"Expected 52.0, got {slab['fixed_fee']}"


# ---------------- Broad audit: invariant across all mapped non-return rows ----------------
def _page(auth, **params):
    r = auth.get(f"{BASE_URL}/api/calculations", params=params)
    assert r.status_code == 200, r.text[:300]
    return r.json()


class TestFixedFeeInvariantAudit:
    def test_all_mapped_sales_rows_slab_matches_subcategory(self, auth):
        mismatches = []
        checked = 0
        skip = 0
        limit = 2000
        total = None
        while True:
            data = _page(auth, severity_flag="mapped", order_type="sales",
                         limit=limit, skip=skip, sort_by="order_id", sort_dir="asc")
            if total is None:
                total = data["total"]
            items = data["items"]
            if not items:
                break
            for it in items:
                bd = it.get("breakdown") or {}
                slab = bd.get("fixed_fee_slab") or {}
                label = slab.get("label")
                sub = bd.get("sub_category")
                if label is None:
                    continue  # no slab matched (unmapped component) - not a mismatch
                checked += 1
                if (label or "").strip().lower() != (sub or "").strip().lower():
                    if len(mismatches) < 20:
                        mismatches.append({
                            "order_id": it.get("online_order_id"),
                            "sku": it.get("sku"),
                            "sub_category": sub,
                            "slab_label": label,
                        })
            skip += limit
            if skip >= total:
                break
        print(f"Audited {checked} mapped sales rows (total mapped sales={total}); mismatches={len(mismatches)}")
        assert not mismatches, f"Fixed fee slab sub-category mismatches: {mismatches}"

    @pytest.mark.parametrize("sub", ["Tops", "Trousers", "Blazers", "Coats", "Dresses", "Shrug"])
    def test_per_subcategory_slab_label(self, auth, sub):
        data = _page(auth, sub_category=sub, severity_flag="mapped",
                     order_type="sales", limit=100)
        items = data["items"]
        if not items:
            pytest.skip(f"No mapped sales rows for sub_category {sub}")
        bad = [
            {"order_id": i.get("online_order_id"),
             "slab": (i["breakdown"]["fixed_fee_slab"] or {}).get("label")}
            for i in items
            if (i["breakdown"].get("fixed_fee_slab") or {}).get("label")
            and (i["breakdown"]["fixed_fee_slab"]["label"] or "").strip().lower() != sub.lower()
        ]
        assert not bad, f"{sub}: wrong slab labels -> {bad[:10]}"


# ---------------- Regression: other matched rules populate ----------------
class TestOtherRulesRegression:
    def test_commission_gt_populated_for_mapped_sales(self, auth):
        data = _page(auth, severity_flag="mapped", order_type="sales", limit=200)
        items = data["items"]
        assert items
        for it in items[:200]:
            bd = it["breakdown"]
            assert bd["commission_rule"]["commission_pct"] is not None, it.get("online_order_id")
            assert bd["gt_charge_cell"]["unit_charge"] is not None, it.get("online_order_id")
            assert bd["fixed_fee_slab"]["fixed_fee"] is not None, it.get("online_order_id")
            assert it.get("expected_settlement") is not None
            assert it.get("total_deductions") is not None

    def test_return_rows_have_return_fee_zone(self, auth):
        data = _page(auth, severity_flag="mapped", order_type="return", limit=100)
        items = data["items"]
        if not items:
            pytest.skip("No mapped return rows")
        for it in items:
            cell = it["breakdown"]["return_fee_cell"]
            assert cell["applied"] is True
            assert cell["zone"] is not None
            assert cell["fee"] is not None

    def test_masters_gt_and_return_fee_counts(self, auth):
        gt = auth.get(f"{BASE_URL}/api/masters/gt-charges", params={"limit": 500})
        rf = auth.get(f"{BASE_URL}/api/masters/return-fees", params={"limit": 500})
        assert gt.status_code == 200, gt.text[:200]
        assert rf.status_code == 200, rf.text[:200]

        def count(resp):
            d = resp.json()
            if isinstance(d, list):
                return len(d)
            return d.get("total", len(d.get("items", [])))

        assert count(gt) == 96, f"GT rows = {count(gt)}"
        assert count(rf) == 12, f"Return fee rows = {count(rf)}"
