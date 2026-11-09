# Mobility Monitor

**A small, observable data pipeline for public vehicle recall data.** Mobility Monitor requests recall records from the NHTSA API, preserves the source responses, validates and normalizes records, and loads them into PostgreSQL or SQLite. Its operations dashboard explains what happened during each run.

The project is intended as a data engineering portfolio project. It focuses on the full path from source request to a traceable database row, including retries, data quality checks, repeat-safe loads, and run history.

## What you can explore

- **Pipeline flow:** follow data from the NHTSA API through raw storage, validation, and the database.
- **Run ledger:** review previous executions, year ranges, row counts, and status.
- **Run details:** inspect each make/model/year request, including success or failure, retry count, response rows, and request duration.
- **Data catalog:** see what one row represents in each table and which key identifies it.
- **Quality controls:** review source coverage, invalid records, duplicate rows, unexpected source fields, and unusual volume changes.

## How the pipeline works

```text
NHTSA Recalls API
       │  request by make, model, and model year
       ▼
Retry and request logging
       │
       ├──────────────► Raw JSON snapshots in data/raw/
       │
       ▼
Validate and normalize ── invalid rows ──► data/quarantine/
       │
       ▼
Repeat-safe database load
       │
       ├── pipeline_runs      one row per pipeline run
       ├── pipeline_requests  one row per source request
       └── vehicle_recalls    one row per recall campaign and vehicle
       │
       ▼
FastAPI ──► React dashboard
```

The recall table uses campaign number, make, model, and model year as its unique key. Rerunning the same scope updates matching records and inserts new ones instead of creating duplicates. Raw snapshots retain the original successful API responses for traceability; malformed records are saved with a reason in quarantine.

## Technology

| Part | Technology | Purpose |
|---|---|---|
| Ingestion and validation | Python, Requests | Fetch source data, retry transient errors, validate and normalize records |
| Storage | PostgreSQL or SQLite, SQLAlchemy | Store run metadata, request logs, and normalized recall records |
| API | FastAPI | Serve dashboard, catalog, and run detail data |
| Dashboard | React, Vite | Show pipeline status and operational history |
| Scheduling | GitHub Actions | Run ingestion on a schedule or manually when a persistent database is configured |

## Run locally

Requirements: Python 3.11+, Node.js 20+, and Docker Desktop if you want PostgreSQL.

### 1. Start PostgreSQL

From the project root:

```bash
docker compose up -d postgres
```

### 2. Install and start the API

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg://recallops:recallops-local@localhost:5432/recallops'
uvicorn recallops.api:app --reload --port 8000
```

For a quick run without Docker, leave `DATABASE_URL` unset. The project then uses a local SQLite database at `data/recallops.db`.

### 3. Start the dashboard

In a second terminal:

```bash
cd web
npm install
npm run dev
```

Open the local URL printed by Vite. In development, Vite forwards `/api` requests to the API at `localhost:8000`.

### 4. Run an ingestion

Use the dashboard's **Run pipeline** button or run the CLI from the project root:

```bash
python -m recallops.cli --start-year 2022 --end-year 2026
```

The default catalog contains five make/model pairs. A four-year range therefore makes 20 source requests. A run can take a few minutes because requests are rate-limited and retried when needed.

## Preview data and live data

When the dashboard cannot reach the API, it displays clearly labeled sample values so the interface can still be previewed. Those values are illustrative; they are not a live NHTSA result. To see real records, start PostgreSQL (or use SQLite), start the API, and run the pipeline.

## API routes

| Route | Description |
|---|---|
| `GET /health` | API health |
| `GET /api/dashboard` | Latest run, recent runs, quality checks, and database coverage |
| `GET /api/runs/{run_id}` | Run summary and per-request log |
| `GET /api/catalog` | Table grain, key, and purpose |
| `GET /api/recalls?make=Toyota&limit=100` | Normalized recall records |
| `POST /api/run?start_year=2022&end_year=2026` | Start an ingestion run |

## Quality controls

| Check | What it catches | What happens |
|---|---|---|
| Source coverage | Failed or incomplete source requests | Retry transient errors; mark a partial run for review |
| Required fields and year range | Missing campaign number or invalid vehicle details | Save the original row and reason in quarantine |
| Duplicate records | Repeated campaign/vehicle rows within a response scope | Skip repeated rows and rely on the database unique key across runs |
| Schema changes | Fields not yet recognized by the normalizer | Preserve source JSON and surface the unfamiliar field names |
| Volume change | Large record-count change from a prior run with the same scope | Keep the data and flag the change for review |

An empty response for a vehicle and year is valid; it is different from a failed request.

## Operational runbook

1. Review the latest run status and source coverage in the dashboard.
2. Open the run details to find failed or slow make/model/year requests and inspect retry counts.
3. Check the raw snapshot and quarantine file for the affected run under `data/`.
4. Correct the source mapping or input issue, then rerun the same year range.
5. Confirm that the new run completed and the affected records appear in the database.

Common cases:

- **NHTSA timeout, HTTP 429, or 5xx:** bounded retries use backoff; the request is marked failed if retries are exhausted.
- **Unrecognized source field:** raw data is retained and the field is listed for review before changing the mapping.
- **Unexpected volume change:** the records are kept; compare the latest and previous raw snapshots.
- **Dashboard says API disconnected:** start FastAPI and check that `http://localhost:8000/health` returns `{"status":"ok"}`.

## Scheduled ingestion and deployment

The GitHub Actions workflow supports scheduled and manual ingestion. Configure the `DATABASE_URL` repository secret with a reachable, persistent PostgreSQL database. The hosted workflow does not provide a persistent database by itself.

The dashboard is a Vite/React frontend and the API is a separate FastAPI service. A Vercel frontend deployment will also need a reachable API URL and a persistent database service; deploying only the static frontend will show the labeled preview data.

## Scope

Mobility Monitor requests public NHTSA recall data by make, model, and model year. It does not ingest VINs, consumer complaint narratives, names, or contact details. See the [NHTSA dataset and API documentation](https://www.nhtsa.gov/nhtsa-datasets-and-apis) before expanding the source catalog or request volume.
