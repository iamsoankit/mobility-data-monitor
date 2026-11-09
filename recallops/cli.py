from __future__ import annotations

import argparse
from datetime import date

from .database import initialize_database
from .database import SessionLocal
from .models import PipelineRun
from .pipeline import run_pipeline
from sqlalchemy import select


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest and validate vehicle recall data from NHTSA.")
    parser.add_argument("--start-year", type=int, default=date.today().year - 3)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    args = parser.parse_args()
    initialize_database()
    run_id = run_pipeline(args.start_year, args.end_year)
    with SessionLocal() as db:
        run = db.scalar(select(PipelineRun).where(PipelineRun.run_id == run_id))
        status = run.status if run else "missing"
        print(f"Finished RecallOps run: {run_id} ({status})")
        if status == "failed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
