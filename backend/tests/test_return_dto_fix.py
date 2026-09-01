"""Tests for iteration 8: Return-DTO uses Return Fee from Level/Zone matrix.
Bug fixes:
 (1) commission_incl_gst / fixed_fee_incl_gst in the drawer must be shown as pre-GST base + GST separately
 (2) Return-DTO's return_fee must come from return_fees master (level, zone), not fixed_fee
"""
import os
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"


def _login():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@kazo.com", "password": "admin123"})
    assert r.status_code == 200, r.text
    return s


def test_return_dto_math_uses_return_fee_master():
    s = _login()
    r = s.get(f"{API}/calculations", params={"order_type": "return_dto", "limit": 200})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) > 0

    # Build return_fees master lookup
    rf = s.get(f"{API}/masters/return-fees").json()
    matrix = {(x["level"], x["zone"]): float(x["fee"]) for x in rf}

    for row in items[:50]:
        assert row["commission_incl_gst"] == 0, row
        assert row["fixed_fee_incl_gst"] == 0, row
        assert row["gt_charge"] == 0, row
        assert row["tcs"] == 0, row
        assert row["tds"] == 0, row
        lvl = row["breakdown"].get("level")
        zn = row["breakdown"].get("zone")
        if lvl and zn and (lvl, zn) in matrix:
            expected_fee = matrix[(lvl, zn)]
            assert abs(row["return_fee"] - expected_fee) < 0.01, (
                f"Return fee mismatch: got {row['return_fee']} vs matrix {expected_fee} for {lvl}/{zn}"
            )
            nsv_val = row["breakdown"]["nsv_val"]
            expected_settle = -abs(nsv_val) - expected_fee
            assert abs(row["expected_settlement"] - expected_settle) < 0.05


def test_known_return_dto_order():
    """Order DFC4F34A-58F6-40EA-9AA1-2C13EB9F2140: nsv=-646, Level 1 / Zonal → fee=112 → settle=-758."""
    s = _login()
    r = s.get(f"{API}/calculations", params={"search": "DFC4F34A-58F6-40EA-9AA1-2C13EB9F2140", "limit": 5})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) > 0, "Known return_dto order not found"
    row = [x for x in items if x.get("order_type") == "return_dto"]
    assert row, "No return_dto row for known order id"
    row = row[0]
    assert row["breakdown"]["level"] == "Level 1"
    assert row["breakdown"]["zone"] == "Zonal"
    assert abs(row["return_fee"] - 112) < 0.01, f"expected 112 got {row['return_fee']}"
    assert abs(row["expected_settlement"] - (-758)) < 1.0


def test_aggregate_return_fee_sum():
    s = _login()
    # Fetch all return_dto rows (5443 rows, so paginate)
    total_return_fee = 0.0
    total_fixed_fee = 0.0
    skip = 0
    while True:
        r = s.get(f"{API}/calculations", params={"order_type": "return_dto", "limit": 2000, "skip": skip})
        items = r.json()["items"]
        if not items:
            break
        for x in items:
            total_return_fee += (x.get("return_fee") or 0)
            total_fixed_fee += (x.get("fixed_fee_incl_gst") or 0)
        skip += len(items)
        if len(items) < 2000:
            break
    print(f"return_dto sums: return_fee={total_return_fee:.2f}, fixed_fee_incl_gst={total_fixed_fee:.2f}")
    assert total_fixed_fee == 0, f"return_dto rows should have zero fixed_fee_incl_gst, got {total_fixed_fee}"
    # Expected ≈ 658,488
    assert 600000 < total_return_fee < 720000, f"return_fee sum out of expected range: {total_return_fee}"


def test_sales_regression():
    s = _login()
    total_settle = 0.0
    skip = 0
    while True:
        r = s.get(f"{API}/calculations", params={"order_type": "sales", "limit": 2000, "skip": skip})
        items = r.json()["items"]
        if not items:
            break
        for x in items:
            total_settle += (x.get("expected_settlement") or 0)
        skip += len(items)
        if len(items) < 2000:
            break
    print(f"sales expected_settlement sum: {total_settle:.2f}")
    assert 14000000 < total_settle < 15500000, f"Sales settlement out of range: {total_settle}"


def test_rto_internal_zero():
    s = _login()
    for ot in ("rto", "internal_cancel"):
        r = s.get(f"{API}/calculations", params={"order_type": ot, "limit": 100})
        items = r.json()["items"]
        for x in items:
            assert x["expected_settlement"] == 0, f"{ot} should be 0"
            assert x["commission_incl_gst"] == 0
            assert x["fixed_fee_incl_gst"] == 0


def test_dashboard_endpoints_still_200():
    s = _login()
    for ep in [
        "/dashboard/overview?period_type=month&period_value=2026-04",
        "/dashboard/return-velocity?period_type=month&period_value=2026-04",
        "/insights/health-score?period_type=month&period_value=2026-04",
    ]:
        r = s.get(f"{API}{ep}")
        assert r.status_code == 200, f"{ep} → {r.status_code}"
