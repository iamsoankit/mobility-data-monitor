from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

import requests

from .config import API_MAX_RETRIES, API_TIMEOUT_SECONDS, SOURCE_ROOT

logger = logging.getLogger(__name__)


class NHTSAError(RuntimeError):
    pass


def fetch_recalls(make: str, model: str, model_year: int, session: requests.Session | None = None) -> dict[str, Any]:
    client = session or requests.Session()
    query = urlencode({"make": make, "model": model, "modelYear": model_year})
    url = f"{SOURCE_ROOT}/recalls/recallsByVehicle?{query}"
    last_error = "unknown error"
    for attempt in range(API_MAX_RETRIES):
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
            return payload
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError, ValueError, NHTSAError) as exc:
            last_error = str(exc)
            if attempt + 1 < API_MAX_RETRIES:
                time.sleep(min(2 ** attempt, 8))
                continue
            break
    raise NHTSAError(f"Request failed after {API_MAX_RETRIES} attempts: {last_error}")

