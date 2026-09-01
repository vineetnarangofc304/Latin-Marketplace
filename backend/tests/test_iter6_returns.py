"""Iteration 6: Sales returns + calculations completeness tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ledger-dashboard-13.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

EXPECTED_TOTAL = 21614
EXPECTED_COUNTS = {
    "sales": 12246,
    "return_dto": 5443,
    "rto": 3705,
    "internal_cancel": 128,
    "return": 92,
}


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@kazo.com", "password": "admin123"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# --- Sales dataset completeness ---
def test_sales_total_count(session):
    r = session.get(f"{API}/sales", params={"limit": 1})
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    total = data.get("total") or data.get("count") or data.get("total_count")
    print(f"Sales total: {total}")
    assert total == EXPECTED_TOTAL, f"expected {EXPECTED_TOTAL}, got {total}"


def test_sales_returns_present(session):
    r = session.get(f"{API}/sales", params={"txn_type": "Return", "limit": 5})
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    items = data.get("items") or data.get("data") or data.get("results") or []
    assert len(items) > 0, f"no return rows: {data}"
    for it in items:
        assert it.get("txn_type") == "Return", it
        nsv = it.get("nsv_val")
        assert nsv is not None and nsv < 0, f"expected negative nsv, got {nsv}: {it}"


def test_sales_months(session):
    r = session.get(f"{API}/sales/months")
    assert r.status_code == 200, r.text[:300]
    months = r.json()
    # format may be list of {month, count} or dict
    found = None
    if isinstance(months, list):
        for m in months:
            if m.get("month") == "2026-04" or m.get("_id") == "2026-04":
                found = m.get("count")
                break
    print(f"months: {months}")
    assert found == EXPECTED_TOTAL, f"expected April count {EXPECTED_TOTAL}, got {found}"


# --- Calculations completeness ---
def test_calculations_total(session):
    r = session.get(f"{API}/calculations", params={"limit": 1})
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    total = data.get("total") or data.get("count") or data.get("total_count")
    print(f"Calc total: {total}")
    assert total == EXPECTED_TOTAL, f"expected {EXPECTED_TOTAL}, got {total}"


# --- Order-type distribution via Mongo ---
def test_order_type_distribution():
    from pymongo import MongoClient
    mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db_name = os.environ.get("DB_NAME", "test_database")
    db = mc[db_name]
    pipeline = [{"$group": {"_id": "$order_type", "n": {"$sum": 1}}}]
    counts = {d["_id"]: d["n"] for d in db.calculations.aggregate(pipeline)}
    print(f"order_type counts: {counts}")
    total = sum(counts.values())
    assert total == EXPECTED_TOTAL, f"sum {total} != {EXPECTED_TOTAL}"
    for k, v in EXPECTED_COUNTS.items():
        assert counts.get(k) == v, f"{k}: expected {v}, got {counts.get(k)}"


# --- Math validation ---
def _get_sample(db, order_type):
    d = db.calculations.find_one({"order_type": order_type})
    if d and "nsv_val" not in d and isinstance(d.get("breakdown"), dict):
        # nsv_val lives inside breakdown sub-doc
        d["nsv_val"] = d["breakdown"].get("nsv_val")
    return d


def test_math_sales():
    from pymongo import MongoClient
    db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "test_database")]
    d = _get_sample(db, "sales")
    assert d, "no sales doc"
    nsv = abs(d["nsv_val"]); gt = abs(d.get("gt_charge", 0))
    assert abs(d["nsv_after_gt"] - (nsv - gt)) < 0.05, d
    cp = d.get("commission_pct", 0)
    expected_comm = d["nsv_after_gt"] * cp * 1.18
    assert abs(d["commission_incl_gst"] - expected_comm) < 0.05, (d["commission_incl_gst"], expected_comm)
    exp_settle = d["nsv_after_gt"] - (d["commission_incl_gst"] + d.get("fixed_fee_incl_gst", 0) + d.get("gt_charge", 0) + d.get("tcs", 0) + d.get("tds", 0))
    assert abs(d["expected_settlement"] - exp_settle) < 0.10, (d["expected_settlement"], exp_settle)


def test_math_return_dto():
    from pymongo import MongoClient
    db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "test_database")]
    d = _get_sample(db, "return_dto")
    assert d, "no return_dto doc"
    assert d.get("commission_incl_gst", 0) == 0, d
    assert d.get("gt_charge", 0) == 0, d
    assert d.get("tcs", 0) == 0 and d.get("tds", 0) == 0, d
    ff = d.get("fixed_fee_incl_gst", 0)
    rf = d.get("return_fee", 0)
    assert abs(rf - ff) < 0.01, (rf, ff)
    nsv_after = -abs(d["nsv_val"])
    assert abs(d["nsv_after_gt"] - nsv_after) < 0.05, (d["nsv_after_gt"], nsv_after)
    assert abs(d["expected_settlement"] - (nsv_after - rf)) < 0.10, d


def test_math_return():
    from pymongo import MongoClient
    db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "test_database")]
    d = _get_sample(db, "return")
    assert d, "no return doc"
    assert d["nsv_val"] < 0, d
    assert d.get("commission_incl_gst", 0) <= 0, d
    assert d.get("return_fee", 0) > 0, d


def test_math_rto_zero():
    from pymongo import MongoClient
    db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "test_database")]
    for ot in ["rto", "internal_cancel"]:
        d = _get_sample(db, ot)
        assert d, f"no {ot} doc"
        for k in ["commission_incl_gst", "fixed_fee_incl_gst", "gt_charge", "return_fee", "tcs", "tds", "expected_settlement"]:
            assert d.get(k, 0) == 0, f"{ot}: {k}={d.get(k)}"
        assert d.get("unmapped") is False, d


# --- Financial impact ---
def test_financial_aggregates():
    from pymongo import MongoClient
    db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "test_database")]
    pipeline = [{"$group": {"_id": "$order_type", "s": {"$sum": "$expected_settlement"}}}]
    agg = {d["_id"]: d["s"] for d in db.calculations.aggregate(pipeline)}
    print(f"settle by type: {agg}")
    total = sum(agg.values())
    print(f"grand total: {total}")
    assert abs(total - 4_631_550) / 4_631_550 < 0.02, total
    assert abs(agg.get("sales", 0) - 14_690_173) / 14_690_173 < 0.02, agg.get("sales")
    assert abs(agg.get("return_dto", 0) - (-9_797_947)) / 9_797_947 < 0.02, agg.get("return_dto")
    assert abs(agg.get("rto", 0)) < 1, agg.get("rto")
    assert abs(agg.get("internal_cancel", 0)) < 1, agg.get("internal_cancel")


# --- Regression: BA030AAB search ---
def test_search_ba030aab(session):
    r = session.get(f"{API}/calculations", params={"search": "BA030AAB", "limit": 20})
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    items = data.get("items") or data.get("data") or []
    print(f"BA030AAB items: {len(items)}")
    assert len(items) >= 2, f"expected 2 rows, got {len(items)}: {items}"
    types = sorted([i.get("order_type") for i in items])
    print(f"types: {types}")
    assert "sales" in types
    assert "return_dto" in types
