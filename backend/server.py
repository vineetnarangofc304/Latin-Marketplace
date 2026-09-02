"""Latin Quarter · Marketplace AutoPilot (Fundle) — FastAPI backend
Modules: auth, masters (commission rules, fixed fee, GT charges, return fee),
uploads (sales & settlement parsers), calculations, reconciliation, dashboards.
"""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import asyncio
import os
import io
import re
import uuid
import logging
import bcrypt
import jwt
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Literal

from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Request, Response, Query, status
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId
import openpyxl

# ---------- Config ----------
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"
ACCESS_TTL_MIN = 60 * 24  # 24h for enterprise usability
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@fundle.ai")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
MARKETING_EMAIL = os.environ.get("MARKETING_EMAIL", "marketing@fundle.ai")
MARKETING_PASSWORD = os.environ.get("MARKETING_PASSWORD", "admin123")

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kazo")

app = FastAPI(title="Latin Quarter · Marketplace AutoPilot")
api = APIRouter(prefix="/api")


# ---------- Utilities ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def hash_pwd(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def hash_pwd_async(pw: str) -> str:
    return await asyncio.to_thread(hash_pwd, pw)


def verify_pwd(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), h.encode("utf-8"))
    except Exception:
        return False


async def verify_pwd_async(pw: str, h: str) -> bool:
    return await asyncio.to_thread(verify_pwd, pw, h)


def create_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id, "email": email, "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TTL_MIN),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def current_user(request: Request) -> Dict[str, Any]:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"password_hash": 0, "_id": 0})
    if not user:
        raise HTTPException(401, "User not found")
    return user


def require_role(*roles: str):
    async def _dep(user=Depends(current_user)):
        if user["role"] not in roles and user["role"] != "admin":
            raise HTTPException(403, f"Requires role: {roles}")
        return user
    return _dep


# ---------- Models ----------
class LoginIn(BaseModel):
    email: str
    password: str


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Literal["admin", "finance", "ops", "viewer"] = "viewer"


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str


# ---------- Auth Routes ----------
@api.post("/auth/login")
async def login(payload: LoginIn, response: Response):
    email = payload.email.strip().lower()
    user = await db.users.find_one({"email": email})
    if not user or not await verify_pwd_async(payload.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user["id"], user["email"], user["role"])
    response.set_cookie(
        "access_token", token, httponly=True, secure=False,
        samesite="lax", max_age=ACCESS_TTL_MIN * 60, path="/",
    )
    return {
        "token": token,
        "user": {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]},
    }


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def me(user=Depends(current_user)):
    return {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]}


