from __future__ import annotations

import time

import httpx

from fara_ingest.rate_limit import TokenBucket

USER_AGENT = "fara-ingest/0.1 (https://github.com/lehogg325/FARA)"

# Confirmed live 2026-08-21 (docs/api-notes.md): 5 requests / 10 seconds, rolling window.
DEFAULT_MAX_TOKENS = 5
DEFAULT_REFILL_SECONDS = 10.0


class FaraApiError(RuntimeError):
    pass


def default_bucket() -> TokenBucket:
    return TokenBucket(max_tokens=DEFAULT_MAX_TOKENS, refill_seconds=DEFAULT_REFILL_SECONDS)


class RateLimitedClient:
    """HTTP client for FARA's JSON endpoints — rate-limited client-side and
    retried with backoff on 429/5xx. Bulk downloads (bulk.py) intentionally do
    NOT go through this: they hit a plain static file host, not the rate-limited
    ORDS API (docs/api-notes.md).
    """

    def __init__(
        self,
        *,
        bucket: TokenBucket | None = None,
        client: httpx.Client | None = None,
        max_retries: int = 3,
        sleep=time.sleep,
    ):
        self.bucket = bucket or default_bucket()
        self._client = client or httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        self.max_retries = max_retries
        self._sleep = sleep

    def get_json(self, url: str) -> dict:
        attempt = 0
        while True:
            self.bucket.acquire()
            response = self._client.get(url)
            if response.status_code == 200:
                return response.json()

            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt < self.max_retries:
                attempt += 1
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2**attempt, 30)
                self._sleep(delay)
                continue

            raise FaraApiError(f"GET {url} failed: HTTP {response.status_code}: {response.text[:200]!r}")

    def close(self) -> None:
        self._client.close()
