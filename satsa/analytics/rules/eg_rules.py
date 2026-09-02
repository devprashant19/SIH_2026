"""Execution-gap rules EG-01..EG-11."""

from __future__ import annotations

import pandas as pd

from satsa.analytics.rules.base import AlertHit, Rule, RuleContext, RuleResult, score_past
from satsa.features.base import INVESTIGATED_RANK, action_rank, period_bounds
from satsa.features.notes import per_alert_template_similarity

SAMPLE = 200


def _ids(frame: pd.DataFrame, k: int = SAMPLE) -> list[str]:
    return frame["alert_id"].astype(str).head(k).tolist()


class EG01AcknowledgedNotInvestigated(Rule):
    id, scope = "EG-01", "alert"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        a = rc.entity.alerts
        _, period_end = period_bounds(rc.entity.period)
        stale = float(self.p("stale_hours", 72))
        age_h = (period_end - pd.to_datetime(a["acknowledged_at"])).dt.total_seconds() / 3600
        mask = (a["analyst_action"] == "ACKNOWLEDGED") & a["closed_at"].isna() & ~a["escalation_flag"].fillna(False).astype(bool) & (age_h > stale)
        hits = a[mask]
        alert_hits = [AlertHit(str(r.alert_id), {"severity": r.severity, "acknowledged_at": str(r.acknowledged_at), "age_hours": round(float(h), 1)}) for r, h in zip(hits.itertuples(), age_h[mask])]
        n = len(a)
        rate = len(hits) / n if n else 0.0
        if n < int(self.p("min_n", 30)):
            return self.suppressed(rc, "LOW_N", {"n": n})
        thr = float(self.p("entity_rate_threshold", 0.15))
        ev = {"n_hit": len(hits), "n": n, "rate": rate, "peer_rate": rc.peer_median("ack_only_rate"), "stale_hours": stale, "sample_ids": _ids(hits, 5), "features": self.peer_block(rc, "ack_only_rate")}
        return self.result(rc, rate >= thr, score_past(rate, thr), ev, alert_hits)


class EG02FastClosure(Rule):
    id, scope = "EG-02", "alert"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        a = rc.entity.closed
        taus = rc.settings.features.fast_close_minutes
        best = None
        alert_hits: list[AlertHit] = []
        for sev, key in (("CRITICAL", "rate_threshold_critical"), ("HIGH", "rate_threshold_high")):
            sub = a[(a["severity"] == sev) & a["time_to_close_min"].notna() & (a["closure_reason"] != "DUPLICATE")]
            fast = sub[sub["time_to_close_min"] < taus[sev]]
            alert_hits += [AlertHit(str(r.alert_id), {"severity": sev, "ttc_min": float(r.time_to_close_min), "closure_reason": r.closure_reason}) for r in fast.itertuples()]
            feat = f"fast_close_rate_{sev.lower()}"
            if not rc.ok(feat):
                continue
            rate = rc.val(feat)
            thr = float(self.p(key, 0.3))
            s = score_past(rate, thr)
            if best is None or s > best["score"]:
                best = {"score": s, "hit": rate >= thr, "severity": sev, "rate": rate, "tau": taus[sev], "peer_rate": rc.peer_median(feat), "ttc_median": rc.val(f"ttc_median_{sev.lower()}"), "peer_ttc": rc.peer_median(f"ttc_median_{sev.lower()}"), "sample_ids": _ids(fast, 5), "n": len(sub)}
        if best is None:
            return self.suppressed(rc, "LOW_N", {"n": int(rc.n("fast_close_rate_critical"))})
        hit = bool(best.pop("hit"))
        ev = {**best, "features": self.peer_block(rc, "fast_close_rate_critical", "fast_close_rate_high", "ttc_median_critical", "ttc_median_high")}
        return self.result(rc, hit, best["score"], ev, alert_hits)


