# RecallOps

**Automotive recall data, with the operational details made visible.** RecallOps pulls vehicle recall records from NHTSA, saves the source responses, loads normalized records into PostgreSQL, and reports the checks and exceptions from each pipeline run.

This portfolio project is designed to show data ingestion, SQL transformation, repeat-safe processing, quality controls, failure visibility, and operational documentation. It uses public NHTSA recall data. See the [NHTSA dataset and API documentation](https://www.nhtsa.gov/nhtsa-datasets-and-apis).

## What it does

- Fetches recall results for a small make/model catalog across a chosen model-year range.
- Retries transient API failures and records each successful/failed source request.
- Keeps timestamped raw JSON snapshots so transformed records can be traced back to source responses.
- Normalizes campaign, vehicle, component, report date, summary, consequence, and remedy fields into PostgreSQL (SQLite is available for a quick local run).
- Makes reruns safe with a stable campaign + make + model + model-year key; existing rows are updated and new rows inserted.
- Quarantines malformed records instead of silently dropping them.
- Reports source coverage, duplicate rows, schema changes, quarantined rows, and large volume changes.
- Offers a small operations dashboard with run history and per-check status.
- Can run on demand or daily through GitHub Actions after a `DATABASE_URL` secret is configured.

## Architecture

```text
NHTSA recalls API
       │
       ▼
Python ingestion ──► timestamped raw JSON
       │
       ├── validation / deduplication / quarantine
       ▼
PostgreSQL ──► FastAPI status API ──► React operations dashboard
       │
       └── run metadata, quality checks, record history
```

## Run locally

Requirements: Python 3.11+, Node.js 20+, and Docker Desktop (for PostgreSQL).

1. Start PostgreSQL:

   ```bash
   docker compose up -d postgres
   ```

2. Install and run the API:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   export DATABASE_URL='postgresql+psycopg://recallops:recallops-local@localhost:5432/recallops'
   uvicorn recallops.api:app --reload --port 8000
   ```

   For a quick local-only run without Docker, leave `DATABASE_URL` unset; the pipeline uses `data/recallops.db` (SQLite).

3. In a second terminal, start the dashboard:

   ```bash
   cd web
   npm install
   npm run dev
   ```

   Open the local Vite URL printed in the terminal. Its development proxy sends `/api` requests to `localhost:8000`.

4. Click **Run pipeline**, or run from the project root:

   ```bash
   python -m recallops.cli --start-year 2022 --end-year 2026
   ```

The first run queries five make/model pairs over four years (20 API requests). Adjust the year range in the command to manage run time and source coverage.

## API routes

- `GET /health` — service health.
- `GET /api/dashboard` — latest run, recent history, quality checks, and coverage counts.
- `GET /api/recalls?make=Toyota&limit=100` — normalized recall records.
- `POST /api/run` — start a background ingestion run. Optional query parameters: `start_year`, `end_year`.

## Quality controls

| Check | What it catches | Handling |
|---|---|---|
| Source coverage | Failed API calls or incomplete run | Retry transient errors; mark partial runs for review |
| Required fields and year range | Missing campaign, make/model, or invalid model year | Quarantine the raw record with a reason |
| Duplicate records | Same campaign and vehicle returned more than once | Skip duplicate within a run; stable database key makes reruns idempotent |
| Schema changes | New source fields not yet mapped | Preserve them in raw JSON and surface the new field names |
| Volume change | A greater than 50% change from the previous identical scope | Flag for analyst review; do not discard data |

An empty result for one vehicle/year is valid. It is different from a failed source request.

## Operational runbook

1. **Check run status.** In the dashboard, inspect source coverage, quarantined rows, duplicate count, and volume-change warning.
2. **Find the source query.** Each raw snapshot records its make, model, model year, and original JSON response. Failed request details are attached to the run.
3. **Inspect quarantine.** Read the reason beside each invalid record. Keep the original value intact while deciding whether normalization needs a fix.
4. **Recover.** Fix the mapping or input issue, then rerun the same year range. The stable unique key prevents duplicate rows.
5. **Confirm recovery.** Check that the latest run is healthy, source coverage is complete, and the affected record is loaded.

### Common cases

- **NHTSA timeout / HTTP 429 or 5xx:** automatic bounded retry with backoff; if still failing, the run is marked for review.
- **Unknown response field:** preserved in the raw snapshot and shown as schema drift. Add a mapping only after reviewing the new field.
- **Sudden volume change:** data is retained and the run is marked for review; compare the raw payload with the prior same-scope run.
- **Dashboard says API disconnected:** start the FastAPI service and confirm `http://localhost:8000/health` returns `{"status":"ok"}`.

## Scheduled runs

The included workflow supports daily scheduled and manual runs. Add a `DATABASE_URL` GitHub Actions secret pointing to a persistent PostgreSQL database. Until that secret exists, scheduled runs exit cleanly with a notice instead of failing. The workflow only reports an action failure when every source request fails; partial runs remain visible as warnings in the dashboard and run history.

## Privacy and scope

This starter project requests NHTSA recall data by make, model, and model year. It does not ingest VINs, consumer complaint narratives, names, or contact details. Extend the catalog gradually and review the source terms and rate limits before increasing request volume.
