from __future__ import annotations

import logging
import time
from dataclasses import dataclass
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
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2 ** attempt, 8)
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

