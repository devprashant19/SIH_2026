"""Negative-space rules NS-01..NS-08. Module B supplies peer context through rc.aux:
   aux["peer_category_share"]  {category: share of peers reporting it}
   aux["expected_volume"]      {actual, predicted, sigma, z, inputs}
   aux["peer_class_rates"]     {asset_class: median alerts per asset across peers}
"""

from __future__ import annotations

from satsa.analytics.rules.base import Rule, RuleContext, RuleResult, score_past


class NS01SilentCriticalAssets(Rule):
    id, scope = "NS-01", "asset"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        n_t1 = rc.n("silent_asset_rate_tier1")
        if n_t1 < int(self.p("min_tier1_assets", 3)):
            return self.suppressed(rc, "LOW_N", {"n_tier1": n_t1})
        hist, now = rc.val("silent_asset_rate_tier1_hist"), rc.val("silent_asset_rate_tier1") or 0.0
        h_thr, n_thr = float(self.p("newly_silent_rate_threshold", 0.2)), float(self.p("silent_rate_threshold", 0.4))
        silent = rc.entity.extras.get("silent_tier1_assets") or []
        newly = rc.entity.extras.get("newly_silent_tier1_assets") or []
        cond_a = hist is not None and hist >= h_thr
        cond_b = now >= n_thr
        ev = {"n_silent": len(silent), "n_tier1": n_t1, "n_new": len(newly), "example_asset": (newly or silent or ["n/a"])[0], "rate": hist if cond_a else now, "peer_rate": rc.peer_median("silent_asset_rate_tier1_hist" if cond_a else "silent_asset_rate_tier1"), "silent_assets": silent, "newly_silent_assets": newly, "features": self.peer_block(rc, "silent_asset_rate_tier1", "silent_asset_rate_tier1_hist")}
        score = max(score_past(hist, h_thr) if cond_a else 0.0, score_past(now, n_thr) if cond_b else 0.0)
        return self.result(rc, cond_a or cond_b, score, ev)


class NS02TelemetryCoverageGap(Rule):
    id = "NS-02"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        gap = rc.val("coverage_gap_score_tier1")
        g_thr = float(self.p("coverage_gap_tier1_threshold", 0.25))
        ex = rc.entity.extras
        counts, expected = ex.get("dropped_source_asset_counts") or {}, ex.get("dropped_source_expected_alerts") or {}
        min_assets, min_expected = int(self.p("min_assets_declaring_dropped_source", 3)), float(self.p("min_expected_alerts_dropped_source", 5))
        significant = [s for s in ex.get("dropped_sources") or [] if counts.get(s, 0) >= min_assets and expected.get(s, 0) >= min_expected]
        cond_a = gap is not None and gap >= g_thr
        cond_b = len(significant) >= int(self.p("source_dropout_threshold", 1))
        exp_total = sum(expected.get(s, 0) for s in significant)
        ev = {"gap_tier1": gap if cond_a else None, "missing": ex.get("missing_sources") or [], "dropped": significant, "n_declaring": sum(counts.get(s, 0) for s in significant), "expected_alerts": exp_total, "dropped_assets": {s: (ex.get("dropped_source_assets") or {}).get(s, []) for s in significant}, "features": self.peer_block(rc, "coverage_gap_score_tier1", "coverage_gap_score", "source_dropout_count")}
        if gap is None and not ex.get("dropped_sources"):
            return self.suppressed(rc, "MISSING", ev)
        drop_score = min(1.0, 0.5 + 0.05 * exp_total) if cond_b else 0.0
        return self.result(rc, cond_a or cond_b, max(score_past(gap, g_thr) if cond_a else 0.0, drop_score), ev)


