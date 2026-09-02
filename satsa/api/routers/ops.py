"""Ingestion, pipeline jobs, configuration, audit, model registry and report endpoints."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response

from satsa.api import queries as q
from satsa.api.config_store import config_history, effective_config, save_config, what_if
from satsa.api.deps import get_db_dep, get_reader, get_settings_dep
from satsa.api.schemas import ConfigUpdate, PipelineRunRequest, TrainRequest, WhatIfRequest
from satsa.audit.audit_log import record_event
from satsa.audit.verify import verify_chain
from satsa.config import Settings
from satsa.db.connection import Database
from satsa.ingest.loader import ingest_path, ingest_submission

router = APIRouter()


# ---- ingestion ---------------------------------------------------------------------------

@router.post("/ingest/upload", status_code=201)
async def ingest_upload(request: Request, entity_id: str = Form(...), period: str = Form(...), mapping: str = Form("generic_csv"),
                        files: list[UploadFile] = File(...), db: Database = Depends(get_db_dep), settings: Settings = Depends(get_settings_dep)) -> dict:
    incoming = settings.resolve(settings.paths.incoming_dir) / f"{entity_id}_{period}"
    incoming.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for up in files:
        dest = incoming / Path(up.filename or "upload").name
        with dest.open("wb") as fh:
            shutil.copyfileobj(up.file, fh)
        saved.append(dest)
    main = next((p for p in saved if "assets" not in p.stem and "entities" not in p.stem and "escalations" not in p.stem and "incidents" not in p.stem), saved[0])
    extras = [p for p in saved if p != main]
    try:
        res = ingest_submission(main, settings=settings, db=db, entity_id=entity_id, submission_period=period, mapping_name=mapping,
                                extra_files=extras, triggered_by="api", trigger_source="api")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"ingest failed: {exc}") from exc
    return {"submission_id": res.submission_id, "status": res.status, "tables": res.tables, "superseded": res.superseded,
            "validation": res.validation.to_dict() if res.validation else None}


@router.post("/ingest/scan")
def ingest_scan(mapping: str = "generic_csv", db: Database = Depends(get_db_dep), settings: Settings = Depends(get_settings_dep)) -> dict:
    folder = settings.resolve(settings.paths.incoming_dir)
    results = ingest_path(folder, settings=settings, db=db, mapping_name=mapping, triggered_by="api", trigger_source="api") if folder.exists() else []
    return {"ingested": [r.summary() for r in results if r.status == "INGESTED"], "skipped": [r.summary() for r in results if r.status == "ALREADY_INGESTED"], "errors": [r.summary() for r in results if r.status == "FATAL"]}


@router.get("/ingest/submissions")
def list_submissions(period: str | None = None, entity_id: str | None = None, conn=Depends(get_reader)) -> list[dict]:
    return q.submissions(conn, period, entity_id)


@router.get("/ingest/submissions/{submission_id}")
def submission(submission_id: str, conn=Depends(get_reader)) -> dict:
    rows = [s for s in q.submissions(conn) if s["submission_id"] == submission_id]
    if not rows:
        row = conn.execute("SELECT entity_id, submission_period FROM raw_submissions WHERE submission_id = ?", [submission_id]).fetchone()
        if row is None:
            raise HTTPException(404, "submission not found")
        rows = [s for s in q.submissions(conn, row[1], row[0]) if s["submission_id"] == submission_id]
    return rows[0]


# ---- pipeline / jobs ---------------------------------------------------------------------

@router.post("/pipeline/run", status_code=202)
def pipeline_run(body: PipelineRunRequest, request: Request, db: Database = Depends(get_db_dep), settings: Settings = Depends(get_settings_dep)) -> dict:
    jobs = request.app.state.jobs
    if jobs.busy():
        raise HTTPException(409, "a job is already running; wait for it to finish")
    from satsa.pipeline.run import run_pipeline

    def _do() -> dict:
        res = run_pipeline(body.period, settings=request.app.state.settings, db=db, force=body.force, triggered_by="api", trigger_source="api")
        return {"run_id": res.run_id, "status": res.status, "counts": res.counts, "error": res.error, "stages": res.stage_log}

    job = jobs.submit("PIPELINE", _do, {"period": body.period, "force": body.force})
    return job.as_dict()


@router.get("/pipeline/jobs")
def pipeline_jobs(request: Request) -> list[dict]:
    return request.app.state.jobs.list()


@router.get("/pipeline/jobs/{job_id}")
def pipeline_job(job_id: str, request: Request) -> dict:
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job.as_dict()


@router.get("/pipeline/status")
def pipeline_status(request: Request, conn=Depends(get_reader)) -> dict:
    active = request.app.state.jobs.active
    last = q.runs(conn, run_type="PIPELINE", limit=1)
    return {"running": active.as_dict() if active else None, "last_run": last[0] if last else None}


@router.get("/pipeline/runs")
def pipeline_runs(period: str | None = None, limit: int = 50, conn=Depends(get_reader)) -> list[dict]:
    return q.runs(conn, run_type="PIPELINE", period=period, limit=limit)


@router.get("/pipeline/runs/{run_id}")
def pipeline_run_detail(run_id: str, conn=Depends(get_reader)) -> dict:
    d = q.run_detail(conn, run_id)
    if d is None:
        raise HTTPException(404, "run not found")
    return d


# ---- config -------------------------------------------------------------------------------

@router.get("/config")
def get_config(settings: Settings = Depends(get_settings_dep)) -> dict:
    return effective_config(settings)


@router.put("/config")
def put_config(body: ConfigUpdate, request: Request, db: Database = Depends(get_db_dep), settings: Settings = Depends(get_settings_dep)) -> dict:
    try:
        with db.write() as conn:
            new = save_config(conn, settings, body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    request.app.state.settings = new
    return effective_config(new)


@router.post("/config/what-if")
def config_what_if(body: WhatIfRequest, conn=Depends(get_reader), settings: Settings = Depends(get_settings_dep)) -> dict:
    return what_if(conn, settings, body)


@router.get("/config/history")
def get_config_history(limit: int = 50, conn=Depends(get_reader)) -> list[dict]:
    return config_history(conn, limit)


# ---- audit / models -----------------------------------------------------------------------

@router.get("/audit/runs")
def audit_runs(type: str | None = None, period: str | None = None, limit: int = Query(100, le=1000), offset: int = 0, conn=Depends(get_reader)) -> list[dict]:
    return q.runs(conn, run_type=type, period=period, limit=limit, offset=offset)


@router.get("/audit/verify")
def audit_verify(conn=Depends(get_reader)) -> dict:
    v = verify_chain(conn)
    return {"ok": v.ok, "n_runs": v.n_runs, "first_broken_run_id": v.first_broken_run_id, "detail": v.detail}


@router.get("/audit/runs/{run_id}")
def audit_run(run_id: str, conn=Depends(get_reader)) -> dict:
    d = q.run_detail(conn, run_id)
    if d is None:
        raise HTTPException(404, "run not found")
    return d


@router.get("/models")
def list_models(conn=Depends(get_reader)) -> list[dict]:
    return q.models(conn)


@router.get("/models/{version}")
def model_version(version: str, conn=Depends(get_reader)) -> list[dict]:
    rows = [m for m in q.models(conn) if m["version"] == version]
    if not rows:
        raise HTTPException(404, "version not found")
    return rows


@router.post("/models/train", status_code=202)
def train(body: TrainRequest, request: Request, db: Database = Depends(get_db_dep)) -> dict:
    jobs = request.app.state.jobs
    if jobs.busy():
        raise HTTPException(409, "a job is already running; wait for it to finish")
    from dataclasses import asdict

    from satsa.models.train import train_models

    def _do() -> dict:
        res = train_models(db, request.app.state.settings, body.periods, promote=body.promote, triggered_by="api", trigger_source="api")
        return asdict(res)

    return jobs.submit("TRAIN", _do, body.model_dump()).as_dict()


# ---- reports --------------------------------------------------------------------------------

@router.get("/reports")
def report_history(conn=Depends(get_reader)) -> list[dict]:
    out = []
    for r in q.runs(conn, run_type="REPORT", limit=200):
        d = q.run_detail(conn, r["run_id"]) or {}
        m = (d.get("output_manifest") or {})
        out.append({"report_id": r["run_id"], "scope": m.get("scope"), "target": m.get("target"), "period": r["submission_period"], "format": m.get("format"), "created_at": r["finished_at"], "config_hash": r["config_hash"], "run_id": m.get("pipeline_run_id"), "file_name": m.get("file_name")})
    return out


@router.get("/reports/entity/{entity_id}.pdf")
def entity_pdf(entity_id: str, period: str | None = None, db: Database = Depends(get_db_dep), settings: Settings = Depends(get_settings_dep)) -> FileResponse:
    from satsa.reports.pdf import entity_report

    with db.read() as conn:
        p, run_id = q.current_run(conn, period)
        if run_id is None:
            raise HTTPException(404, "no scored run for this period")
        path = entity_report(conn, settings, entity_id, p)
    _log_report(db, settings, "entity", entity_id, p, "pdf", path.name, run_id)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/reports/period/{period}.pdf")
def period_pdf(period: str, db: Database = Depends(get_db_dep), settings: Settings = Depends(get_settings_dep)) -> FileResponse:
    from satsa.reports.pdf import period_report

    with db.read() as conn:
        p, run_id = q.current_run(conn, period)
        if run_id is None:
            raise HTTPException(404, "no scored run for this period")
        path = period_report(conn, settings, p)
    _log_report(db, settings, "period", p, p, "pdf", path.name, run_id)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/reports/{kind}.csv")
def csv_export(kind: str, period: str | None = None, entity_id: str | None = None, db: Database = Depends(get_db_dep), settings: Settings = Depends(get_settings_dep)) -> Response:
    from satsa.reports.csv_export import export_csv

    if kind not in ("findings", "sri", "alert_samples", "features"):
        raise HTTPException(404, "unknown export")
    with db.read() as conn:
        p, run_id = q.current_run(conn, period)
        if run_id is None:
            raise HTTPException(404, "no scored run for this period")
        text = export_csv(conn, kind, run_id, entity_id)
    _log_report(db, settings, "entity" if entity_id else "period", entity_id or p, p, "csv", f"{kind}_{p}.csv", run_id)
    return Response(content=text, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{kind}_{p}.csv"'})


def _log_report(db: Database, settings: Settings, scope: str, target: str, period: str, fmt: str, file_name: str, pipeline_run_id: str) -> None:
    with db.write() as conn:
        record_event(conn, settings, run_type="REPORT", period=period, triggered_by="api", trigger_source="api",
                     manifest={"scope": scope, "target": target, "format": fmt, "file_name": file_name, "pipeline_run_id": pipeline_run_id, "generated_at": datetime.now().isoformat(timespec="seconds")})
