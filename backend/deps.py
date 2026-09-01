"""Shared authorization deps."""
from fastapi import Depends, HTTPException, Request
import jwt
import os
from db import db

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"


async def current_user(request: Request):
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


require_admin = require_role("admin")
