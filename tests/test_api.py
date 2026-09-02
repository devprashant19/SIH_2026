"""API tests against the session-scoped scored database. Every endpoint family is exercised."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from satsa.api.main import create_app
from satsa.config import Settings
from satsa.db.connection import Database


@pytest.fixture(scope="module")
def client(scored_db: tuple[Settings, Database]) -> Iterator[TestClient]:
    settings, db = scored_db
    app = create_app(settings=settings, database=db)
    with TestClient(app) as c:
        yield c


def _ok(r):
    assert r.status_code == 200, r.text
    return r.json()


def test_health_periods_summary(client: TestClient) -> None:
    h = _ok(client.get("/api/v1/health"))
    assert h["status"] == "ok" and h["active_models"].get("entity_ensemble")
    periods = _ok(client.get("/api/v1/periods"))
    assert [p["period"] for p in periods] == ["2026-01", "2026-02", "2026-03", "2026-04"] and all(p["latest_run_id"] for p in periods)
    s = _ok(client.get("/api/v1/summary", params={"period": "2026-04"}))
    assert s["n_entities"] == 4 and s["n_uncertain"] >= 0 and s["run_id"]
    assert client.get("/api/v1/does-not-exist").status_code == 404


def test_heatmap_and_entity_detail(client: TestClient) -> None:
    hm = _ok(client.get("/api/v1/entities/heatmap", params={"period": "2026-04"}))
    assert len(hm["rows"]) == 4 and hm["rows"][0]["priority_rank"] == 1
    row = next(r for r in hm["rows"] if r["entity_id"] == "E03")
    assert set(row["dims"]) >= {"execution_gap", "negative_space"} and row["capabilities"].get("Investigation") is not None
    assert len(row["trend"]) == 4
    d = _ok(client.get("/api/v1/entities/E03", params={"period": "2026-04"}))
    assert d["sri"]["sri"] > 0 and abs(sum(x["weight"] for x in d["sri"]["dimensions"]) - 1.0) < 1e-6
    assert d["findings_summary"]["by_class"]["execution_gap"] >= 3
    assert any(f["name"] == "note_template_score" for f in d["headline_features"])
    assert d["data_quality"]["rows"] > 0 and len(d["recent_periods"]) == 4
    card = _ok(client.get("/api/v1/entities/E03/sri", params={"period": "2026-04"}))
    assert abs(sum(x["contribution"] for x in card["dimensions"]) - card["sri"]) < 1e-6
    feats = _ok(client.get("/api/v1/entities/E03/features", params={"period": "2026-04"}))
    assert "fast_close_rate_critical" in feats["features"] and feats["peer_group"]["n"] == 4
    assert client.get("/api/v1/entities/NOPE").status_code == 404


def test_findings_drilldown_to_raw_records(client: TestClient) -> None:
    lst = _ok(client.get("/api/v1/findings", params={"period": "2026-04", "entity_id": "E03", "status": "open"}))
    assert lst["total"] >= 3 and all(i["feedback_status"] is None for i in lst["items"])
    rule_finding = next(i for i in lst["items"] if i["rule_id"] == "EG-02")
    d = _ok(client.get(f"/api/v1/findings/{rule_finding['finding_id']}"))
    assert d["rule"]["rule_id"] == "EG-02" and d["rule"]["template"] and d["rationale"]
    assert d["t_star"] == pytest.approx(0.2) and d["decision"] in ("AUTO_FLAG", "MANUAL_REVIEW", "AUTO_CLEAR")
    assert any(f["name"] == "fast_close_rate_critical" for f in d["evidence_features"])
    ev = _ok(client.get(f"/api/v1/findings/{rule_finding['finding_id']}/evidence", params={"limit": 5, "sort": "ttc"}))
    assert ev["total"] > 0 and len(ev["items"]) <= 5 and ev["items"][0]["time_to_close_min"] < 15
    a = ev["items"][0]
    raw = _ok(client.get(f"/api/v1/alerts/{a['entity_id']}/{a['submission_period']}/{a['alert_id']}"))
    assert raw["alert"]["alert_id"] == a["alert_id"] and raw["submission"]["file_hash"] and raw["raw_line"]
    combined = next(i for i in lst["items"] if i["rule_id"] is None)
    cd = _ok(client.get(f"/api/v1/findings/{combined['finding_id']}"))
    assert cd["shap"] and cd["shap"]["contributions"] and cd["p_ml"] is not None


def test_queue_controls_and_feedback_flow(client: TestClient) -> None:
    qd = _ok(client.get("/api/v1/review/queue", params={"period": "2026-04", "entity_id": "E03", "limit": 10}))
    assert qd["total"] > 0 and qd["items"][0]["queue_rank"] == 1 and qd["items"][0]["alert"]["severity"]
    item = _ok(client.get(f"/api/v1/review/queue/{qd['items'][0]['flag_id']}"))
    assert item["alert"]["alert"]["alert_id"] == qd["items"][0]["alert_id"]
    controls = _ok(client.get("/api/v1/controls/priority", params={"period": "2026-04"}))
    assert any(c["entity_id"] is None for c in controls) and controls[0]["priority"] >= controls[-1]["priority"]

    fid = _ok(client.get("/api/v1/findings", params={"period": "2026-04", "entity_id": "E03"}))["items"][0]["finding_id"]
    r = client.post("/api/v1/feedback", json={"target_type": "finding", "target_id": fid, "decision": "ACCEPT", "reviewer_id": "examiner_01", "note": "Confirmed with SOC lead"})
    assert r.status_code == 201 and r.json()["decision"] == "ACCEPT"
    hist = _ok(client.get("/api/v1/feedback", params={"target_id": fid}))
    assert hist[0]["reviewer_id"] == "examiner_01"
    assert _ok(client.get(f"/api/v1/findings/{fid}"))["feedback_status"] == "ACCEPT"
    reviewed = _ok(client.get("/api/v1/findings", params={"period": "2026-04", "entity_id": "E03", "status": "reviewed"}))
    assert [i["finding_id"] for i in reviewed["items"]] == [fid]
    bulk = client.post("/api/v1/feedback/bulk", json={"items": [{"target_type": "alert_flag", "target_id": qd["items"][0]["flag_id"], "decision": "REJECT", "reviewer_id": "examiner_02"}]})
    assert bulk.status_code == 201 and bulk.json()["recorded"] == 1
    stats = _ok(client.get("/api/v1/feedback/stats"))
    assert stats["n_feedback"] == 2 and any(c["name"] == "calibrator_a" for c in stats["calibrators"])
    assert client.post("/api/v1/feedback", json={"target_type": "finding", "target_id": "missing", "decision": "ACCEPT", "reviewer_id": "x"}).status_code == 404
    recal = _ok(client.post("/api/v1/feedback/recalibrate", json={"promote": False}))
    assert recal["skipped_reason"] and recal["skipped_reason"].startswith("INSUFFICIENT_FEEDBACK")
    audit_types = {r["run_type"] for r in _ok(client.get("/api/v1/audit/runs"))}
    assert {"FEEDBACK", "RECALIBRATE", "PIPELINE"} <= audit_types


def test_benchmark_coverage_trends(client: TestClient) -> None:
    metrics = _ok(client.get("/api/v1/benchmark/metrics"))
    assert any(m["key"] == "escalation_ratio_critical" for m in metrics)
    b = _ok(client.get("/api/v1/benchmark", params={"feature": "note_template_score", "period": "2026-04", "entity_id": "E03"}))
    assert b["entity_value"] > 0.8 and len(b["entities"]) == 4 and b["stats"]["median"] is not None
    assert client.get("/api/v1/benchmark", params={"feature": "nope"}).status_code == 404
    rank = _ok(client.get("/api/v1/benchmark/rank", params={"period": "2026-04"}))
    assert rank["rows"][0]["sri"] >= rank["rows"][-1]["sri"]
    cov = _ok(client.get("/api/v1/coverage", params={"period": "2026-04", "dimension": "category"}))
    e06 = next(r for r in cov["rows"] if r["entity_id"] == "E06")
    lm = cov["columns"].index("lateral_movement")
    assert e06["cells"][lm]["status"] == "absent"
    cell = _ok(client.get("/api/v1/coverage/E06/lateral_movement", params={"period": "2026-04"}))
    assert cell["status"] == "absent" and "sector" in cell["expected_reason"]
    for dim in ("asset_class", "source"):
        assert _ok(client.get("/api/v1/coverage", params={"period": "2026-04", "dimension": dim}))["rows"]
    t = _ok(client.get("/api/v1/trends/entities/E03"))
    assert t["periods"] == ["2026-01", "2026-02", "2026-03", "2026-04"] and t["sri"][3] > t["sri"][0]
    sec = _ok(client.get("/api/v1/trends/sector"))
    assert len(sec["median_sri"]) == 4
    ctrl = _ok(client.get("/api/v1/trends/controls"))
    assert ctrl["controls"] and len(ctrl["controls"][0]["series"]) == 4


def test_ingestion_pipeline_jobs(client: TestClient, scored_db: tuple[Settings, Database]) -> None:
    settings, _ = scored_db
    subs = _ok(client.get("/api/v1/ingest/submissions", params={"period": "2026-04"}))
    assert len(subs) == 4 and subs[0]["validation"]["n_rows"] > 0
    one = _ok(client.get(f"/api/v1/ingest/submissions/{subs[0]['submission_id']}"))
    assert one["submission_id"] == subs[0]["submission_id"]
    # upload the E01 April CSVs again: identical content -> ALREADY_INGESTED
    syn = Path(settings.resolve(settings.paths.processed_dir)).parent / "syn"
    files = [("files", (p.name, p.read_bytes(), "text/csv")) for p in sorted(syn.glob("E01_2026-04_*.csv"))]
    r = client.post("/api/v1/ingest/upload", data={"entity_id": "E01", "period": "2026-04"}, files=files)
    assert r.status_code == 201 and r.json()["status"] == "ALREADY_INGESTED"
    job = client.post("/api/v1/pipeline/run", json={"period": "2026-04"})
    assert job.status_code == 202
    jid = job.json()["job_id"]
    for _ in range(200):
        st = _ok(client.get(f"/api/v1/pipeline/jobs/{jid}"))
        if st["status"] in ("SUCCESS", "FAILED"):
            break
        time.sleep(0.1)
    assert st["status"] == "SUCCESS" and st["result"]["status"] == "SKIPPED_IDENTICAL"
    runs = _ok(client.get("/api/v1/pipeline/runs", params={"period": "2026-04"}))
    assert runs[0]["status"] == "SKIPPED_IDENTICAL" and _ok(client.get(f"/api/v1/pipeline/runs/{runs[1]['run_id']}"))["stages"]
    assert _ok(client.get("/api/v1/pipeline/status"))["last_run"]


def test_config_roundtrip_and_what_if(client: TestClient) -> None:
    cfg = _ok(client.get("/api/v1/config"))
    assert cfg["costs"]["derived"]["execution_gap"]["t_star"] == pytest.approx(0.2) and len(cfg["rules"]) == 19
    before = cfg["config_hash"]
    wi = _ok(client.post("/api/v1/config/what-if", json={"period": "2026-04", "costs": {"execution_gap": {"C_FP": 1, "C_FN": 9}}}))
    assert wi["thresholds"]["execution_gap"]["t_star"] == pytest.approx(0.1) and len(wi["rows"]) == 4
    bad = client.put("/api/v1/config", json={"sri_weights": {"dimensions": {"execution_gap": {"weight": 0.9}}}})
    assert bad.status_code == 422
    good = _ok(client.put("/api/v1/config", json={"costs": {"classes": {"execution_gap": {"C_FN": 5}}}, "note": "raise cost of missing an execution gap", "saved_by": "examiner_01"}))
    assert good["config_hash"] != before and good["costs"]["derived"]["execution_gap"]["t_star"] == pytest.approx(1 / 6)
    assert _ok(client.get("/api/v1/health"))["config_hash"] == good["config_hash"]
    hist = _ok(client.get("/api/v1/config/history"))
    assert hist[0]["note"] == "raise cost of missing an execution gap"
    assert "CONFIG" in {r["run_type"] for r in _ok(client.get("/api/v1/audit/runs"))}
    _ok(client.put("/api/v1/config", json={"costs": {"classes": {"execution_gap": {"C_FN": 4}}}, "saved_by": "examiner_01"}))


def test_audit_models_reports(client: TestClient) -> None:
    v = _ok(client.get("/api/v1/audit/verify"))
    assert v["ok"] and v["n_runs"] > 5
    runs = _ok(client.get("/api/v1/audit/runs", params={"type": "PIPELINE"}))
    assert runs and runs[0]["code_hash"] and runs[0]["config_hash"] and runs[0]["run_hash"]
    detail = _ok(client.get(f"/api/v1/audit/runs/{runs[0]['run_id']}"))
    assert detail["config_snapshot"]["sri_weights"] and detail["input_manifest"]
    models = _ok(client.get("/api/v1/models"))
    names = {m["model_name"] for m in models if m["is_active"]}
    assert {"entity_ensemble", "calibrator_a", "alert_if"} <= names
    assert _ok(client.get(f"/api/v1/models/{models[0]['version']}"))
    pdf = client.get("/api/v1/reports/entity/E03.pdf", params={"period": "2026-04"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    port = client.get("/api/v1/reports/period/2026-04.pdf")
    assert port.status_code == 200 and port.content[:4] == b"%PDF"
    for kind in ("findings", "sri", "alert_samples", "features"):
        csv = client.get(f"/api/v1/reports/{kind}.csv", params={"period": "2026-04"})
        assert csv.status_code == 200 and csv.text.splitlines()[0]
    assert client.get("/api/v1/reports/nope.csv").status_code == 404
    hist = _ok(client.get("/api/v1/reports"))
    assert len(hist) >= 6 and hist[0]["format"] in ("pdf", "csv")
