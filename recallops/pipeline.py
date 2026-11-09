from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import VEHICLES
from .config import QUARANTINE_DIR, RAW_DATA_DIR
from .database import SessionLocal, initialize_database
from .models import PipelineRequest, PipelineRun, RecallRecord
from .source import NHTSAError, fetch_recalls

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("recallops.pipeline")

KNOWN_FIELDS = {
    "nhtsacampaignnumber", "nhtsaactionnumber", "reportreceiveddate", "component", "summary",
    "consequence", "remedy", "notes", "modelyear", "make", "model", "parkit", "parkoutside",
    "manufacturer", "manufacturerid", "odidatabaseid", "pota", "recalldate", "updateddate",
}


def _get(record: dict, *names: str):
    lowered = {str(k).lower().replace("_", ""): v for k, v in record.items()}
    for name in names:
        if name.lower().replace("_", "") in lowered:
            return lowered[name.lower().replace("_", "")]
    return None


def _as_date(value) -> date | None:
    if not value:
        return None
    raw = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y%m%d", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw[:19], fmt).date()
        except ValueError:
            continue
    return None


def _normalize(record: dict, requested_make: str, requested_model: str, requested_year: int) -> tuple[dict | None, str | None]:
    campaign = _get(record, "NHTSACampaignNumber", "CampaignNumber", "NHTSAActionNumber")
    make = _get(record, "Make") or requested_make
    model = _get(record, "Model") or requested_model
    raw_year = _get(record, "ModelYear") or requested_year
    try:
        year = int(raw_year)
    except (ValueError, TypeError):
        return None, f"ModelYear is not an integer: {raw_year!r}"
    if not campaign:
        return None, "Missing campaign number"
    if not make or not model:
        return None, "Missing make or model"
    if year < 1980 or year > date.today().year + 1:
        return None, f"ModelYear outside accepted range: {year}"
    if year != requested_year:
        return None, f"Returned ModelYear {year} did not match requested year {requested_year}"
    return {
        "campaign_number": str(campaign).strip(),
        "make": str(make).strip().title(),
        "model": str(model).strip().title(),
        "model_year": year,
        "component": _get(record, "Component"),
        "report_received_date": _as_date(_get(record, "ReportReceivedDate")),
        "summary": _get(record, "Summary"),
        "consequence": _get(record, "Consequence"),
        "remedy": _get(record, "Remedy"),
        "source_url": "https://api.nhtsa.gov/recalls/recallsByVehicle?" + urlencode({"make": requested_make, "model": requested_model, "modelYear": requested_year}),
    }, None


