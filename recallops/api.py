from __future__ import annotations

import threading
from datetime import date

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, select

from .database import SessionLocal, initialize_database
from .models import PipelineRequest, PipelineRun, RecallRecord
from .pipeline import run_pipeline

app = FastAPI(title="RecallOps API", version="0.1.0", description="Pipeline run status, recall records, and quality checks")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])
run_lock = threading.Lock()
run_active = False


@app.on_event("startup")
def startup() -> None:
    initialize_database()


def _run_payload(run: PipelineRun) -> dict:
    return {
        "run_id": run.run_id,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "start_year": run.start_year,
        "end_year": run.end_year,
        "source_queries": run.source_queries,
        "source_failures": run.source_failures,
        "records_fetched": run.records_fetched,
        "records_loaded": run.records_loaded,
        "records_inserted": run.records_inserted,
        "records_updated": run.records_updated,
        "records_quarantined": run.records_quarantined,
        "duplicate_records": run.duplicate_records,
        "new_fields": run.new_fields or {},
        "quality": run.quality or {},
        "error_summary": run.error_summary,
    }


def _background_run(start_year: int, end_year: int) -> None:
    global run_active
    try:
        run_pipeline(start_year, end_year)
    finally:
        with run_lock:
            run_active = False


@app.get("/health")
def health() -> dict:
    initialize_database()
    return {"status": "ok", "service": "recallops-api"}


@app.get("/api/dashboard")
def dashboard() -> dict:
    initialize_database()
    with SessionLocal() as db:
        latest = db.scalar(select(PipelineRun).order_by(desc(PipelineRun.started_at)).limit(1))
        recent = db.scalars(select(PipelineRun).order_by(desc(PipelineRun.started_at)).limit(8)).all()
        total = db.scalar(select(func.count(RecallRecord.id))) or 0
        make_counts = db.execute(select(RecallRecord.make, func.count(RecallRecord.id)).group_by(RecallRecord.make).order_by(desc(func.count(RecallRecord.id))).limit(8)).all()
        model_counts = db.execute(select(RecallRecord.make, RecallRecord.model, RecallRecord.model_year, func.count(RecallRecord.id)).group_by(RecallRecord.make, RecallRecord.model, RecallRecord.model_year).order_by(desc(func.count(RecallRecord.id))).limit(10)).all()
        return {
            "status": latest.status if latest else "not_started",
            "latest_run": _run_payload(latest) if latest else None,
            "recent_runs": [_run_payload(run) for run in recent],
            "total_recall_vehicle_rows": total,
            "by_make": [{"make": row[0], "count": row[1]} for row in make_counts],
            "by_vehicle": [{"make": row[0], "model": row[1], "year": row[2], "count": row[3]} for row in model_counts],
            "run_active": run_active,
        }


@app.get("/api/recalls")
def recalls(make: str | None = None, limit: int = 100) -> list[dict]:
    initialize_database()
    with SessionLocal() as db:
        query = select(RecallRecord).order_by(desc(RecallRecord.report_received_date)).limit(min(max(limit, 1), 500))
        if make:
            query = query.where(RecallRecord.make.ilike(make))
        records = db.scalars(query).all()
        return [{"campaign_number": r.campaign_number, "make": r.make, "model": r.model, "model_year": r.model_year, "component": r.component, "report_received_date": r.report_received_date.isoformat() if r.report_received_date else None, "summary": r.summary, "consequence": r.consequence, "remedy": r.remedy, "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None} for r in records]


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str) -> dict:
    initialize_database()
    with SessionLocal() as db:
        run = db.get(PipelineRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found.")
        requests = db.scalars(select(PipelineRequest).where(PipelineRequest.run_id == run_id).order_by(PipelineRequest.request_id)).all()
        return {
            **_run_payload(run),
            "requests": [{
                "request_id": request.request_id,
                "make": request.make,
                "model": request.model,
                "model_year": request.model_year,
                "status": request.status,
                "attempts": request.attempts,
                "duration_ms": request.duration_ms,
                "rows_returned": request.rows_returned,
                "source_url": request.source_url,
                "error_summary": request.error_summary,
                "completed_at": request.completed_at.isoformat() if request.completed_at else None,
            } for request in requests],
        }


@app.get("/api/catalog")
def catalog() -> list[dict]:
    return [
        {"table": "pipeline_runs", "grain": "One row per pipeline execution", "key": "run_id", "purpose": "Run status, year scope, counts, and quality summary"},
        {"table": "pipeline_requests", "grain": "One row per make/model/year request in a run", "key": "run_id + make + model + model_year", "purpose": "Request outcome, retries, response rows, duration, and error"},
        {"table": "vehicle_recalls", "grain": "One recall campaign for one make/model/model year", "key": "campaign_number + make + model + model_year", "purpose": "Normalized recall details; safe to upsert on repeat runs"},
        {"table": "raw JSON snapshots", "grain": "One run snapshot containing successful source responses", "key": "run_id + retrieval timestamp", "purpose": "Source traceability and reprocessing"},
    ]


@app.post("/api/run", status_code=202)
def start_run(background_tasks: BackgroundTasks, start_year: int | None = None, end_year: int | None = None) -> dict:
    global run_active
    start_year = start_year or date.today().year - 3
    end_year = end_year or date.today().year
    if start_year < 1980 or end_year > date.today().year + 1 or start_year > end_year:
        raise HTTPException(status_code=422, detail="Choose a valid model-year range from 1980 through next year.")
    with run_lock:
        if run_active:
            raise HTTPException(status_code=409, detail="A pipeline run is already active.")
        run_active = True
    background_tasks.add_task(_background_run, start_year, end_year)
    return {"message": "Pipeline run started.", "start_year": start_year, "end_year": end_year}
