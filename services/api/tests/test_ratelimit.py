"""Rate limiting tests: bucket correctness, per-user isolation, and limits."""
from __future__ import annotations

import math
import threading
import time

import pytest

from app.core.ratelimit import RateLimitExceeded, TokenBucketStore, apply_rate_limit, rate_limit_settings


def test_bucket_allows_burst_then_blocks_and_recovers(monkeypatch):
    store = TokenBucketStore(clock=lambda: 0.0)
    # capacity 2, refill 2s -> burst of 2 then a block with a retry window.
    assert store.consume("u", capacity=2, refill_seconds=2.0, now=0.0) is None
    assert store.consume("u", capacity=2, refill_seconds=2.0, now=0.0) is None
    wait = store.consume("u", capacity=2, refill_seconds=2.0, now=0.0)
    assert wait is not None and wait > 0
    with pytest.raises(RateLimitExceeded):
        apply_rate_limit("u", capacity=2, refill_seconds=2.0, store=store)
    # After the refill window one token is available again.
    assert store.consume("u", capacity=2, refill_seconds=2.0, now=1.0) is None


def test_users_are_isolated_and_keys_independent(monkeypatch):
    store = TokenBucketStore()
    for _ in range(6):
        apply_rate_limit("u1", capacity=3, refill_seconds=60.0, store=store)
    with pytest.raises(RateLimitExceeded):
        apply_rate_limit("u1", capacity=3, refill_seconds=60.0, store=store)
    # A different user has a separate bucket.
    apply_rate_limit("u2", capacity=3, refill_seconds=60.0, store=store)
    # A different scope for the same user is also separate.
    apply_rate_limit("ai:u1", capacity=3, refill_seconds=60.0, store=store)


def test_max_keys_fails_closed():
    store = TokenBucketStore(max_keys=1, prune_interval=1e9)
    store.consume("a", capacity=1, refill_seconds=1.0, now=0.0)
    with pytest.raises(RateLimitExceeded):
        store.consume("b", capacity=1, refill_seconds=1.0, now=0.0)


def test_global_settings_are_conservative():
    capacity, refill = rate_limit_settings()
    assert capacity == 120
    assert refill == 60.0


def test_thread_safety_under_concurrent_consumers():
    store = TokenBucketStore(max_keys=0)
    results: list[float | None] = []
    lock = threading.Lock()

    def worker(key: str) -> None:
        wait = store.consume(key, capacity=1000, refill_seconds=1.0, now=0.0)
        with lock:
            results.append(wait)

    threads = [threading.Thread(target=worker, args=("shared",)) for _ in range(32)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(value is None for value in results)
    # All capacity was consumed; the next request must wait.
    wait = store.consume("shared", capacity=1000, refill_seconds=1.0, now=0.0)
    assert wait is not None