class EG03CriticalNoEscalation(Rule):
    id, scope = "EG-03", "alert"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        a = rc.entity.closed
        crit = a[a["severity"] == "CRITICAL"]
        hits = crit[~crit["escalation_flag"].fillna(False).astype(bool) & ~crit["closure_reason"].isin(["FALSE_POSITIVE", "DUPLICATE"])]
        alert_hits = [AlertHit(str(r.alert_id), {"category": r.category, "asset_id": r.asset_id, "closure_reason": r.closure_reason, "ttc_min": r.time_to_close_min}) for r in hits.itertuples()]
        if not rc.ok("critical_closed_no_escalation_rate"):
            return self.suppressed(rc, "LOW_N", {"n": len(crit)})
        rate = rc.val("critical_closed_no_escalation_rate")
        thr = float(self.p("rate_threshold", 0.45))
        top = hits["closure_reason"].fillna("UNKNOWN").value_counts()
        ev = {
            "n_hit": len(hits), "n": len(crit), "rate": rate, "top_reason": str(top.idxmax()) if len(top) else "n/a",
            "esc_ratio": rc.val("escalation_ratio_critical"), "peer_esc": rc.peer_median("escalation_ratio_critical"), "sample_ids": _ids(hits, 5),
            "features": self.peer_block(rc, "critical_closed_no_escalation_rate", "escalation_ratio_critical"),
        }
        return self.result(rc, rate >= thr, score_past(rate, thr), ev, alert_hits)


class EG04UniformClosureTimes(Rule):
    id = "EG-04"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        thr = float(self.p("cv_threshold", 0.15))
        for sev, min_key in (("CRITICAL", "min_n_critical"), ("HIGH", "min_n_high")):
            feat = f"ttc_cv_{sev.lower()}"
            if rc.val(feat) is None or rc.n(feat) < int(self.p(min_key, 15)):
                continue
            cv = rc.val(feat)
            ev = {"severity": sev, "cv": cv, "n": rc.n(feat), "p10": rc.val(f"ttc_p10_{sev.lower()}"), "p90": rc.val(f"ttc_p90_{sev.lower()}"), "features": self.peer_block(rc, feat)}
            if cv < thr:
                return self.result(rc, True, score_past(cv, thr, higher_is_worse=False), ev)
        return self.result(rc, False, 0.0, {"features": self.peer_block(rc, "ttc_cv_critical", "ttc_cv_high")})


class EG05TemplateNotes(Rule):
    id, scope = "EG-05", "alert"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        a = rc.entity.alerts
        inv = a[action_rank(a["analyst_action"]) >= INVESTIGATED_RANK]
        sim = per_alert_template_similarity(inv) if len(inv) else pd.Series(dtype=float)
        thr_alert = rc.settings.features.template_cosine_threshold
        hit_rows = inv[sim >= thr_alert] if len(sim) else inv.iloc[0:0]
        alert_hits = [AlertHit(str(r.alert_id), {"cosine": round(float(sim[i]), 3), "note": str(r.investigation_notes)[:120]}) for i, r in zip(hit_rows.index, hit_rows.itertuples())]
        if not rc.ok("note_template_score"):
            return self.suppressed(rc, "LOW_N", {"n": rc.n("note_template_score")})
        score, dup = rc.val("note_template_score"), rc.val("note_dup_cluster_share") or 0.0
        t_score, t_dup = float(self.p("template_score_threshold", 0.8)), float(self.p("dup_cluster_share_threshold", 0.5))
        top = (rc.entity.extras.get("top_template_notes") or [{"note": "", "count": 0}])[0]
        ev = {"score": score, "dup_share": dup, "peer_score": rc.peer_median("note_template_score"), "top_note": top["note"], "top_count": top["count"], "n": rc.n("note_template_score"), "features": self.peer_block(rc, "note_template_score", "note_dup_cluster_share", "note_distinct_ratio")}
        hit = score >= t_score or dup >= t_dup
        return self.result(rc, hit, max(score_past(score, t_score), score_past(dup, t_dup)), ev, alert_hits)


class EG06MissingNotes(Rule):
    id, scope = "EG-06", "alert"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        a = rc.entity.alerts
        inv = a[action_rank(a["analyst_action"]) >= INVESTIGATED_RANK]
        notes = inv["investigation_notes"].fillna("").astype(str).str.strip()
        hits = inv[notes.str.len() < rc.settings.features.min_note_chars]
        alert_hits = [AlertHit(str(r.alert_id), {"analyst_action": r.analyst_action, "severity": r.severity}) for r in hits.itertuples()]
        if not rc.ok("note_missing_rate"):
            return self.suppressed(rc, "LOW_N", {"n": len(inv)})
        rate, thr = rc.val("note_missing_rate"), float(self.p("rate_threshold", 0.3))
        ev = {"rate": rate, "n_hit": len(hits), "n": len(inv), "peer_rate": rc.peer_median("note_missing_rate"), "sample_ids": _ids(hits, 5), "features": self.peer_block(rc, "note_missing_rate")}
        return self.result(rc, rate >= thr, score_past(rate, thr), ev, alert_hits)


