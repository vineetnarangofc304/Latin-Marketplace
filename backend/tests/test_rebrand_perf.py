"""Tests for rebrand + performance pass (iteration_4)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ledger-dashboard-13.preview.emergentagent.com").rstrip("/")
PERIOD = "2026-04"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@kazo.com", "password": "admin123"},
               timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


ENDPOINTS = [
    f"/api/dashboard/overview?period_type=month&period_value={PERIOD}",
    f"/api/dashboard/commission-summary?period_type=month&period_value={PERIOD}",
    f"/api/dashboard/reconciliation-summary?period_type=month&period_value={PERIOD}",
    f"/api/reports/period?period_type=month&period_value={PERIOD}",
    f"/api/reports/monthly?month={PERIOD}",
    f"/api/insights/health-score?period_type=month&period_value={PERIOD}",
    f"/api/recovery/summary?period_type=month&period_value={PERIOD}",
]


@pytest.mark.parametrize("path", ENDPOINTS)
def test_endpoint_latency_cache(client, path):
    url = f"{BASE_URL}{path}"
    t1 = time.time(); r1 = client.get(url, timeout=15); d1 = time.time() - t1
    assert r1.status_code == 200, f"first call {path} => {r1.status_code} {r1.text[:200]}"
    t2 = time.time(); r2 = client.get(url, timeout=15); d2 = time.time() - t2
    assert r2.status_code == 200
    print(f"[LATENCY] {path} first={d1*1000:.0f}ms second={d2*1000:.0f}ms")
    assert d1 < 3.0, f"first call too slow: {d1:.2f}s"
    assert d2 < 1.5, f"second (cache-hot) call too slow: {d2:.2f}s"
    # 2nd should be <= first + 50ms tolerance (allow small variance on network)
    assert d2 <= d1 + 0.2, f"second call slower than first: first={d1:.3f} second={d2:.3f}"


def test_reports_periods(client):
    r = client.get(f"{BASE_URL}/api/reports/periods", timeout=15)
    assert r.status_code == 200


def test_reports_months(client):
    r = client.get(f"{BASE_URL}/api/reports/months", timeout=15)
    assert r.status_code == 200


def test_gzip_encoding(client):
    r = client.get(
        f"{BASE_URL}/api/reports/period?period_type=month&period_value={PERIOD}",
        headers={"Accept-Encoding": "gzip"},
        timeout=15,
    )
    assert r.status_code == 200
    # requests auto-decompresses but preserves the header
    enc = r.headers.get("Content-Encoding", "")
    print(f"[GZIP] Content-Encoding={enc!r} bytes={len(r.content)}")
    assert "gzip" in enc.lower(), f"expected gzip, got {enc!r}"


def test_cache_different_period(client):
    # Two different periods should give (potentially) different responses & both 200
    r1 = client.get(f"{BASE_URL}/api/dashboard/overview?period_type=month&period_value=2026-04", timeout=15)
    r2 = client.get(f"{BASE_URL}/api/dashboard/overview?period_type=month&period_value=2026-03", timeout=15)
    assert r1.status_code == 200 and r2.status_code == 200
