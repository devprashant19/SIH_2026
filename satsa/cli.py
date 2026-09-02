"""SAT-SA command line.

  satsa info          show version, code hash, config hash, DB path
  satsa init-db       create the DuckDB schema
  satsa seed          generate the synthetic multi-entity dataset
  satsa ingest        ingest a file or directory of submissions
  satsa run           run the analytics pipeline for a period
  satsa train         train and register models
  satsa verify-audit  recompute the audit hash chain
"""

from __future__ import annotations

from pathlib import Path

import typer

from satsa.config import load_settings
from satsa.version import RULES_VERSION, FEATURE_VERSION, __version__, get_code_hash

app = typer.Typer(help="SAT-SA: Supervisory Analytics Tool for SOC Assessment", no_args_is_help=True)


@app.command()
def info(config_dir: Path | None = typer.Option(None, help="Config directory (default: ./config)")) -> None:
    """Print version identifiers and effective configuration hashes."""
    settings = load_settings(config_dir)
    typer.echo(f"satsa {__version__}  rules={RULES_VERSION}  features={FEATURE_VERSION}")
    typer.echo(f"code_hash    {get_code_hash()}")
    typer.echo(f"config_hash  {settings.config_hash}")
    typer.echo(f"weights_hash {settings.weights_hash}")
    typer.echo(f"config_dir   {settings.config_dir}")
    typer.echo(f"db_path      {settings.db_path}")
    for cls in ("execution_gap", "negative_space", "alert_sample"):
        typer.echo(f"t*[{cls}] = {settings.t_star(cls):.3f}  band ±{settings.band_halfwidth(cls):.2f}")


@app.command("init-db")
def init_db(config_dir: Path | None = typer.Option(None, help="Config directory (default: ./config)")) -> None:
    """Create all tables in the DuckDB store (safe to re-run)."""
    from satsa.db.connection import Database
    from satsa.db.migrate import apply_schema, list_tables

    settings = load_settings(config_dir)
    db = Database(settings.db_path)
    try:
        with db.write() as conn:
            version = apply_schema(conn)
        with db.read() as conn:
            tables = list_tables(conn)
    finally:
        db.close()
    typer.echo(f"schema v{version} applied at {settings.db_path}")
    typer.echo(f"{len(tables)} tables: {', '.join(tables)}")


@app.command()
def seed(
    seed_value: int | None = typer.Option(None, "--seed", help="Random seed (default: app.seed from config)"),
    out: Path | None = typer.Option(None, help="Output directory (default: paths.synthetic_dir)"),
    entities: str | None = typer.Option(None, help="Comma-separated subset of entity ids, e.g. E01,E03"),
    config_dir: Path | None = typer.Option(None, help="Config directory (default: ./config)"),
) -> None:
    """Generate the synthetic 8-entity x 6-period dataset (CSV, JSON, SQLite) with ground truth."""
    from simulator.generate import generate_dataset

    settings = load_settings(config_dir)
    ids = [e.strip() for e in entities.split(",")] if entities else None
    summary = generate_dataset(settings, seed=seed_value, out_dir=out, entity_ids=ids)
    typer.echo(f"seed={summary.seed} files={len(summary.files)} alerts={summary.total_alerts} -> {summary.out_dir}")
    for (ent, per), n in sorted(summary.alerts_per_entity_period.items()):
        typer.echo(f"  {ent} {per}: {n} alerts")
    typer.echo("ground truth: " + ", ".join(str(p) for p in summary.ground_truth.values()))


@app.command()
def features(
    period: str = typer.Argument(..., help="Submission period YYYY-MM"),
    persist: bool = typer.Option(False, help="Write rows to features_entity_period / peer_baselines"),
    show: str | None = typer.Option(None, help="Comma-separated features to print per entity"),
    config_dir: Path | None = typer.Option(None, help="Config directory (default: ./config)"),
) -> None:
    """Compute entity-period features for one period (diagnostic; the pipeline does this automatically)."""
    from satsa.audit.hashing import new_id
    from satsa.db.connection import Database
    from satsa.features.build import build_features, persist_features

    settings = load_settings(config_dir)
    db = Database(settings.db_path)
    try:
        run_id = new_id("feat_")
        with db.read() as conn:
            result = build_features(conn, settings, period, run_id)
        typer.echo(f"{len(result.rows)} entities, {len(result.baselines)} baseline rows in {result.seconds:.1f}s (run {run_id})")
        cols = [c.strip() for c in show.split(",")] if show else ["n_alerts", "fast_close_rate_critical", "note_template_score", "escalation_ratio_critical", "silent_asset_rate_tier1_hist", "val_warn_rate"]
        for eid, feats in result.values.items():
            parts = []
            for c in cols:
                v = feats.get(c)
                parts.append(f"{c}={'—' if v is None or v.value is None else f'{v.value:.3f}'}{'' if v is None or v.flag == 'OK' else f'({v.flag})'}")
            typer.echo(f"  {eid} [{result.assignments[eid].peer_group_id} L{result.assignments[eid].peer_level}] " + "  ".join(parts))
        if persist:
            with db.write() as conn:
                counts = persist_features(conn, result)
            typer.echo(f"persisted {counts}")
    finally:
        db.close()


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="Submission file or directory (see loader.py for naming convention)"),
    entity_id: str | None = typer.Option(None, help="Override entity id (single file only)"),
    period: str | None = typer.Option(None, help="Override submission period YYYY-MM (single file only)"),
    mapping: str = typer.Option("generic_csv", help="Schema mapping name under config/schema_mappings"),
    config_dir: Path | None = typer.Option(None, help="Config directory (default: ./config)"),
) -> None:
    """Ingest CSV / JSON / SQLite submissions into the store, recording validation results."""
    from satsa.db.connection import Database
    from satsa.db.migrate import apply_schema
    from satsa.ingest.loader import ingest_path, ingest_submission

    settings = load_settings(config_dir)
    db = Database(settings.db_path)
    try:
        with db.write() as conn:
            apply_schema(conn)
        if path.is_file() and (entity_id or period):
            results = [ingest_submission(path, settings=settings, db=db, entity_id=entity_id, submission_period=period, mapping_name=mapping)]
        else:
            results = ingest_path(path, settings=settings, db=db, mapping_name=mapping)
    finally:
        db.close()
    for r in results:
        typer.echo(r.summary())
    n_fatal = sum(r.status == "FATAL" for r in results)
    typer.echo(f"{len(results)} submissions processed, {n_fatal} fatal")


