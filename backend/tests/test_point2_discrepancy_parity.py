"""
Point 2 regression: variance-discrepancy 'expected' block must equal linked calculation.
Also validates stale-clearing (single recon_run_id), SKU parity, and specific order 100152032783.
"""
import os
import requests
import pytest

def _load_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    return os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

BASE = _load_env()
API = f"{BASE}/api"
ORDER = "100152032783"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@fundle.ai", "password": "admin123"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# --- Reconciliation idempotency / stale clearing ---
def test_reconciliation_run_and_single_run_id(auth):
    r = requests.post(f"{API}/reconciliation/run", json={}, headers=auth, timeout=300)
    assert r.status_code == 200, r.text
    body = r.json()
    run_id_1 = body.get("recon_run_id") or body.get("run_id") or body.get("id")
    # Run again to test stale clearing
    r2 = requests.post(f"{API}/reconciliation/run", json={}, headers=auth, timeout=300)
    assert r2.status_code == 200
    # After the second run all discrepancies should have exactly one distinct recon_run_id
    # Query all discrepancies (paginate)
    seen_run_ids = set()
    page = 1
    total_seen = 0
    while True:
        rr = requests.get(f"{API}/reconciliation/discrepancies",
                          params={"page": page, "page_size": 500}, headers=auth, timeout=120)
        assert rr.status_code == 200
        data = rr.json()
        items = data.get("items") or data.get("data") or []
        if not items:
            break
        for d in items:
            rid = d.get("recon_run_id")
            if rid:
                seen_run_ids.add(rid)
        total_seen += len(items)
        if len(items) < 500:
            break
        page += 1
        if page > 200:
            break
    print(f"Total discrepancies seen: {total_seen}, distinct run_ids: {seen_run_ids}")
    assert len(seen_run_ids) == 1, f"Stale run_ids present: {seen_run_ids}"


# --- Specific order 100152032783 ---
def test_order_100152032783_matches_calc_panel(auth):
    r = requests.get(f"{API}/reconciliation/discrepancies",
                     params={"search": ORDER, "page_size": 20}, headers=auth, timeout=60)
    assert r.status_code == 200
    items = r.json().get("items") or r.json().get("data") or []
    assert items, f"No discrepancy found for {ORDER}"
    target = [d for d in items if d.get("online_order_id") == ORDER]
    assert target, f"Order {ORDER} not in results"
    disc = target[0]

    # Fetch detail
    detail = requests.get(f"{API}/reconciliation/discrepancy/{disc['id']}", headers=auth, timeout=30)
    assert detail.status_code == 200
    d = detail.json()

    assert d["match_status"] == "variance", f"expected variance got {d['match_status']}"
    assert d["sku"] == "LTQRSHRT118021261", f"SKU mismatch: {d['sku']}"

    exp = d["expected"]
    # Client-provided values from the calc drawer
    assert round(float(exp["commission_incl_gst"]), 2) == 34.35
    assert round(float(exp["gt_charge"]), 2) == 31.86
    assert round(float(exp["fixed_fee_incl_gst"]), 2) == 60.18
    assert round(float(exp["expected_settlement"]), 2) == 387.70

    # Component-level compare
    comps = {c["component"]: c for c in d["components"]}
    assert round(comps["commission"]["expected"], 2) == 34.35
    assert round(comps["gt_charge"]["expected"], 2) == 31.86
    assert round(comps["fixed_fee"]["expected"], 2) == 60.18
    assert round(comps["net_settlement"]["expected"], 2) == 387.70


# --- Global parity: every variance discrepancy's expected == its linked calc ---
def test_all_variance_expected_equals_calc(auth):
    # sample a chunk of variance rows and verify against /calculations/{sales_id} or via calc_id lookup
    r = requests.get(f"{API}/reconciliation/discrepancies",
                     params={"status": "variance", "page_size": 500, "page": 1},
                     headers=auth, timeout=120)
    assert r.status_code == 200
    items = r.json().get("items") or r.json().get("data") or []
    # take up to 200 samples
    sample = items[:200]
    assert sample, "No variance discrepancies to check"

    mismatches = []
    checked = 0
    for row in sample:
        det = requests.get(f"{API}/reconciliation/discrepancy/{row['id']}", headers=auth, timeout=20)
        if det.status_code != 200:
            continue
        d = det.json()
        exp = d.get("expected") or {}
        calc_id = d.get("calc_id")
        sales_id = d.get("sales_id")
        if not calc_id and not sales_id:
            continue
        # fetch calc by sales_id via calculations endpoint
        cr = requests.get(f"{API}/calculations", params={"search": d["online_order_id"], "page_size": 20},
                          headers=auth, timeout=30)
        if cr.status_code != 200:
            continue
        citems = cr.json().get("items") or cr.json().get("data") or []
        calc = None
        for c in citems:
            if c.get("id") == calc_id or c.get("sales_id") == sales_id:
                calc = c
                break
        if not calc:
            continue
        checked += 1
        fields = ["commission_incl_gst", "gt_charge", "fixed_fee_incl_gst", "expected_settlement"]
        for f in fields:
            e = round(float(exp.get(f, 0)), 2)
            v = round(float(calc.get(f, 0)), 2)
            if e != v:
                mismatches.append((d["id"], d["online_order_id"], f, e, v))
        # SKU parity: variance discrepancy sku should equal sale.sku
        # Compare against calc's sku if present
        if calc.get("sku") and d.get("sku") and calc["sku"] != d["sku"]:
            mismatches.append((d["id"], d["online_order_id"], "sku", d["sku"], calc["sku"]))

    print(f"Checked {checked} variance rows; mismatches={len(mismatches)}")
    if mismatches[:10]:
        print("Sample mismatches:", mismatches[:10])
    assert not mismatches, f"{len(mismatches)} expected/calc mismatches"


# --- Login regression ---
def test_login_regression():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@fundle.ai", "password": "admin123"}, timeout=30)
    assert r.status_code == 200
    assert "token" in r.json()
