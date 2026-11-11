from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

import requests

from .config import API_MAX_RETRIES, API_TIMEOUT_SECONDS, SOURCE_ROOT

logger = logging.getLogger(__name__)


class NHTSAError(RuntimeError):
    def __init__(self, message: str, attempts: int = 0, duration_ms: int = 0):
        super().__init__(message)
        self.attempts = attempts
        self.duration_ms = duration_ms


@dataclass
class FetchResult:
    payload: dict[str, Any]
    attempts: int
    duration_ms: int


def _retry_delay(retry_after: str | None, attempt: int, now: datetime | None = None) -> float:
    """Return the server's Retry-After delay, or a bounded exponential fallback."""
    fallback = min(2 ** attempt, 8)
    if not retry_after:
        return fallback

    try:
        return max(0.0, float(retry_after))
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(retry_after)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - current_time).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return fallback


def fetch_recalls(make: str, model: str, model_year: int, session: requests.Session | None = None) -> FetchResult:
    client = session or requests.Session()
    query = urlencode({"make": make, "model": model, "modelYear": model_year})
    url = f"{SOURCE_ROOT}/recalls/recallsByVehicle?{query}"
    last_error = "unknown error"
    started = time.monotonic()
    attempts = 0
    for attempt in range(API_MAX_RETRIES):
        attempts = attempt + 1
        try:
            response = client.get(url, timeout=API_TIMEOUT_SECONDS, headers={"Accept": "application/json", "User-Agent": "RecallOps/0.1 portfolio project"})
            if response.status_code == 429 or response.status_code >= 500:
                delay = _retry_delay(response.headers.get("Retry-After"), attempt)
                last_error = f"HTTP {response.status_code}"
                if attempt + 1 < API_MAX_RETRIES:
                    logger.warning("NHTSA returned %s; retrying in %ss (%s %s %s)", response.status_code, delay, make, model, model_year)
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("results", payload.get("Results")), list):
                raise NHTSAError("Unexpected response shape: expected an object with a results list.")
            return FetchResult(payload=payload, attempts=attempts, duration_ms=int((time.monotonic() - started) * 1000))
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError, ValueError, NHTSAError) as exc:
            last_error = str(exc)
            if attempt + 1 < API_MAX_RETRIES:
                time.sleep(min(2 ** attempt, 8))
                continue
            break
    raise NHTSAError(f"Request failed after {attempts} attempts: {last_error}", attempts, int((time.monotonic() - started) * 1000))
