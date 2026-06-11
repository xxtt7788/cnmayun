"""Reusable service-layer primitives: in-process cache with versioned invalidation.

Why a module of decorators instead of a class hierarchy?
- Services are free functions; a decorator is the smallest non-breaking change.
- Future move to Redis: replace ``_store`` with a client. Decorator interface
  (``cached_call``/``bump_version``/``clear_cache``) does not change.

Cache key shape: ``f"{group}:v{version}:{arg_key}"``
- ``group``     — namespace ("overview", "stats", "coverage", ...)
- ``version``   — bumped by ``bump_version(group)`` so background recomputes
                  instantly invalidate stale entries (stale-while-recompute).
- ``arg_key``   — repr(args+kwargs) by default; supply ``key_fn`` to override.

TTL semantics
- TTL in: return cached value
- TTL out: recompute, store with new TTL
- Version bumped mid-TTL: cached value is dropped on next read, recompute.

Anti-stampede: TTL is jittered by ±20% so a fleet of workers does not all
recompute at the same instant.
"""
from __future__ import annotations

import functools
import random
import threading
import time
from typing import Any, Callable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

_store: dict[str, tuple[float, Any]] = {}      # key -> (expire_at, value)
_versions: dict[str, int] = {}                 # group -> current version
_stats: dict[str, int] = {"hit": 0, "miss": 0, "evict": 0}
_lock = threading.RLock()

# Hard cap on cache entries to bound memory. When exceeded, oldest 10% are dropped.
_MAX_ENTRIES = 4096


def bump_version(group: str) -> None:
    """Invalidate every cached value under ``group``.

    Call from any background mutation (e.g. end of ``recompute_company_metrics``).
    Cheap; the next read will recompute.
    """
    with _lock:
        _versions[group] = _versions.get(group, 0) + 1


def clear_cache(group: str | None = None) -> int:
    """Drop cached entries. ``group=None`` clears everything. Returns count cleared."""
    with _lock:
        if group is None:
            count = len(_store)
            _store.clear()
            _versions.clear()
            return count
        # Bump version rather than scanning keys — version bump is O(1)
        before = _versions.get(group, 0)
        _versions[group] = before + 1
        return -1  # sentinel: by-version invalidation, exact count unknown without scan


def cache_stats() -> dict[str, int]:
    """Return hit/miss/evict counts and current size. For diagnostics/metrics."""
    with _lock:
        return {
            **_stats,
            "size": len(_store),
            "groups": len(_versions),
        }


def cached_call(
    group: str,
    ttl_seconds: float = 60.0,
    key_fn: Callable[..., str] | None = None,
    versioned: bool = True,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Cache the result of a sync function.

    Args:
        group:       namespace used for cache key and version invalidation.
        ttl_seconds: base TTL. Actual TTL is jittered by ±20% to avoid stampede.
        key_fn:      optional ``(*args, **kwargs) -> str`` that derives a stable
                     key from the call args. Default: empty string (single-slot
                     per group). The previous behaviour of repr()-ing all args
                     was a foot-gun for functions whose first arg is a SQLAlchemy
                     ``Session`` (every request gets a fresh Session, so the key
                     never matched).
        versioned:   if True, ``bump_version(group)`` invalidates this entry.

    Returns:
        decorator that wraps the original function.

    For functions that should cache per-query-param (e.g. ``list_events(role=X,
    event_type=Y)``), pass a key_fn that hashes only the meaningful args:

        @cached_call(group="events", key_fn=lambda db, **kw: repr(kw))
    """
    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            arg_key = key_fn(*args, **kwargs) if key_fn else ""
            with _lock:
                ver = _versions.get(group, 0) if versioned else 0
                cache_key = f"{group}:v{ver}:{arg_key}"
                hit = _store.get(cache_key)
                if hit is not None and hit[0] > time.monotonic():
                    _stats["hit"] += 1
                    return hit[1]  # type: ignore[return-value]
                _stats["miss"] += 1
            value = fn(*args, **kwargs)
            with _lock:
                # Bound the dict size: if over cap, drop oldest 10% by insertion order.
                if len(_store) >= _MAX_ENTRIES:
                    evict_count = max(1, _MAX_ENTRIES // 10)
                    for old_key in list(_store.keys())[:evict_count]:
                        _store.pop(old_key, None)
                    _stats["evict"] += evict_count
                # Jitter TTL ±20% so concurrent workers don't all expire together.
                jitter = 1.0 + (random.random() * 0.4 - 0.2)
                _store[cache_key] = (time.monotonic() + ttl_seconds * jitter, value)
            return value
        return wrapper
    return decorator
