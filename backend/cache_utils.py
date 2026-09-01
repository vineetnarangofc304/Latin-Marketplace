"""Tiny in-memory TTL cache for expensive aggregate endpoints.

Not a distributed cache — good enough for a single-process backend and
guards against a page that fires the same query multiple times in a few seconds.
Invalidate by tag (e.g. after an upload / recon run) via ``invalidate(tag)``.
"""
import asyncio
import time
from typing import Any, Callable, Optional


class _Entry:
    __slots__ = ("value", "expires_at", "tag")

    def __init__(self, value: Any, expires_at: float, tag: Optional[str]):
        self.value = value
        self.expires_at = expires_at
        self.tag = tag


_store: dict[str, _Entry] = {}
_lock = asyncio.Lock()


async def get_or_set(key: str, ttl_seconds: float, loader: Callable, tag: Optional[str] = None):
    now = time.time()
    async with _lock:
        e = _store.get(key)
        if e and e.expires_at > now:
            return e.value
    value = await loader()
    async with _lock:
        _store[key] = _Entry(value, now + ttl_seconds, tag)
    return value


def invalidate(tag: Optional[str] = None) -> int:
    """Remove entries by tag (or all if tag is None). Returns count removed."""
    if tag is None:
        n = len(_store)
        _store.clear()
        return n
    dead = [k for k, e in _store.items() if e.tag == tag]
    for k in dead:
        _store.pop(k, None)
    return len(dead)