class NS03ExpectedCategoryAbsent(Rule):
    id = "NS-03"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        cfg = rc.settings.expected_categories
        sector = str(rc.entity.entity.get("sector"))
        expected: set[str] = set(cfg.get("by_sector", {}).get(sector, []))
        classes = set(rc.entity.assets["asset_class"].astype(str)) if len(rc.entity.assets) else set()
        for c in classes:
            expected |= set(cfg.get("by_asset_class", {}).get(c, []))
        peer_share: dict[str, float] = rc.aux.get("peer_category_share") or {}
        expected |= {c for c, s in peer_share.items() if s >= float(self.p("peer_share_expected", 0.6))}
        observed = set(rc.entity.extras.get("observed_categories") or [])
        missing = sorted(expected - observed)
        importance = cfg.get("importance") or {}
        denom = sum(importance.get(c, 0.5) for c in expected) or 1.0
        score = sum(importance.get(c, 0.5) for c in missing) / denom
        prev = [set(rc.entity.history_for(p)["category"].dropna().astype(str)) for p in rc.entity.prior_periods[-3:]]
        newly = sorted(c for c in missing if sum(c in s for s in prev) >= 2)
        thr = float(self.p("weighted_score_threshold", 0.25))
        cond = (len(missing) >= int(self.p("min_missing", 2)) and score >= thr) or bool(newly)
        ev = {"missing": missing, "newly_missing": newly, "score": score, "sector": sector, "peer_share": (sum(peer_share.get(c, 0) for c in missing) / len(missing)) if missing else None, "expected": sorted(expected), "observed": sorted(observed)}
        if rc.n("n_alerts") == 0:
            return self.suppressed(rc, "MISSING", ev)
        return self.result(rc, cond, max(score_past(score, thr), 0.6 if newly else 0.0), ev)


class NS04VolumeBelowExpectation(Rule):
    id = "NS-04"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        ev_in = rc.aux.get("expected_volume") or {}
        pred, z = ev_in.get("predicted"), ev_in.get("z")
        if pred is None or z is None or pred < float(self.p("min_predicted", 20)):
            return self.suppressed(rc, "LOW_N", ev_in)
        k = float(self.p("sigma_threshold", 1.2))
        ev = {**ev_in, "z": z, "size_band": rc.entity.entity.get("size_band"), "sector": rc.entity.entity.get("sector"), "n_assets": rc.entity.entity.get("documented_asset_count"), "features": self.peer_block(rc, "alerts_per_documented_asset", "n_alerts")}
        return self.result(rc, z <= -k, score_past(-z, k), ev)


class NS05DropVersusHistory(Rule):
    id = "NS-05"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        delta, zs = rc.val("volume_delta_pct"), rc.val("volume_z_vs_self")
        prev_counts = rc.entity.extras.get("prior_period_counts") or {}
        n_prev = list(prev_counts.values())[-1] if prev_counts else 0
        if delta is None:
            return self.suppressed(rc, "MISSING", {"prior_period_counts": prev_counts})
        d_thr, z_thr = float(self.p("delta_pct_threshold", -0.4)), float(self.p("z_self_threshold", -2.0))
        cond_a = delta <= d_thr and n_prev >= int(self.p("min_n_prev", 50))
        cond_b = zs is not None and zs <= z_thr and delta <= float(self.p("min_delta_for_z", -0.15))
        cur = rc.entity.extras.get("category_counts") or {}
        prev_period = list(prev_counts)[-1] if prev_counts else None
        prev_cats = rc.entity.history_for(prev_period)["category"].value_counts().to_dict() if prev_period else {}
        drops = sorted(((c, prev_cats.get(c, 0) - cur.get(c, 0)) for c in set(prev_cats) | set(cur)), key=lambda kv: -kv[1])[:3]
        ev = {"delta": delta, "prev": n_prev, "current": rc.n("n_alerts"), "z_self": zs if cond_b else None, "top_drops": [f"{c} (-{d})" for c, d in drops if d > 0], "features": self.peer_block(rc, "volume_delta_pct", "volume_z_vs_self")}
        score = max(score_past(delta, d_thr, higher_is_worse=False) if cond_a else 0.0, score_past(zs, z_thr, higher_is_worse=False) if cond_b else 0.0)
        return self.result(rc, cond_a or cond_b, score, ev)


