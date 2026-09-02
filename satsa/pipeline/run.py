"""run_pipeline(period): PRECHECK -> FEATURES -> MODULE_A -> MODULE_B -> MODULE_C -> MODULE_D -> EXPLAIN -> TREND -> PERSIST -> AUDIT.

Idempotent: an identical (inputs, config, code, models) run is not repeated unless forced.
Every row written carries run_id; nothing from earlier runs is deleted.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from satsa.analytics.module_a_execution import run_module_a
from satsa.analytics.module_b_negative import run_module_b
from satsa.analytics.module_c_benchmark import run_module_c
from satsa.analytics.module_d_prioritise import apply_decisions, build_review_queue
from satsa.audit.audit_log import finish_run, start_run
from satsa.audit.hashing import hash_dataframe, hash_obj
from satsa.config import Settings
from satsa.db.connection import Database
from satsa.db.repo import fetch_df, fetch_one, insert_df, latest_success_run_id, to_json
from satsa.explain import explain_findings
from satsa.features.build import build_features, persist_features
from satsa.models.registry import ModelBundle, load_active_bundle
from satsa.version import get_code_hash

STAGES = ["PRECHECK", "FEATURES", "MODULE_A", "MODULE_B", "MODULE_C", "MODULE_D", "EXPLAIN", "TREND", "PERSIST", "AUDIT_FINISH"]


@dataclass
class RunResult:
    run_id: str
    period: str
    status: str
    stage_log: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)
    output_hash: str | None = None
    error: str | None = None
    ml_used: bool = False

    def summary(self) -> str:
        secs = sum(s.get("seconds", 0) or 0 for s in self.stage_log)
        return f"{self.status} run {self.run_id} period {self.period} in {secs:.1f}s counts={self.counts}" + (f" error={self.error}" if self.error else "")


class _Stage:
    def __init__(self, log: list[dict], name: str):
        self.log, self.name, self.t0 = log, name, time.perf_counter()

    def done(self, rows: int | None = None, **extra: Any) -> None:
        self.log.append({"stage": self.name, "status": "OK", "rows": rows, "seconds": round(time.perf_counter() - self.t0, 3), **extra})


def input_manifest(conn, period: str) -> tuple[list[dict], str]:
    df = fetch_df(conn, "SELECT submission_id, entity_id, submission_period, file_hash FROM raw_submissions WHERE superseded = FALSE AND fatal = FALSE AND submission_period <= ? ORDER BY submission_id", [period])
    manifest = df.to_dict(orient="records")
    return manifest, hash_obj([(m["submission_id"], m["file_hash"]) for m in manifest])


def previous_sri(conn, period: str) -> dict[str, float]:
    prev = fetch_one(conn, "SELECT max(submission_period) FROM sri_scores WHERE submission_period < ?", [period])
    if not prev or prev[0] is None:
        return {}
    run_id = latest_success_run_id(conn, prev[0])
    if run_id is None:
        return {}
    df = fetch_df(conn, "SELECT entity_id, sri FROM sri_scores WHERE run_id = ?", [run_id])
    return dict(zip(df["entity_id"], df["sri"]))


def run_pipeline(period: str, *, settings: Settings, db: Database, force: bool = False, triggered_by: str = "cli", trigger_source: str = "cli", bundle: ModelBundle | None = None) -> RunResult:
    log: list[dict[str, Any]] = []
    with db.read() as conn:
        manifest, in_hash = input_manifest(conn, period)
        if not any(m["submission_period"] == period for m in manifest):
            raise RuntimeError(f"no usable submissions for {period}; ingest data first")
        if bundle is None:
            bundle = load_active_bundle(conn, settings, strict=True)
        versions = bundle.versions
        prev_sri = previous_sri(conn, period)
        dup = fetch_one(
            conn,
            "SELECT run_id FROM audit_runs WHERE run_type = 'PIPELINE' AND status = 'SUCCESS' AND submission_period = ? AND input_hash = ? AND config_hash = ? AND code_hash = ? AND model_versions_json = ? ORDER BY finished_at DESC LIMIT 1",
            [period, in_hash, settings.config_hash, get_code_hash(), to_json(versions)],
        )
    if dup and not force:
        with db.write() as conn:
            rid = start_run(conn, settings, run_type="PIPELINE", period=period, triggered_by=triggered_by, trigger_source=trigger_source, model_versions=versions, input_manifest=manifest, input_hash=in_hash)
            finish_run(conn, settings, rid, status="SKIPPED_IDENTICAL", output_manifest={"reused_run_id": dup[0]}, stage_log=[{"stage": "PRECHECK", "status": "SKIPPED_IDENTICAL", "reused_run_id": dup[0]}])
        return RunResult(rid, period, "SKIPPED_IDENTICAL", counts={"reused_run_id": dup[0]})

    with db.write() as conn:
        run_id = start_run(conn, settings, run_type="PIPELINE", period=period, triggered_by=triggered_by, trigger_source=trigger_source, model_versions=versions, input_manifest=manifest, input_hash=in_hash)
    result = RunResult(run_id, period, "RUNNING", log, ml_used=bundle.available)
    try:
        st = _Stage(log, "PRECHECK")
        st.done(len(manifest), models=versions, ml_available=bundle.available)

        st = _Stage(log, "FEATURES")
        with db.read() as conn:
            fb = build_features(conn, settings, period, run_id)
        st.done(len(fb.rows))

        st = _Stage(log, "MODULE_A")
        ma = run_module_a(fb, settings, bundle, run_id)
        st.done(len(ma.findings), alert_flags=len(ma.alert_flags), detectors=ma.detectors)

        st = _Stage(log, "MODULE_B")
        mb = run_module_b(fb, settings, run_id)
        st.done(len(mb.findings))

        st = _Stage(log, "MODULE_C")
        sri_rows, _ = run_module_c(fb, settings, {e: s.p_final for e, s in ma.scores.items()}, mb.p_b, prev_sri, run_id)
        st.done(len(sri_rows))

        st = _Stage(log, "MODULE_D")
        findings = ma.findings + mb.findings
        apply_decisions(findings, settings)
        build_review_queue(ma.alert_flags, settings)
        st.done(len(findings), manual_review=sum(f["decision"] == "MANUAL_REVIEW" for f in findings), auto_flag=sum(f["decision"] == "AUTO_FLAG" for f in findings))

        st = _Stage(log, "EXPLAIN")
        st.done(explain_findings(findings, fb, bundle, settings))

        st = _Stage(log, "TREND")
        trend_rows = [{
            "entity_id": r["entity_id"], "submission_period": period, "run_id": run_id, "sri": r["sri"], "sri_delta": r["sri_delta_prev"], "sri_slope_3": None,
            "n_findings_a": sum(1 for f in ma.findings if f["entity_id"] == r["entity_id"] and f["rule_id"]),
            "n_findings_b": sum(1 for f in mb.findings if f["entity_id"] == r["entity_id"] and f["rule_id"]),
            "top_feature_deltas_json": None,
        } for r in sri_rows]
        st.done(len(trend_rows))

        st = _Stage(log, "PERSIST")
        f_df, a_df, s_df, t_df = pd.DataFrame(findings), pd.DataFrame(ma.alert_flags), pd.DataFrame(sri_rows), pd.DataFrame(trend_rows)
        out_hash = hash_obj({
            "findings": hash_dataframe(f_df.drop(columns=["finding_id", "run_id"], errors="ignore")),
            "flags": hash_dataframe(a_df.drop(columns=["flag_id", "run_id"], errors="ignore")),
            "sri": hash_dataframe(s_df.drop(columns=["run_id"], errors="ignore")),
        })
        with db.write() as conn:
            counts = persist_features(conn, fb)
            counts["findings"] = insert_df(conn, "findings", f_df) if len(f_df) else 0
            counts["alert_sample_flags"] = insert_df(conn, "alert_sample_flags", a_df) if len(a_df) else 0
            counts["sri_scores"] = insert_df(conn, "sri_scores", s_df)
            counts["trend_entity"] = insert_df(conn, "trend_entity", t_df)
            st.done(sum(counts.values()), **counts)
            st = _Stage(log, "AUDIT_FINISH")
            finish_run(conn, settings, run_id, status="SUCCESS", output_manifest={"counts": counts, "ml_used": bundle.available}, output_hash=out_hash, stage_log=log)
            st.done()
        result.status, result.counts, result.output_hash = "SUCCESS", counts, out_hash
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        log.append({"stage": "ERROR", "status": "FAILED", "error": err, "trace": traceback.format_exc()[-2000:]})
        with db.write() as conn:
            finish_run(conn, settings, run_id, status="FAILED", stage_log=log, error_text=err)
        result.status, result.error = "FAILED", err
    return result
