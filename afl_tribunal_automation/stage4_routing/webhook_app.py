"""FastAPI intake for the umpiring platform. Run with:

    uvicorn stage4_routing.webhook_app:app --host 0.0.0.0 --port 8000

or `python cli.py serve-webhook`.
"""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException

from config import settings
from stage4_routing.schemas import IncomingUmpireReport
from stage4_routing.umpire_ingest import process_incoming_report

app = FastAPI(title="AFL Tribunal Automation — Umpire Report Intake")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/webhooks/umpire-report")
def umpire_report_webhook(
    report: IncomingUmpireReport,
    x_webhook_secret: str | None = Header(default=None),
) -> dict:
    if settings.umpire_webhook_shared_secret and x_webhook_secret != settings.umpire_webhook_shared_secret:
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    try:
        result = process_incoming_report(report)
    except Exception as exc:  # noqa: BLE001 - surface as a 502 to the caller
        raise HTTPException(status_code=502, detail=f"failed to route report: {exc}") from exc

    return {"umpire_report_id": result.id, "status": result.status.value}