class NS06BrokenSubmission(Rule):
    id = "NS-06"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        n = rc.n("n_alerts")
        err, notes, unk = rc.val("val_err_rate") or 0.0, rc.val("val_missing_notes_rate") or 0.0, rc.val("unknown_asset_alert_rate") or 0.0
        e_thr, n_thr, u_thr = float(self.p("val_err_rate_threshold", 0.1)), float(self.p("missing_notes_rate_threshold", 0.3)), float(self.p("unknown_asset_rate_threshold", 0.2))
        problems, score = [], 0.0
        if n == 0:
            problems.append("contains no alert rows")
            score = 1.0
        if err >= e_thr:
            problems.append(f"has {err:.0%} of rows with validation errors")
            score = max(score, score_past(err, e_thr))
        if notes >= n_thr:
            problems.append(f"lacks investigation notes on {notes:.0%} of rows")
            score = max(score, score_past(notes, n_thr))
        if unk >= u_thr:
            problems.append(f"references assets outside the inventory on {unk:.0%} of rows")
            score = max(score, score_past(unk, u_thr))
        v = rc.entity.validation
        details = f"n_rows={v.get('n_rows', 0)}, errors={v.get('ERROR', 0)}, warnings={v.get('WARN', 0)}, V-07={v.get('V-07', 0)}, V-12={v.get('V-12', 0)}"
        ev = {"problem": "; ".join(problems) if problems else "is clean", "details": details, "validation": v, "features": self.peer_block(rc, "val_err_rate", "val_warn_rate", "unknown_asset_alert_rate", "val_missing_notes_rate")}
        return self.result(rc, bool(problems), score, ev)


class NS07BlindSpotByAssetClass(Rule):
    id = "NS-07"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        per_class = rc.entity.extras.get("alerts_per_asset_by_class") or {}
        peer = rc.aux.get("peer_class_rates") or {}
        ratio_thr, min_assets, min_peer = float(self.p("ratio_to_peer_threshold", 0.2)), int(self.p("min_assets_in_class", 3)), float(self.p("min_peer_median", 2.0))
        worst = None
        for cls, info in per_class.items():
            pm = peer.get(cls)
            if info["n_assets"] < min_assets or pm is None or pm < min_peer:
                continue
            ratio = info["alerts_per_asset"] / pm
            if worst is None or ratio < worst["ratio"]:
                worst = {"asset_class": cls, "n_assets": info["n_assets"], "rate": info["alerts_per_asset"], "peer_rate": pm, "ratio": ratio}
        if worst is None:
            return self.suppressed(rc, "LOW_N", {"classes": list(per_class)})
        hit = worst["ratio"] < ratio_thr
        ev = {**worst, "classes": per_class, "peer_class_rates": peer}
        return self.result(rc, hit, score_past(worst["ratio"], ratio_thr, higher_is_worse=False), ev)


class NS08CriticalUnderMonitoring(Rule):
    id = "NS-08"

    def evaluate(self, rc: RuleContext) -> RuleResult:
        ratio = rc.val("criticality_volume_ratio")
        if ratio is None or rc.n("alerts_per_asset_tier1") < int(self.p("min_tier1_assets", 3)):
            return self.suppressed(rc, "LOW_N", {"n_tier1": rc.n("alerts_per_asset_tier1")})
        thr = float(self.p("criticality_volume_ratio_threshold", 0.5))
        ev = {"r1": rc.val("alerts_per_asset_tier1"), "r3": rc.val("alerts_per_asset_tier3"), "ratio": ratio, "peer_ratio": rc.peer_median("criticality_volume_ratio"), "features": self.peer_block(rc, "criticality_volume_ratio", "alerts_per_asset_tier1", "alerts_per_asset_tier3")}
        return self.result(rc, ratio < thr, score_past(ratio, thr, higher_is_worse=False), ev)


NS_RULES = [NS01SilentCriticalAssets, NS02TelemetryCoverageGap, NS03ExpectedCategoryAbsent, NS04VolumeBelowExpectation, NS05DropVersusHistory, NS06BrokenSubmission, NS07BlindSpotByAssetClass, NS08CriticalUnderMonitoring]
