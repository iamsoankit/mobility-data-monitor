from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DATA_DIR = ROOT / "data"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'recallops.db'}")
RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", str(DATA_DIR / "raw")))
QUARANTINE_DIR = Path(os.getenv("QUARANTINE_DIR", str(DATA_DIR / "quarantine")))
API_TIMEOUT_SECONDS = float(os.getenv("API_TIMEOUT_SECONDS", "25"))
API_MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", "3"))
SOURCE_ROOT = "https://api.nhtsa.gov"
