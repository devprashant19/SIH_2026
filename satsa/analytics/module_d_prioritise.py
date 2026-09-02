"""Module D: cost-sensitive decisions, ranking, and the stratified alert-sample review queue."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from satsa.config import Settings

AUTO_FLAG, MANUAL_REVIEW, AUTO_CLEAR = "AUTO_FLAG", "MANUAL_REVIEW", "AUTO_CLEAR"


def decide(p: float, t_star: float, delta: float) -> str:
    if p >= t_star + delta:
        return AUTO_FLAG
    if p <= t_star - delta:
        return AUTO_CLEAR
    return MANUAL_REVIEW


def apply_decisions(findings: list[dict[str, Any]], settings: Settings) -> None:
    for f in findings:
        cls = f["finding_class"]
        t, d = settings.t_star(cls), settings.band_halfwidth(cls)
        _, c_fn = settings.cost(cls)
        f["t_star"], f["band_low"], f["band_high"] = t, max(0.0, t - d), min(1.0, t + d)
        f["decision"] = decide(f["p_final"], t, d)
        f["expected_cost"] = f["p_final"] * c_fn
    # Uncertain findings first (they need a human), then by expected cost of missing them.
    order = {MANUAL_REVIEW: 0, AUTO_FLAG: 1, AUTO_CLEAR: 2}
    for rank, f in enumerate(sorted(findings, key=lambda x: (order[x["decision"]], -x["expected_cost"])), start=1):
        f["priority_rank"] = rank


def build_review_queue(flags: list[dict[str, Any]], settings: Settings) -> None:
    """Decide each alert flag, then rank per entity with round-robin over rule ids so the
    sample covers every kind of weakness rather than one dominant rule."""
    t, d = settings.t_star("alert_sample"), settings.band_halfwidth("alert_sample")
    budget = settings.pipeline.review_budget_per_entity
    for fl in flags:
        fl["decision"] = decide(fl["p_alert"], t, d)
    by_entity: dict[str, list[dict]] = defaultdict(list)
    for fl in flags:
        if fl["decision"] != AUTO_CLEAR:
            by_entity[fl["entity_id"]].append(fl)
    for eid, items in by_entity.items():
        buckets: dict[str, list[dict]] = defaultdict(list)
        for fl in sorted(items, key=lambda x: (x["decision"] != MANUAL_REVIEW, -x["p_alert"])):
            buckets[fl["rule_ids"][0] if fl["rule_ids"] else "ML"].append(fl)
        rank, keys = 1, sorted(buckets)
        while rank <= budget and any(buckets.values()):
            for k in keys:
                if buckets[k] and rank <= budget:
                    fl = buckets[k].pop(0)
                    fl["queue_rank"] = rank
                    why = "uncertain, needs a decision" if fl["decision"] == MANUAL_REVIEW else "high probability"
                    fl["queue_reason"] = f"rank {rank} for {eid}: {why} ({k})"
                    rank += 1


def control_priorities(findings: list[dict[str, Any]], settings: Settings) -> list[dict[str, Any]]:
    """Expected cost aggregated per control, per entity and across the portfolio."""
    labels = settings.rules.get("controls") or {}
    agg: dict[tuple[str | None, str], dict[str, Any]] = {}
    for f in findings:
        if not f.get("rule_id"):
            continue
        for key in ((f["entity_id"], f["control_id"]), (None, f["control_id"])):
            a = agg.setdefault(key, {"entity_id": key[0], "control_id": key[1], "label": labels.get(key[1], key[1]), "priority": 0.0, "n_findings": 0, "rules": defaultdict(float)})
            a["priority"] += f.get("expected_cost") or 0.0
            a["n_findings"] += 1
            a["rules"][f["rule_id"]] += f.get("expected_cost") or 0.0
    out = []
    for a in agg.values():
        rules = sorted(a.pop("rules").items(), key=lambda kv: -kv[1])
        out.append({**a, "top_rule_ids": [r for r, _ in rules[:3]]})
    return sorted(out, key=lambda x: -x["priority"])
