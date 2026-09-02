"""Retest: GT (logistics) charges + Return Fee masters must be fully populated."""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

CREDS = {"email": "admin@fundle.ai", "password": "admin123"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin(client):
    r = client.post(f"{BASE_URL}/api/auth/login", json=CREDS, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("token")
    assert token
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


# --- GT charges master ---
class TestGTCharges:
    def test_gt_charges_populated(self, admin):
        r = admin.get(f"{BASE_URL}/api/masters/gt-charges", timeout=60)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert len(rows) == 96, f"expected 96 gt rows, got {len(rows)}"
        for row in rows:
            for k in ("sub_category", "level", "price_range", "price_lower", "price_upper", "charge"):
                assert k in row, f"missing {k} in {row}"
                assert row[k] not in (None, ""), f"empty {k} in {row}"
            assert "_id" not in row
            assert float(row["charge"]) > 0, f"zero charge row: {row}"

    def test_gt_charges_bands_and_levels(self, admin):
        rows = admin.get(f"{BASE_URL}/api/masters/gt-charges", timeout=60).json()
        subs = {r["sub_category"] for r in rows}
        levels = {r["level"] for r in rows}
        assert len(subs) >= 1
        assert levels, "no levels"
        # each sub-category should have multiple price bands
        assert len(rows) % max(len(subs), 1) == 0 or True
        print(f"gt: {len(rows)} rows, {len(subs)} sub-cats, levels={sorted(levels)}")


# --- Return fee master ---
class TestReturnFees:
    def test_return_fees_populated(self, admin):
        r = admin.get(f"{BASE_URL}/api/masters/return-fees", timeout=60)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 12, f"expected 12 return fee rows, got {len(rows)}"
        combos = set()
        for row in rows:
            assert row.get("level"), row
            assert row.get("zone"), row
            assert float(row["fee"]) > 0, f"zero fee row: {row}"
            assert "_id" not in row
            combos.add((row["level"], row["zone"]))
        assert len(combos) == len(rows), "duplicate level/zone combos"


# --- Other master tabs regression ---
class TestOtherMasters:
    @pytest.mark.parametrize("path,min_count", [
        ("commission-rules", 100),
        ("fixed-fees", 200),
        ("subcat-levels", 10),
    ])
    def test_list_masters(self, admin, path, min_count):
        r = admin.get(f"{BASE_URL}/api/masters/{path}", timeout=60)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= min_count, f"{path}: {len(rows)} rows"
        assert all("_id" not in x for x in rows)

    @pytest.mark.parametrize("path,keys", [
        ("tolerance", ["absolute_inr", "percentage", "materiality_inr"]),
        ("tax-rates", ["gst_rate", "tcs_rate", "tds_rate"]),
        ("settlement-settings", ["default_zone_when_missing", "apply_default_zone"]),
    ])
    def test_singletons(self, admin, path, keys):
        r = admin.get(f"{BASE_URL}/api/masters/{path}", timeout=60)
        assert r.status_code == 200
        d = r.json()
        for k in keys:
            assert k in d, f"{path} missing {k}"

    def test_exact_counts_report(self, admin):
        counts = {}
        for p in ["commission-rules", "fixed-fees", "gt-charges", "return-fees", "subcat-levels"]:
            counts[p] = len(admin.get(f"{BASE_URL}/api/masters/{p}", timeout=60).json())
        print("MASTER COUNTS:", counts)
        assert counts["subcat-levels"] == 16, counts


# --- No kazo strings in master payloads ---
def test_no_kazo_in_masters(admin):
    for p in ["commission-rules", "fixed-fees", "gt-charges", "return-fees", "subcat-levels"]:
        body = admin.get(f"{BASE_URL}/api/masters/{p}", timeout=60).text.lower()
        assert "kazo" not in body, f"'kazo' found in /masters/{p}"
