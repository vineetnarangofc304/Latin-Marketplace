"""Tests for SKU Costs upload, template, list, and P&L endpoints (summary/sku/monthly)."""
import io
import os
import csv
import pytest
import requests
import openpyxl

BASE_URL = "https://latin-quarter-mp.preview.emergentagent.com"
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@fundle.ai", "password": "admin123"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def hdr(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- SKU Costs ----------
def test_sku_cost_template_xlsx(hdr):
    r = requests.get(f"{API}/sku-costs/template", headers=hdr, timeout=30)
    assert r.status_code == 200
    assert r.content[:2] == b"PK"
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb.active
    headers = [c.value for c in ws[1]]
    assert "SKU" in headers and "Cost" in headers


def test_sku_costs_upload_csv_and_search(hdr):
    csv_data = "SKU,Cost\nTEST_PNL_SKU_A,111.5\nTEST_PNL_SKU_B,222\n"
    files = {"file": ("costs.csv", csv_data, "text/csv")}
    r = requests.post(f"{API}/sku-costs/upload", files=files, headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["accepted_count"] == 2

    r2 = requests.get(f"{API}/sku-costs", params={"search": "TEST_PNL_SKU_A"}, headers=hdr, timeout=30)
    assert r2.status_code == 200
    items = r2.json()["items"]
    assert any(i["sku"] == "TEST_PNL_SKU_A" and abs(i["cost"] - 111.5) < 0.01 for i in items)


def test_sku_costs_upload_case_insensitive_headers(hdr):
    csv_data = "sku,unit cost\nTEST_PNL_SKU_C,50\n"
    files = {"file": ("costs2.csv", csv_data, "text/csv")}
    r = requests.post(f"{API}/sku-costs/upload", files=files, headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["accepted_count"] == 1


def test_sku_costs_upload_missing_cost_column(hdr):
    csv_data = "SKU,Price\nTEST_PNL_SKU_D,50\n"
    files = {"file": ("costs_bad.csv", csv_data, "text/csv")}
    r = requests.post(f"{API}/sku-costs/upload", files=files, headers=hdr, timeout=30)
    assert r.status_code == 400
    assert "cost" in r.text.lower()


# Cleanup test data
def test_cleanup_test_skus(hdr):
    # We can only clear all - skip since risky. Leave test skus in DB (harmless).
    pass


# ---------- P&L ----------
def test_pnl_summary_2026_06(hdr):
    r = requests.get(f"{API}/pnl/summary", params={"period_type": "month", "period_value": "2026-06"}, headers=hdr, timeout=60)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["net_nsv"] > 0
    assert j["product_cost"] > 0
    assert j["net_pnl"] > 0
    assert 20 < j["margin_pct"] < 45, f"margin_pct={j['margin_pct']}"
    assert j["skus_missing_cost"] < 200
    print("summary:", j)


def test_pnl_by_sku_shape_and_sort(hdr):
    r = requests.get(
        f"{API}/pnl/sku",
        params={"period_type": "month", "period_value": "2026-06", "sort_by": "net_pnl", "sort_dir": "desc", "limit": 50},
        headers=hdr, timeout=60,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["total"] > 0
    items = j["items"]
    for req in ("sku", "net_units", "net_nsv", "fees", "taxes", "product_cost", "net_pnl", "margin_pct"):
        assert req in items[0], f"missing {req}"
    # sort desc
    pnls = [i["net_pnl"] for i in items]
    assert pnls == sorted(pnls, reverse=True)
    # identity checks on top row
    top = items[0]
    assert abs(top["net_pnl"] - round(top["settlement"] - top["product_cost"], 2)) < 0.05
    assert abs(top["fees"] - round(top["commission"] + top["gt_charge"] + top["fixed_fee"] + top["return_fee"], 2)) < 0.05


def test_pnl_by_sku_search(hdr):
    # Get any sku from the list first
    r = requests.get(f"{API}/pnl/sku", params={"period_type": "month", "period_value": "2026-06", "limit": 1}, headers=hdr, timeout=60)
    sku = r.json()["items"][0]["sku"]
    r2 = requests.get(f"{API}/pnl/sku", params={"period_type": "month", "period_value": "2026-06", "search": sku[:8]}, headers=hdr, timeout=60)
    assert r2.status_code == 200
    assert all(sku[:8].lower() in i["sku"].lower() for i in r2.json()["items"])


def test_pnl_monthly_includes_2026_06(hdr):
    r = requests.get(f"{API}/pnl/monthly", headers=hdr, timeout=60)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert isinstance(rows, list) and len(rows) > 0
    for req in ("month", "net_nsv", "fees", "taxes", "product_cost", "net_pnl", "margin_pct"):
        assert req in rows[0]
    months = [r["month"] for r in rows]
    assert "2026-06" in months


def test_pnl_consistency_sku_sum_vs_summary(hdr):
    s = requests.get(f"{API}/pnl/summary", params={"period_type": "month", "period_value": "2026-06"}, headers=hdr, timeout=60).json()
    sku = requests.get(f"{API}/pnl/sku", params={"period_type": "month", "period_value": "2026-06", "limit": 10000}, headers=hdr, timeout=60).json()
    total = round(sum(i["net_pnl"] for i in sku["items"]), 2)
    # allow small rounding
    assert abs(total - s["net_pnl"]) < max(5.0, abs(s["net_pnl"]) * 0.001), f"sku_sum={total} vs summary={s['net_pnl']}"