@api.post("/auth/register")
async def register(payload: RegisterIn, user=Depends(require_role("admin"))):
    email = payload.email.strip().lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Email already exists")
    doc = {
        "id": new_id(), "email": email, "name": payload.name,
        "role": payload.role, "password_hash": hash_pwd(payload.password),
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    return {"id": doc["id"], "email": email, "name": payload.name, "role": payload.role}


@api.get("/auth/users")
async def list_users(user=Depends(require_role("admin"))):
    docs = await db.users.find({}, {"password_hash": 0, "_id": 0}).to_list(500)
    return docs


# Include auth router now; other routers imported below
from routers import masters, uploads_r, calculations, reconciliation, dashboards, reports, recovery, insights  # noqa: E402

app.include_router(api)
app.include_router(masters.router, prefix="/api", dependencies=[Depends(current_user)])
app.include_router(uploads_r.router, prefix="/api", dependencies=[Depends(current_user)])
app.include_router(calculations.router, prefix="/api", dependencies=[Depends(current_user)])
app.include_router(reconciliation.router, prefix="/api", dependencies=[Depends(current_user)])
app.include_router(dashboards.router, prefix="/api", dependencies=[Depends(current_user)])
app.include_router(reports.router, prefix="/api", dependencies=[Depends(current_user)])
app.include_router(recovery.router, prefix="/api", dependencies=[Depends(current_user)])
app.include_router(insights.router, prefix="/api", dependencies=[Depends(current_user)])

# CORS — when allow_credentials=True, the spec forbids allow_origins=["*"].
# We honour the CORS_ORIGINS env var when it's an explicit list, but if it's "*"
# we fall back to allow_origin_regex=".*" which reflects the caller's origin
# (satisfying browsers even with credentials).
_origins_raw = os.environ.get("CORS_ORIGINS", "*").strip()
if _origins_raw == "*" or not _origins_raw:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in _origins_raw.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.on_event("startup")
async def _startup():
    """Seed the admin user inline (blocks readiness briefly, but very fast),
    then kick off the rest of bootstrap (indexes + masters) in the background
    so K8s readiness probes succeed within seconds.
    """
    # 1) Seed / rehash admin inline so login is available from the first request.
    try:
        existing = await db.users.find_one({"email": ADMIN_EMAIL})
        if not existing:
            await db.users.insert_one({
                "id": new_id(), "email": ADMIN_EMAIL, "name": "Administrator",
                "role": "admin", "password_hash": await hash_pwd_async(ADMIN_PASSWORD),
                "created_at": now_iso(),
            })
            logger.info(f"Seeded admin inline: {ADMIN_EMAIL}")
        elif not await verify_pwd_async(ADMIN_PASSWORD, existing["password_hash"]):
            await db.users.update_one(
                {"email": ADMIN_EMAIL},
                {"$set": {"password_hash": await hash_pwd_async(ADMIN_PASSWORD)}},
            )
            logger.info(f"Rehashed admin inline: {ADMIN_EMAIL}")
    except Exception as e:
        logger.exception(f"Inline admin seed failed (deferring to background): {e}")

    # 2) Kick off the rest of bootstrap in the background.
    asyncio.create_task(_bootstrap())


async def _bootstrap():
    try:
        # Run all index creations concurrently — much faster than serial awaits
        # against a remote (Atlas) cluster.
        index_specs: List[tuple[str, list, dict]] = [
            ("users", ["email"], {"unique": True}),
            ("users", ["id"], {"unique": True}),
            # Sales
            ("sales", [("upload_id", 1)], {}),
            ("sales", [("online_order_id", 1), ("sku", 1)], {}),
            ("sales", [("order_date", 1)], {}),
            ("sales", [("report_month", 1)], {}),
            ("sales", [("report_month", 1), ("sub_category", 1)], {}),
            ("sales", [("report_month", 1), ("zone", 1)], {}),
            ("sales", [("report_month", 1), ("order_status", 1)], {}),
            ("sales", [("report_month", 1), ("txn_type", 1)], {}),
            # Settlement
            ("settlement", [("upload_id", 1)], {}),
            ("settlement", [("online_order_id", 1), ("sku", 1)], {}),
            ("settlement", [("report_month", 1)], {}),
            ("settlement", [("report_month", 1), ("online_order_id", 1), ("sku", 1)], {}),
            # Calculations
            ("calculations", [("sales_id", 1)], {"unique": True}),
            ("calculations", [("report_month", 1)], {}),
            ("calculations", [("unmapped", 1)], {}),
            ("calculations", [("report_month", 1), ("unmapped", 1)], {}),
            ("calculations", [("report_month", 1), ("breakdown.sub_category", 1)], {}),
            ("calculations", [("report_month", 1), ("breakdown.master_category", 1)], {}),
            ("calculations", [("report_month", 1), ("breakdown.zone", 1)], {}),
            ("calculations", [("report_month", 1), ("expected_settlement", -1)], {}),
            ("calculations", [("online_order_id", 1), ("sku", 1)], {}),
            # Discrepancies
            ("discrepancies", [("severity", 1), ("recon_run_id", 1)], {}),
            ("discrepancies", [("report_month", 1)], {}),
            ("discrepancies", [("report_month", 1), ("severity", 1)], {}),
            ("discrepancies", [("report_month", 1), ("recoverable", -1)], {}),
            ("discrepancies", [("recon_run_id", 1), ("severity", 1)], {}),
            ("discrepancies", [("match_status", 1)], {}),
            ("discrepancies", [("online_order_id", 1), ("sku", 1)], {}),
            # Uploads
            ("uploads", [("uploaded_at", -1)], {}),
            ("uploads", [("type", 1), ("uploaded_at", -1)], {}),
            # Recovery
            ("recovery_cases", [("discrepancy_id", 1)], {}),
            ("recovery_cases", [("status", 1)], {}),
            ("recovery_cases", [("report_month", 1)], {}),
            ("recovery_cases", [("report_month", 1), ("status", 1)], {}),
            ("recovery_cases", [("report_month", 1), ("priority", 1)], {}),
            ("recovery_cases", [("recoverable_amount", -1)], {}),
            ("recovery_notes", [("case_id", 1), ("created_at", 1)], {}),
            ("recovery_evidence", [("case_id", 1)], {}),
            # Insights briefs
            ("insights_briefs", [("created_at", -1)], {}),
            ("insights_briefs", [("period_type", 1), ("period_value", 1), ("created_at", -1)], {}),
            # Commission masters
            ("commission_rules", [("brand", 1), ("sub_category", 1)], {}),
            ("commission_rules", [("is_active", 1)], {}),
        ]

        async def _mk_index(coll_name: str, keys, opts):
            try:
                await db[coll_name].create_index(keys, **opts)
            except Exception as e:
                logger.warning(f"index {coll_name}{keys}: {e}")

        await asyncio.gather(*(_mk_index(c, k, o) for c, k, o in index_specs))

        # Seed admin
        existing = await db.users.find_one({"email": ADMIN_EMAIL})
        if not existing:
            await db.users.insert_one({
                "id": new_id(), "email": ADMIN_EMAIL, "name": "Administrator",
                "role": "admin", "password_hash": await hash_pwd_async(ADMIN_PASSWORD),
                "created_at": now_iso(),
            })
            logger.info(f"Seeded admin: {ADMIN_EMAIL}")
        elif not await verify_pwd_async(ADMIN_PASSWORD, existing["password_hash"]):
            await db.users.update_one(
                {"email": ADMIN_EMAIL},
                {"$set": {"password_hash": await hash_pwd_async(ADMIN_PASSWORD)}},
            )
            logger.info(f"Rehashed admin password: {ADMIN_EMAIL}")

        # Latin Quarter clean-start seed: drop any legacy KAZO admin, seed the Fundle
        # marketing user, and seed only config singletons (tax / tolerance / settlement).
        # Contract-rate masters are loaded by the tenant via /masters.
        await db.users.delete_many({"email": "admin@kazo.com"})
        existing_mkt = await db.users.find_one({"email": MARKETING_EMAIL})
        if not existing_mkt:
            await db.users.insert_one({
                "id": new_id(), "email": MARKETING_EMAIL, "name": "Marketing (Fundle)",
                "role": "viewer", "password_hash": await hash_pwd_async(MARKETING_PASSWORD),
                "created_at": now_iso(),
            })
            logger.info(f"Seeded marketing user: {MARKETING_EMAIL}")
        await masters.seed_config_defaults(db)
        await masters.seed_latin_masters(db)
        logger.info("Bootstrap complete")
    except Exception as e:
        # Never block app readiness on bootstrap errors — log and keep serving.
        logger.exception(f"Bootstrap failed (app is still up): {e}")


@app.on_event("shutdown")
async def _shutdown():
    client.close()


@app.get("/api/health")
async def health():
    return {"status": "ok", "time": now_iso()}


@app.get("/health")
async def health_root():
    """Lightweight probe endpoint at root — some ingress paths hit / or /health."""
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"service": "latinquarter-marketplace-autopilot", "status": "ok"}