class EG07RepeatNoRemediation(Rule):
    id, scope = "EG-07", "asset"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        groups = [g for g in rc.entity.extras.get("repeat_groups", []) if not g.get("addressed")]
        a = rc.entity.alerts
        alert_hits: list[AlertHit] = []
        for g in groups:
            rows = a[(a["asset_id"].astype(str) == g["asset_id"]) & (a["category"] == g["category"])]
            alert_hits += [AlertHit(str(r.alert_id), {"asset_id": g["asset_id"], "category": g["category"], "k": g["k"], "closure_reason": r.closure_reason}) for r in rows.itertuples()]
        if not rc.ok("repeat_no_remediation_rate"):
            return self.suppressed(rc, "LOW_N", {"n": rc.n("repeat_no_remediation_rate")})
        rate, crit = rc.val("repeat_no_remediation_rate"), rc.val("repeat_no_remediation_critical_assets") or 0
        thr, thr_c = float(self.p("rate_threshold", 0.2)), int(self.p("critical_assets_threshold", 2))
        ex = groups[0] if groups else {"asset_id": "n/a", "k": 0, "category": "n/a"}
        reasons = a[(a["asset_id"].astype(str) == ex.get("asset_id")) & (a["category"] == ex.get("category"))]["closure_reason"].fillna("open").value_counts()
        ev = {"n_groups": len(groups), "k_min": self.p("repeat_k", 3), "rate": rate, "peer_rate": rc.peer_median("repeat_no_remediation_rate"), "n_tier1": int(crit), "example_asset": ex["asset_id"], "example_k": ex["k"], "example_category": ex["category"], "example_reason": str(reasons.idxmax()) if len(reasons) else "n/a", "groups": groups[:20], "features": self.peer_block(rc, "repeat_no_remediation_rate", "cross_period_repeat_rate")}
        hit = rate >= thr or crit >= thr_c
        return self.result(rc, hit, max(score_past(rate, thr), score_past(crit, thr_c)), ev, alert_hits)


class EG08ClosureCollapse(Rule):
    id = "EG-08"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        ent, top = rc.val("closure_reason_entropy"), rc.val("closure_reason_top_share")
        fp = rc.val("fp_rate_critical")
        n_closed, n_crit = rc.n("closure_reason_entropy"), rc.n("fp_rate_critical")
        e_thr, s_thr, fp_thr = float(self.p("entropy_threshold", 0.35)), float(self.p("top_share_threshold", 0.8)), float(self.p("fp_rate_critical_threshold", 0.7))
        cond_a = ent is not None and top is not None and n_closed >= int(self.p("min_n_closed", 40)) and ent <= e_thr and top >= s_thr
        cond_b = fp is not None and n_crit >= int(self.p("min_n_critical", 10)) and fp >= fp_thr
        ev = {
            "top_share": top if cond_a else None, "top_reason": rc.entity.extras.get("closure_reason_top"), "entropy": ent, "peer_entropy": rc.peer_median("closure_reason_entropy"),
            "fp_rate_critical": fp if cond_b else None, "peer_fp": rc.peer_median("fp_rate_critical"), "distribution": rc.entity.extras.get("closure_reason_distribution"),
            "features": self.peer_block(rc, "closure_reason_entropy", "closure_reason_top_share", "fp_rate_critical"),
        }
        if n_closed < int(self.p("min_n_closed", 40)) and n_crit < int(self.p("min_n_critical", 10)):
            return self.suppressed(rc, "LOW_N", ev)
        score = max(score_past(ent, e_thr, higher_is_worse=False) if cond_a else 0.0, score_past(fp, fp_thr) if cond_b else 0.0)
        return self.result(rc, cond_a or cond_b, score, ev)