@app.command()
def train(
    periods: str = typer.Option(..., help="Comma-separated training periods, e.g. 2026-01,2026-02,2026-03"),
    promote: bool = typer.Option(False, help="Make the new models active"),
    seed_value: int | None = typer.Option(None, "--seed"),
    config_dir: Path | None = typer.Option(None, help="Config directory (default: ./config)"),
) -> None:
    """Train the anomaly ensemble, alert model and calibrators on historical periods."""
    from satsa.db.connection import Database
    from satsa.db.migrate import apply_schema
    from satsa.models.train import train_models

    settings = load_settings(config_dir)
    db = Database(settings.db_path)
    try:
        with db.write() as conn:
            apply_schema(conn)
        plist = [p.strip() for p in periods.split(",") if p.strip()]
        res = train_models(db, settings, plist, promote=promote, seed=seed_value)
    finally:
        db.close()
    for name, m in res.metrics.items():
        typer.echo(f"{name:<18} {res.versions[name]}  {m}")
    typer.echo(f"entity rows={res.rows_entity} alert rows={res.rows_alert} promoted={promote}")


@app.command()
def run(
    period: str = typer.Argument(..., help="Submission period YYYY-MM"),
    force: bool = typer.Option(False, help="Re-run even if an identical run exists"),
    config_dir: Path | None = typer.Option(None, help="Config directory (default: ./config)"),
) -> None:
    """Run the supervisory analytics pipeline for one period."""
    from satsa.db.connection import Database
    from satsa.db.migrate import apply_schema
    from satsa.pipeline.run import run_pipeline

    settings = load_settings(config_dir)
    db = Database(settings.db_path)
    try:
        with db.write() as conn:
            apply_schema(conn)
        res = run_pipeline(period, settings=settings, db=db, force=force, triggered_by="cli")
    finally:
        db.close()
    typer.echo(res.summary())
    for s in res.stage_log:
        extra = {k: v for k, v in s.items() if k not in ("stage", "status", "rows", "seconds", "trace")}
        typer.echo(f"  {s['stage']:<13} {s['status']:<8} rows={s.get('rows')} {s.get('seconds', '')}s {extra if extra else ''}")
    if res.status == "FAILED":
        raise typer.Exit(code=1)


@app.command()
def demo(
    workdir: Path | None = typer.Option(None, help="Run in a scratch directory instead of the project data folder"),
    keep: bool = typer.Option(False, help="Reuse existing data instead of regenerating it"),
    periods: str | None = typer.Option(None, help="Comma-separated periods (default: all six)"),
    config_dir: Path | None = typer.Option(None, help="Config directory (default: ./config)"),
) -> None:
    """Walk through the whole supervisory workflow and narrate what a supervisor would see."""
    from satsa.db.connection import Database
    from satsa.demo import demo_settings, run_demo

    settings = load_settings(config_dir)
    if workdir:
        workdir.mkdir(parents=True, exist_ok=True)
        settings = demo_settings(settings, workdir)
    db = Database(settings.db_path)
    try:
        plist = [p.strip() for p in periods.split(",")] if periods else None
        run_demo(settings, db, rebuild=not keep, periods=plist, echo=typer.echo)
    finally:
        db.close()
    typer.echo("\nStart the dashboard with `satsa serve` and open http://localhost:8000 to follow the same path in the UI.")


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Bind address (default: api.host from config)"),
    port: int | None = typer.Option(None, help="Port (default: api.port from config)"),
    reload: bool = typer.Option(False, help="Auto-reload on code changes (development only)"),
    config_dir: Path | None = typer.Option(None, help="Config directory (default: ./config)"),
) -> None:
    """Start the API and dashboard server (single worker; DuckDB allows one writer)."""
    import uvicorn

    settings = load_settings(config_dir)
    uvicorn.run("satsa.api.main:app", host=host or settings.api.host, port=port or settings.api.port, reload=reload, workers=1)


@app.command("verify-audit")
def verify_audit(config_dir: Path | None = typer.Option(None, help="Config directory (default: ./config)")) -> None:
    """Recompute the audit hash chain."""
    from satsa.audit.verify import verify_chain
    from satsa.db.connection import Database

    settings = load_settings(config_dir)
    db = Database(settings.db_path, read_only=True)
    try:
        with db.read() as conn:
            v = verify_chain(conn)
    finally:
        db.close()
    typer.echo(f"ok={v.ok} runs={v.n_runs}" + (f" first_broken={v.first_broken_run_id} ({v.detail})" if not v.ok else ""))
    if not v.ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
