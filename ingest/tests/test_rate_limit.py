from __future__ import annotations

from fara_ingest.rate_limit import TokenBucket


def test_allows_burst_up_to_capacity_without_sleeping():
    sleeps: list[float] = []
    clock = [0.0]
    bucket = TokenBucket(max_tokens=5, refill_seconds=10.0, sleep=sleeps.append, now=lambda: clock[0])

    for _ in range(5):
        bucket.acquire()

    assert sleeps == []


def test_sixth_request_within_window_waits_for_oldest_to_expire():
    sleeps: list[float] = []
    clock = [0.0]

    def fake_sleep(seconds: float) -> None:
        # A real sleep() lets time pass; simulate that so the retry loop can
        # observe the window has since cleared, instead of spinning forever.
        sleeps.append(seconds)
        clock[0] += seconds

    bucket = TokenBucket(max_tokens=5, refill_seconds=10.0, sleep=fake_sleep, now=lambda: clock[0])

    for _ in range(5):
        bucket.acquire()

    # 6th request at t=0 must wait until the 1st request (t=0) exits the 10s window.
    bucket.acquire()
    assert sleeps == [10.0]


def test_requests_outside_window_dont_count_against_capacity():
    clock = [0.0]
    bucket = TokenBucket(max_tokens=5, refill_seconds=10.0, sleep=lambda s: None, now=lambda: clock[0])

    for _ in range(5):
        bucket.acquire()

    clock[0] = 11.0  # past the 10s window — all 5 prior requests have expired
    sleeps: list[float] = []
    bucket._sleep = sleeps.append
    bucket.acquire()
    assert sleeps == []