class EG09BatchClosure(Rule):
    id = "EG-09"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        if not rc.ok("batch_close_score") or rc.n("batch_close_score") < int(self.p("min_n_closed", 50)):
            return self.suppressed(rc, "LOW_N", {"n": rc.n("batch_close_score")})
        score, thr = rc.val("batch_close_score"), float(self.p("batch_score_threshold", 0.2))
        closed = rc.entity.closed
        window = rc.settings.features.batch_window_minutes
        bins = pd.to_datetime(closed["closed_at"]).dt.floor(f"{window}min")
        top_bin = bins.value_counts().idxmax()
        inwin = closed[bins == top_bin]
        ev = {"n_window": len(inwin), "share": score, "window": window, "window_start": str(top_bin), "n_analysts": int(inwin["analyst_id"].nunique()), "sample_ids": _ids(inwin, 5), "features": self.peer_block(rc, "batch_close_score")}
        hits = [AlertHit(str(r.alert_id), {"closed_at": str(r.closed_at)}) for r in inwin.itertuples()] if score >= thr else []
        return self.result(rc, score >= thr, score_past(score, thr), ev, hits)


class EG10InvestigatedRateDeficit(Rule):
    id = "EG-10"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        gap, slope = rc.val("aact_inv_gap_30_max"), rc.val("aact_inv_rate_slope_30")
        if gap is None and slope is None:
            return self.suppressed(rc, "LOW_N", {"n": rc.n("aact_inv_gap_30_max")})
        g_thr, s_thr = float(self.p("gap_threshold", 0.2)), float(self.p("slope_threshold_per_day", -0.01))
        cat = rc.entity.extras.get("aact_worst_category")
        detail = (rc.entity.extras.get("aact_category_gaps") or {}).get(cat, {})
        cond_a = gap is not None and gap >= g_thr and detail.get("n", 0) >= int(self.p("min_n_category", 10))
        cond_b = slope is not None and slope <= s_thr
        ev = {"category": cat, "entity_rate": detail.get("entity_rate"), "global_rate": detail.get("global_rate"), "gap": gap, "n": detail.get("n"), "slope": slope if cond_b else None, "slope_per_week": None if slope is None else slope * 7, "features": self.peer_block(rc, "aact_inv_gap_30_max", "aact_inv_gap_30_wmean", "aact_inv_rate_slope_30")}
        score = max(score_past(gap, g_thr) if cond_a else 0.0, score_past(slope, s_thr, higher_is_worse=False) if cond_b else 0.0)
        return self.result(rc, cond_a or cond_b, score, ev)


class EG11EscalatedWithoutRecord(Rule):
    id, scope = "EG-11", "alert"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        wr, link = rc.val("escalation_without_record_rate"), rc.val("incident_link_rate")
        if rc.n("escalation_without_record_rate") < int(self.p("min_n", 5)):
            return self.suppressed(rc, "LOW_N", {"n": rc.n("escalation_without_record_rate")})
        wr_thr, link_thr = float(self.p("without_record_rate_threshold", 0.25)), float(self.p("incident_link_rate_threshold", 0.5))
        cond_a = wr is not None and wr >= wr_thr
        cond_b = link is not None and rc.ok("incident_link_rate") and link <= link_thr
        ids = rc.entity.extras.get("escalated_without_record_alert_ids") or []
        ev = {"without_record_rate": wr if cond_a else None, "n_without": len(ids), "incident_link_rate": link if cond_b else None, "peer_link": rc.peer_median("incident_link_rate"), "sample_ids": ids[:5], "features": self.peer_block(rc, "escalation_without_record_rate", "incident_link_rate")}
        score = max(score_past(wr, wr_thr) if cond_a else 0.0, score_past(link, link_thr, higher_is_worse=False) if cond_b else 0.0)
        return self.result(rc, cond_a or cond_b, score, ev, [AlertHit(i, {}) for i in ids])


EG_RULES = [EG01AcknowledgedNotInvestigated, EG02FastClosure, EG03CriticalNoEscalation, EG04UniformClosureTimes, EG05TemplateNotes, EG06MissingNotes, EG07RepeatNoRemediation, EG08ClosureCollapse, EG09BatchClosure, EG10InvestigatedRateDeficit, EG11EscalatedWithoutRecord]
