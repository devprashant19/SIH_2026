"""PDF reports with reportlab (pure Python, no system dependencies).

entity_report: scorecard arithmetic, findings with rationale, review-queue sample, feedback,
and the config/model/run hashes that make the report reproducible.
period_report: portfolio heatmap table, control priorities, queue statistics.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from satsa.api import queries as q
from satsa.config import Settings
from satsa.db.repo import fetch_df, fetch_one

STYLES = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=STYLES["BodyText"], fontSize=8.5, leading=11)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#5c6470"))
H1 = ParagraphStyle("h1", parent=STYLES["Heading1"], fontSize=15, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=STYLES["Heading2"], fontSize=11, spaceBefore=8, spaceAfter=3)

GRID = TableStyle([
    ("FONT", (0, 0), (-1, -1), "Helvetica", 8), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
    ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#1b1f24")), ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#e3e6ea")),
    ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
])


def _p(text: str, style=BODY) -> Paragraph:
    return Paragraph(str(text).replace("&", "&amp;").replace("<", "&lt;"), style)


def _fmt(v, digits=2) -> str:
    if v is None:
        return "n/a"
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return str(v)


def _footer(conn: duckdb.DuckDBPyConnection, settings: Settings, run_id: str) -> list:
    row = fetch_one(conn, "SELECT code_hash, config_hash, model_versions_json, finished_at FROM audit_runs WHERE run_id = ?", [run_id])
    return [Spacer(1, 6), _p(f"Pipeline run {run_id} finished {row[3]} · code {str(row[0])[:12]} · config {str(row[1])[:12]} · models {row[2]} · report generated {datetime.now():%Y-%m-%d %H:%M}", SMALL),
            _p("SAT-SA is a supervisory analytics aid. Findings are indicators for examiner review, not conclusions.", SMALL)]


def entity_report(conn: duckdb.DuckDBPyConnection, settings: Settings, entity_id: str, period: str) -> Path:
    p, run_id = q.current_run(conn, period)
    ent = next((e for e in q.entities(conn) if e["entity_id"] == entity_id), None)
    if ent is None or run_id is None:
        raise ValueError("entity or run not found")
    out_dir = settings.resolve(settings.paths.reports_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"SATSA_{entity_id}_{p}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title=f"SAT-SA entity report {entity_id} {p}")
    story = [_p(f"Supervisory assessment: {ent['name']} ({entity_id})", H1), _p(f"Sector {ent['sector']} · size {ent['size_band']} · submission period {p}", SMALL)]

    card = q.sri_scorecard(conn, settings, entity_id, p)
    if card:
        story.append(_p(f"Supervisory Risk Indicator: {card['sri']:.1f} / 100 ({card['band']}), confidence {card['confidence']:.2f}", H2))
        rows = [["Dimension", "Weight", "Score", "Contribution", "Sub-indicators"]]
        for d in card["dimensions"]:
            subs = ", ".join(f"{s['name']} {_fmt(s['raw'], 3)} (pct {_fmt(s['percentile'], 2)})" for s in d["subs"][:4]) if d["subs"] else ""
            rows.append([d["label"], f"{d['weight']:.2f}", f"{d['score']:.1f}", f"{d['contribution']:.1f}", _p(subs, SMALL)])
        t = Table(rows, colWidths=[38 * mm, 15 * mm, 15 * mm, 22 * mm, 90 * mm])
        t.setStyle(GRID)
        story.append(t)
        story.append(_p(f"SRI = sum(weight x dimension score); weights hash {card['weights_hash'][:12]}.", SMALL))

    findings = q.list_findings(conn, period=p, entity_id=entity_id, limit=500)["items"]
    story.append(_p(f"Findings ({len(findings)})", H2))
    rows = [["#", "Rule", "Finding", "p", "Decision", "Rationale"]]
    for f in findings:
        detail = q.finding_detail(conn, settings, f["finding_id"]) or {}
        rows.append([str(f["priority_rank"]), f["rule_id"] or "combined", _p(f["title"], SMALL), _fmt(f["p_final"]), f["decision"].replace("_", " ").lower(), _p(detail.get("rationale", ""), SMALL)])
    if len(rows) == 1:
        rows.append(["", "", "no findings", "", "", ""])
    t = Table(rows, colWidths=[8 * mm, 16 * mm, 34 * mm, 10 * mm, 20 * mm, 92 * mm], repeatRows=1)
    t.setStyle(GRID)
    story.append(t)

    queue = q.review_queue(conn, period=p, entity_id=entity_id, limit=25)["items"]
    story.append(_p(f"Alert samples for manual review ({len(queue)})", H2))
    rows = [["Rank", "Alert", "Rules", "p", "Severity", "Category", "TTC (min)", "Closure"]]
    for it in queue:
        a = it["alert"]
        rows.append([str(it["queue_rank"]), it["alert_id"], ", ".join(it["rule_ids"]) or "ML", _fmt(it["p_alert"]), a.get("severity") or "", a.get("category") or "", _fmt(a.get("time_to_close_min"), 0), a.get("closure_reason") or ""])
    if len(rows) == 1:
        rows.append(["", "none", "", "", "", "", "", ""])
    t = Table(rows, colWidths=[10 * mm, 36 * mm, 30 * mm, 10 * mm, 18 * mm, 30 * mm, 18 * mm, 28 * mm], repeatRows=1)
    t.setStyle(GRID)
    story.append(t)

    fb = fetch_df(conn, "SELECT created_at, target_type, target_id, decision, reviewer_id, note FROM feedback WHERE entity_id = ? AND submission_period = ? ORDER BY created_at DESC LIMIT 30", [entity_id, p])
    story.append(_p(f"Supervisor feedback ({len(fb)})", H2))
    rows = [["When", "Target", "Decision", "Reviewer", "Note"]] + [[str(r.created_at)[:16], f"{r.target_type} {str(r.target_id)[:14]}", r.decision, r.reviewer_id, _p(r.note or "", SMALL)] for r in fb.itertuples()]
    if len(rows) == 1:
        rows.append(["", "no feedback recorded", "", "", ""])
    t = Table(rows, colWidths=[26 * mm, 40 * mm, 18 * mm, 24 * mm, 72 * mm], repeatRows=1)
    t.setStyle(GRID)
    story.append(t)
    story += _footer(conn, settings, run_id)
    doc.build(story)
    return path


def period_report(conn: duckdb.DuckDBPyConnection, settings: Settings, period: str) -> Path:
    p, run_id = q.current_run(conn, period)
    if run_id is None:
        raise ValueError("no scored run")
    out_dir = settings.resolve(settings.paths.reports_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"SATSA_portfolio_{p}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title=f"SAT-SA portfolio report {p}")
    s = q.summary(conn, p)
    story = [_p(f"Portfolio supervisory summary: {p}", H1), _p(f"{s['n_entities']} entities scored · {s['n_high_risk']} high or critical · {s['n_open_findings']} open findings · {s['n_uncertain']} uncertain · {s['n_dq_failures']} data-quality failures", SMALL)]
    hm = q.heatmap(conn, p)
    story.append(_p("Entity risk heatmap", H2))
    rows = [["Rank", "Entity", "Sector", "SRI", "Band", "Exec gap", "Neg space", "Escalation", "Investigation", "Data", "Findings", "Uncertain"]]
    for r in hm["rows"]:
        d = r["dims"]
        rows.append([str(r["priority_rank"]), f"{r['entity_id']} {r['name'][:22]}", r["sector"], _fmt(r["sri"], 1), r["band"], _fmt(d.get("execution_gap"), 0), _fmt(d.get("negative_space"), 0), _fmt(d.get("escalation_discipline"), 0), _fmt(d.get("investigation_quality"), 0), _fmt(d.get("data_integrity"), 0), str(r["n_findings"]), str(r["n_manual_review"])])
    t = Table(rows, colWidths=[11 * mm, 44 * mm, 17 * mm, 11 * mm, 18 * mm, 14 * mm, 14 * mm, 15 * mm, 18 * mm, 11 * mm, 14 * mm, 15 * mm], repeatRows=1)
    t.setStyle(GRID)
    story.append(t)
    story.append(_p("Control priorities (expected cost of missed weaknesses, summed over findings)", H2))
    rows = [["Control", "Entity", "Priority", "Findings", "Top rules"]] + [[c["label"], c["entity_id"] or "portfolio", _fmt(c["priority"]), str(c["n_findings"]), ", ".join(c["top_rule_ids"])] for c in q.control_priorities(conn, settings, p)[:20]]
    t = Table(rows, colWidths=[60 * mm, 22 * mm, 18 * mm, 18 * mm, 60 * mm], repeatRows=1)
    t.setStyle(GRID)
    story.append(t)
    story += _footer(conn, settings, run_id)
    doc.build(story)
    return path
