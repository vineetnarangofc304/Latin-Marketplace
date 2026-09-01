"""Regression tests for CORS + async bcrypt + inline admin seed.

Run against the pod-internal backend at http://localhost:8001 so we test the
backend behaviour directly (Cloudflare on preview URLs strips CORS headers).
"""
import os
import time
import concurrent.futures
import requests
import pytest

LOCAL = "http://localhost:8001"
PUBLIC = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or LOCAL
ADMIN_EMAIL = "admin@kazo.com"
ADMIN_PASSWORD = "admin123"


# ---------- CORS preflight ----------
class TestCORS:
    def test_preflight_fundlezone_origin_echoed(self):
        r = requests.options(
            f"{LOCAL}/api/auth/login",
            headers={
                "Origin": "https://kazob2b.fundlezone.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
            timeout=5,
        )
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == "https://kazob2b.fundlezone.com"
        assert r.headers.get("access-control-allow-credentials") == "true"

    def test_preflight_random_origin_echoed(self):
        r = requests.options(
            f"{LOCAL}/api/auth/login",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
            },
            timeout=5,
        )
        assert r.status_code == 200
        # Spec: with credentials, must echo origin, NOT '*'
        assert r.headers.get("access-control-allow-origin") == "https://example.com"
        assert r.headers.get("access-control-allow-credentials") == "true"


# ---------- Login regression ----------
class TestLogin:
    def test_valid_login_fast(self):
        t0 = time.time()
        r = requests.post(
            f"{LOCAL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=5,
        )
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data and data["token"]
        assert data["user"]["email"] == ADMIN_EMAIL
        assert data["user"]["role"] == "admin"
        assert elapsed < 1.0, f"login too slow: {elapsed:.2f}s"

    def test_invalid_password_401_fast(self):
        t0 = time.time()
        r = requests.post(
            f"{LOCAL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": "wrong"},
            timeout=5,
        )
        elapsed = time.time() - t0
        assert r.status_code == 401
        assert elapsed < 1.0, f"invalid login too slow: {elapsed:.2f}s"


# ---------- Concurrent login (event-loop blocking check) ----------
class TestConcurrentLogin:
    def test_5_concurrent_logins_no_stall(self):
        def _one():
            t0 = time.time()
            r = requests.post(
                f"{LOCAL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=10,
            )
            return r.status_code, time.time() - t0

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            results = list(ex.map(lambda _: _one(), range(5)))

        for status, _ in results:
            assert status == 200
        max_elapsed = max(e for _, e in results)
        # With async bcrypt off-thread, 5 concurrent should each stay well under ~1.5s
        assert max_elapsed < 2.0, f"slowest concurrent login: {max_elapsed:.2f}s (event loop may be blocked)"


# ---------- Broader regression through public URL ----------
class TestAuthenticatedEndpoints:
    @pytest.fixture(scope="class")
    def token(self):
        r = requests.post(
            f"{PUBLIC}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        return r.json()["token"]

    @pytest.mark.parametrize("path", [
        "/api/dashboard/overview",
        "/api/calculations?limit=1",
        "/api/masters/export",
        "/api/insights/health-score",
        "/api/recovery/summary",
    ])
    def test_endpoint_200(self, token, path):
        r = requests.get(
            f"{PUBLIC}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"