def _safe_file_part(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_").lower()


def run_pipeline(start_year: int, end_year: int) -> str:
    if start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year")
    if end_year > date.today().year + 1 or start_year < 1980:
        raise ValueError("Choose model years from 1980 through next year")

    pipeline_started = time.monotonic()
    initialize_database()
    run_id = str(uuid4())
    scope = f"{start_year}:{end_year}|" + ",".join(f"{m}/{d}" for m, d in VEHICLES)
    raw_dir = RAW_DATA_DIR / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    quarantine_dir = QUARANTINE_DIR / run_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    counts = Counter()
    failures: list[str] = []
    quarantined: list[dict] = []
    unknown_fields: Counter = Counter()
    seen: set[tuple[str, str, str, int]] = set()
    raw_snapshots: list[dict] = []
    request_durations_ms = 0
    upsert_duration_ms = 0

    with SessionLocal() as db:
        run = PipelineRun(run_id=run_id, status="running", start_year=start_year, end_year=end_year, scope=scope)
        db.add(run)
        db.commit()
        previous = db.scalar(select(PipelineRun).where(PipelineRun.status.in_(["ok", "warning"])).order_by(PipelineRun.started_at.desc()).limit(1))
        comparable_previous = previous.records_fetched if previous and previous.scope == scope else None

        total_queries = len(VEHICLES) * (end_year - start_year + 1)
        for make, model in VEHICLES:
            for year in range(start_year, end_year + 1):
                counts["queries"] += 1
                query_started = time.monotonic()
                attempts = 0
                duration_ms = 0
                rows_returned = 0
                source_url = "https://api.nhtsa.gov/recalls/recallsByVehicle?" + urlencode({"make": make, "model": model, "modelYear": year})
                try:
                    fetch_result = fetch_recalls(make, model, year)
                    payload = fetch_result.payload
                    attempts = fetch_result.attempts
                    duration_ms = fetch_result.duration_ms
                    request_durations_ms += duration_ms
                    results = payload.get("results", payload.get("Results", [])) or []
                    if not isinstance(results, list):
                        raise NHTSAError("NHTSA results field was not a list")
                    counts["successes"] += 1
                    counts["fetched"] += len(results)
                    rows_returned = len(results)
                    raw_snapshots.append({"make": make, "model": model, "model_year": year, "payload": payload})
                    for item in results:
                        if not isinstance(item, dict):
                            quarantined.append({"requested": [make, model, year], "record": item, "reason": "Result was not a JSON object"})
                            continue
                        for key in item:
                            canonical = str(key).lower().replace("_", "").replace(" ", "")
                            if canonical not in KNOWN_FIELDS:
                                unknown_fields[str(key)] += 1
                        normalized, reason = _normalize(item, make, model, year)
                        if reason:
                            quarantined.append({"requested": [make, model, year], "record": item, "reason": reason})
                            continue
                        key = (normalized["campaign_number"], normalized["make"].casefold(), normalized["model"].casefold(), normalized["model_year"])
                        if key in seen:
                            counts["duplicates"] += 1
                            continue
                        seen.add(key)
                        counts["valid"] += 1
                        upsert_started = time.monotonic()
                        existing = db.scalar(select(RecallRecord).where(
                            RecallRecord.campaign_number == normalized["campaign_number"],
                            RecallRecord.make == normalized["make"],
                            RecallRecord.model == normalized["model"],
                            RecallRecord.model_year == normalized["model_year"],
                        ))
                        now = datetime.now(timezone.utc)
                        if existing is None:
                            db.add(RecallRecord(**normalized, first_seen_at=now, last_seen_at=now, last_changed_at=now))
                            counts["inserted"] += 1
                        else:
                            changed = any(getattr(existing, field) != value for field, value in normalized.items() if field != "source_url")
                            for field, value in normalized.items():
                                setattr(existing, field, value)
                            existing.last_seen_at = now
                            if changed:
                                existing.last_changed_at = now
                                counts["updated"] += 1
                        # Commit in bounded batches; duplicate runs remain safe through the unique key.
                        if (counts["inserted"] + counts["updated"]) % 100 == 0:
                            db.commit()
                        upsert_duration_ms += int((time.monotonic() - upsert_started) * 1000)
                    db.add(PipelineRequest(run_id=run_id, make=make.title(), model=model.title(), model_year=year,
                                           status="success", attempts=attempts, duration_ms=duration_ms,
                                           rows_returned=rows_returned, source_url=source_url))
                    db.commit()
                    time.sleep(0.12)
                except Exception as exc:
                    failures.append(f"{make} {model} {year}: {str(exc)[:240]}")
                    logger.exception("Source query failed for %s %s %s", make, model, year)
                    attempts = getattr(exc, "attempts", attempts)
                    duration_ms = getattr(exc, "duration_ms", int((time.monotonic() - query_started) * 1000))
                    request_durations_ms += duration_ms
                    db.add(PipelineRequest(run_id=run_id, make=make.title(), model=model.title(), model_year=year,
                                           status="failed", attempts=attempts, duration_ms=duration_ms,
                                           rows_returned=rows_returned, source_url=source_url,
                                           error_summary=str(exc)[:500]))
                    db.commit()

        archive_started = time.monotonic()
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        raw_path = raw_dir / f"{run_id}-{stamp}.json"
        raw_path.write_text(json.dumps({"run_id": run_id, "retrieved_at": datetime.now(timezone.utc).isoformat(), "source": "NHTSA recalls API", "responses": raw_snapshots}, ensure_ascii=False, indent=2), encoding="utf-8")
        if quarantined:
            (quarantine_dir / "invalid_records.json").write_text(json.dumps(quarantined, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        archive_duration_ms = int((time.monotonic() - archive_started) * 1000)

        finalize_started = time.monotonic()
        source_complete = counts["successes"] == total_queries
        volume_change_pct = None
        if comparable_previous is not None and comparable_previous > 0:
            volume_change_pct = round((counts["fetched"] - comparable_previous) / comparable_previous * 100, 1)
        quality = {
            "source_queries_expected": total_queries,
            "source_queries_succeeded": counts["successes"],
            "source_queries_failed": len(failures),
            "duplicate_rows": counts["duplicates"],
            "invalid_rows_quarantined": len(quarantined),
            "new_source_fields": dict(unknown_fields),
            "volume_change_pct_vs_previous_same_scope": volume_change_pct,
            "raw_snapshot": str(raw_path.relative_to(RAW_DATA_DIR.parent)),
            "quarantine_file": str((quarantine_dir / "invalid_records.json").relative_to(QUARANTINE_DIR.parent)) if quarantined else None,
            "stage_durations_ms": {
                "source_requests": request_durations_ms,
                "database_upserts": upsert_duration_ms,
                "raw_archive": archive_duration_ms,
            },
            "checks": [
                {"name": "Source coverage", "status": "passed" if source_complete else "warning", "detail": f"{counts['successes']} of {total_queries} requests succeeded"},
                {"name": "Required fields and year range", "status": "passed" if not quarantined else "warning", "detail": f"{len(quarantined)} records quarantined"},
                {"name": "Duplicate records", "status": "passed" if not counts["duplicates"] else "warning", "detail": f"{counts['duplicates']} duplicate rows skipped"},
                {"name": "Schema changes", "status": "passed" if not unknown_fields else "warning", "detail": f"{len(unknown_fields)} unrecognized fields recorded"},
                {"name": "Volume change", "status": "passed" if volume_change_pct is None or abs(volume_change_pct) <= 50 else "warning", "detail": "First run or within 50% of previous same-scope run" if volume_change_pct is None or abs(volume_change_pct) <= 50 else f"Fetched volume changed {volume_change_pct}%"},
            ],
        }
        if counts["successes"] == 0:
            status = "failed"
        elif failures or quarantined or counts["duplicates"] or unknown_fields or (volume_change_pct is not None and abs(volume_change_pct) > 50):
            status = "warning"
        else:
            status = "ok"
        quality["stage_durations_ms"]["quality_summary"] = int((time.monotonic() - finalize_started) * 1000)
        quality["stage_durations_ms"]["total_pipeline"] = int((time.monotonic() - pipeline_started) * 1000)
        run.finished_at = datetime.now(timezone.utc)
        run.status = status
        run.source_queries = counts["successes"]
        run.source_failures = len(failures)
        run.records_fetched = counts["fetched"]
        run.records_loaded = counts["inserted"] + counts["updated"]
        run.records_inserted = counts["inserted"]
        run.records_updated = counts["updated"]
        run.records_quarantined = len(quarantined)
        run.duplicate_records = counts["duplicates"]
        run.new_fields = dict(unknown_fields)
        run.quality = quality
        run.error_summary = "\n".join(failures[:20]) if failures else None
        db.commit()
        logger.info("Run %s finished with %s: fetched=%s inserted=%s updated=%s quarantined=%s", run_id, status, counts["fetched"], counts["inserted"], counts["updated"], len(quarantined))
    return run_id

