"""Generate alerts, escalations and incidents for one entity-period from its profile."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from simulator.entity_profiles import ANALYSTS, SECTOR_CATEGORY_WEIGHTS, SEVERITY_MIX, EntityProfile
from simulator.note_corpus import free_text_note, template_note

FAST_CLOSE_MAX = {"CRITICAL": 14, "HIGH": 9, "MEDIUM": 4}
TTC_MEDIAN_MIN = {"CRITICAL": 240, "HIGH": 180, "MEDIUM": 90, "LOW": 45, "INFO": 20}
HEALTHY_CLOSURE = [("FALSE_POSITIVE", 0.35), ("BENIGN", 0.25), ("NO_ACTION_REQUIRED", 0.15), ("REMEDIATED", 0.15), ("DUPLICATE", 0.05), ("OTHER", 0.05)]
COLLAPSED_CLOSURE = [("FALSE_POSITIVE", 0.88), ("BENIGN", 0.06), ("NO_ACTION_REQUIRED", 0.04), ("REMEDIATED", 0.02)]


@dataclass
class Asset:
    asset_id: str
    entity_id: str
    criticality_tier: str
    asset_class: str
    expected_telemetry_sources: list[str]
    hostname: str


@dataclass
class PeriodOutput:
    alerts: list[dict] = field(default_factory=list)
    escalations: list[dict] = field(default_factory=list)
    incidents: list[dict] = field(default_factory=list)
    alert_labels: list[dict] = field(default_factory=list)  # (alert_id, injected_pattern)


def _weighted(rnd: random.Random, table: dict[str, float] | list[tuple[str, float]]) -> str:
    items = list(table.items()) if isinstance(table, dict) else table
    keys = [k for k, _ in items]
    weights = [w for _, w in items]
    return rnd.choices(keys, weights=weights, k=1)[0]


def _lognormal_minutes(rng: np.random.Generator, median: float, sigma: float) -> float:
    return float(rng.lognormal(mean=math.log(max(median, 0.5)), sigma=sigma))


def period_bounds(period: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(period + "-01", "%Y-%m-%d")
    nxt = datetime(start.year + (start.month == 12), (start.month % 12) + 1, 1)
    return start, nxt


def _random_ts(rnd: random.Random, start: datetime, end: datetime, burst_days: set[int]) -> datetime:
    n_days = (end - start).days
    day_weights = []
    for d in range(n_days):
        dt = start + timedelta(days=d)
        w = 1.0 if dt.weekday() < 5 else 0.55
        if d in burst_days:
            w *= 3.0
        day_weights.append(w)
    day = rnd.choices(range(n_days), weights=day_weights, k=1)[0]
    hour = rnd.choices(range(24), weights=[0.4] * 7 + [1.0] * 12 + [0.6] * 5, k=1)[0]
    return start + timedelta(days=day, hours=hour, minutes=rnd.randint(0, 59), seconds=rnd.randint(0, 59))


def build_assets(profile: EntityProfile, rnd: random.Random, class_sources: dict[str, list[str]], sector_classes: dict[str, float]) -> list[Asset]:
    assets: list[Asset] = []
    n = profile.n_assets
    n_tier1 = max(3, round(n * 0.15))
    n_tier2 = round(n * 0.30)
    for i in range(n):
        tier = "TIER1" if i < n_tier1 else "TIER2" if i < n_tier1 + n_tier2 else "TIER3"
        cls = _weighted(rnd, sector_classes)
        if tier == "TIER1" and profile.sector in ("power", "oil_gas", "transport") and rnd.random() < 0.6:
            cls = rnd.choice([c for c in ("SCADA", "HMI", "HISTORIAN", "DOMAIN_CONTROLLER") if c in sector_classes])
        assets.append(
            Asset(
                asset_id=f"{profile.entity_id}-A{i + 1:03d}",
                entity_id=profile.entity_id,
                criticality_tier=tier,
                asset_class=cls,
                expected_telemetry_sources=list(class_sources.get(cls, ["syslog"])),
                hostname=f"{cls.lower()}-{i + 1:03d}.{profile.entity_id.lower()}.local",
            )
        )
    return assets


def generate_period(
    profile: EntityProfile,
    period: str,
    period_idx: int,
    assets: list[Asset],
    rnd: random.Random,
    rng: np.random.Generator,
    id_offset: int,
) -> PeriodOutput:
    b = profile.behaviour
    out = PeriodOutput()
    start, end = period_bounds(period)
    period_end = end - timedelta(seconds=1)
    gap_active = profile.profile == "EXEC_GAP" and period_idx >= profile.gap_from_period_idx

    # ---- negative-space shaping of the asset / source / category universe ----
    active_assets = list(assets)
    silent_ids: set[str] = set()
    if b.silent_tier1_count and b.silent_from_period_idx is not None and period_idx >= b.silent_from_period_idx:
        tier1 = [a for a in assets if a.criticality_tier == "TIER1"]
        silent_ids = {a.asset_id for a in tier1[: b.silent_tier1_count]}
        active_assets = [a for a in assets if a.asset_id not in silent_ids]
    dropped: set[str] = set()
    if b.dropped_sources and b.dropped_from_period_idx is not None and period_idx >= b.dropped_from_period_idx:
        dropped = set(b.dropped_sources)
    cat_weights = {k: v for k, v in SECTOR_CATEGORY_WEIGHTS[profile.sector].items() if k not in b.missing_categories}

    # Tier-1 assets are monitored more closely in a healthy SOC.
    asset_weights = [1.6 if a.criticality_tier == "TIER1" else 1.0 for a in active_assets]
    analysts = [f"{profile.entity_id.lower()}-an{i + 1:02d}" for i in range(ANALYSTS[profile.size_band])]
    burst_days = set(rnd.sample(range(1, 27), b.burst_days)) if b.burst_days else set()

    n_alerts = int(rng.poisson(profile.base_volume * (1.0 + 0.6 * b.burst_days / 30)))
    seq = id_offset

    def new_alert_id() -> str:
        nonlocal seq
        seq += 1
        return f"{profile.entity_id}-{period.replace('-', '')}-{seq:05d}"

    def emit(alert: dict, label: str | None) -> None:
        out.alerts.append(alert)
        if label:
            out.alert_labels.append({"alert_id": alert["alert_id"], "entity_id": profile.entity_id, "submission_period": period, "injected_pattern": label})

    for _ in range(n_alerts):
        asset = rnd.choices(active_assets, weights=asset_weights, k=1)[0]
        severity = _weighted(rnd, SEVERITY_MIX)
        category = _weighted(rnd, cat_weights)
        sources = [s for s in asset.expected_telemetry_sources if s not in dropped] or ["syslog"]
        alert = _one_alert(
            profile, period, new_alert_id(), asset, severity, category, rnd.choice(sources), rnd.choice(analysts),
            _random_ts(rnd, start, end, burst_days), period_end, gap_active, rnd, rng, out,
        )
        emit(alert[0], alert[1])

    # EG-07: repeat alerts on the same asset with no remediation.
    if gap_active and b.repeat_no_remediation_assets:
        tier1 = [a for a in active_assets if a.criticality_tier == "TIER1"]
        chosen = rnd.sample(tier1, min(3, len(tier1))) + rnd.sample(active_assets, b.repeat_no_remediation_assets - 3)
        for asset in chosen:
            category = _weighted(rnd, cat_weights)
            for _k in range(4):
                ts = _random_ts(rnd, start, end, set())
                alert = _one_alert(profile, period, new_alert_id(), asset, rnd.choice(["HIGH", "MEDIUM"]), category, asset.expected_telemetry_sources[0], rnd.choice(analysts), ts, period_end, False, rnd, rng, out, force_closure="NO_ACTION_REQUIRED")
                alert[0]["remediation_ticket_id"] = None
                alert[0]["root_cause_flag"] = False
                emit(alert[0], "EG-07")

    # Data-quality injections (E06): unknown assets, bad timestamps, duplicate ids.
    if b.unknown_asset_rate:
        for alert in out.alerts:
            if rnd.random() < b.unknown_asset_rate:
                alert["asset_id"] = f"UNKNOWN-{rnd.randint(100, 999)}"
    if b.bad_timestamp_rate:
        for alert in out.alerts:
            if rnd.random() < b.bad_timestamp_rate:
                alert["timestamp"] = "N/A"
    for _ in range(b.duplicate_ids):
        if out.alerts:
            dup = dict(rnd.choice(out.alerts))
            out.alerts.append(dup)

    return out


def _one_alert(
    profile: EntityProfile, period: str, alert_id: str, asset: Asset, severity: str, category: str, source: str,
    analyst: str, ts: datetime, period_end: datetime, gap_active: bool, rnd: random.Random, rng: np.random.Generator,
    out: PeriodOutput, force_closure: str | None = None,
) -> tuple[dict, str | None]:
    b = profile.behaviour
    rule = f"{category}_r{rnd.randint(1, 4)}"
    label: str | None = None
    alert: dict = {
        "alert_id": alert_id, "entity_id": profile.entity_id, "submission_period": period,
        "timestamp": ts, "severity": severity, "category": category, "asset_id": asset.asset_id,
        "source_system": source, "analyst_id": analyst, "analyst_action": "NONE",
        "acknowledged_at": None, "investigated_at": None, "closed_at": None, "time_to_close_min": None,
        "escalation_flag": False, "escalated_at": None, "closure_reason": None, "investigation_notes": None,
        "root_cause_flag": None, "remediation_ticket_id": None, "rule_name": rule,
    }

    ack = ts + timedelta(minutes=_lognormal_minutes(rng, 15, 0.7))
    if ack > period_end:
        return alert, None  # still unacknowledged at period end
    alert["acknowledged_at"] = ack
    alert["analyst_action"] = "ACKNOWLEDGED"

    # EG-01: acknowledged and then nothing.
    if gap_active and rnd.random() < b.ack_only_rate:
        return alert, "EG-01"

    # EG-02: implausibly fast closure of serious alerts with a template note.
    if gap_active and severity in ("CRITICAL", "HIGH") and rnd.random() < b.fast_close_rate:
        closed = ts + timedelta(minutes=rnd.uniform(1, FAST_CLOSE_MAX[severity]))
        alert.update(
            analyst_action="CLOSED", acknowledged_at=min(ack, closed), closed_at=closed,
            closure_reason=rnd.choice(["FALSE_POSITIVE", "BENIGN"]), investigation_notes=template_note(rnd),
        )
        alert["time_to_close_min"] = round((closed - ts).total_seconds() / 60, 1)
        return alert, "EG-02"

    inv = ack + timedelta(minutes=_lognormal_minutes(rng, 25, 0.6))
    alert["investigated_at"] = inv
    alert["analyst_action"] = "INVESTIGATED"

    # Escalation decision.
    p_esc = {"CRITICAL": b.escalation_rate_critical, "HIGH": b.escalation_rate_high}.get(severity, 0.03)
    escalate = rnd.random() < p_esc
    if gap_active and severity == "CRITICAL" and rnd.random() < b.critical_no_escalation_rate:
        escalate = False
        label = "EG-03"

    ticket: str | None = None
    closure: str
    if escalate:
        esc_at = inv + timedelta(minutes=_lognormal_minutes(rng, 20, 0.5))
        alert.update(escalation_flag=True, escalated_at=esc_at, analyst_action="ESCALATED")
        esc_id = f"{alert_id}-ESC"
        incident_id = f"{alert_id}-INC" if severity == "CRITICAL" and rnd.random() < 0.8 else None
        out.escalations.append({
            "escalation_id": esc_id, "entity_id": profile.entity_id, "alert_id": alert_id, "submission_period": period,
            "raised_at": esc_at, "acknowledged_by_ir_at": esc_at + timedelta(minutes=_lognormal_minutes(rng, 30, 0.5)),
            "incident_id": incident_id, "outcome": rnd.choice(["contained", "false_positive", "monitoring"]),
        })
        if incident_id:
            opened = esc_at + timedelta(minutes=5)
            out.incidents.append({
                "incident_id": incident_id, "entity_id": profile.entity_id, "submission_period": period,
                "opened_at": opened, "closed_at": opened + timedelta(hours=rnd.uniform(4, 72)), "severity": severity,
                "root_cause": rnd.choice(["credential misuse", "unpatched service", "misconfiguration", "phishing", "unknown"]),
                "linked_alert_ids": [alert_id],
            })
        closure = "ESCALATED_TO_IR"
    else:
        table = COLLAPSED_CLOSURE if (gap_active and b.closure_collapse) else HEALTHY_CLOSURE
        closure = force_closure or _weighted(rnd, table)
        if closure == "FALSE_POSITIVE" and not (gap_active and b.closure_collapse) and rnd.random() > b.fp_rate / 0.35 * 0.35 + (b.fp_rate - 0.35):
            pass  # keep sampled closure; fp_rate skew handled below
        if not force_closure and b.fp_rate > 0.35 and closure in ("BENIGN", "NO_ACTION_REQUIRED") and rnd.random() < (b.fp_rate - 0.35):
            closure = "FALSE_POSITIVE"
    if label == "EG-03" and closure in ("REMEDIATED", "ESCALATED_TO_IR"):
        closure = rnd.choice(["BENIGN", "NO_ACTION_REQUIRED"])

    # Closure timing: most alerts close within the period.
    ttc_total = _lognormal_minutes(rng, TTC_MEDIAN_MIN[severity], b.ttc_sigma)
    closed = ts + timedelta(minutes=max(ttc_total, (inv - ts).total_seconds() / 60 + 2))
    if closed <= period_end or rnd.random() < 0.7:
        closed = min(closed, period_end - timedelta(minutes=1)) if closed > period_end else closed
        alert.update(analyst_action="CLOSED", closed_at=closed, closure_reason=closure)
        alert["time_to_close_min"] = round((closed - ts).total_seconds() / 60, 1)
        if closure == "REMEDIATED":
            ticket = f"REM-{rnd.randint(1000, 9999)}" if rnd.random() < 0.7 else None
            alert["remediation_ticket_id"] = ticket
            alert["root_cause_flag"] = rnd.random() < 0.8

    # Notes: template, missing, or genuine free text.
    use_template = (gap_active and rnd.random() < b.template_note_rate) or (not gap_active and rnd.random() < min(b.template_note_rate, 0.15))
    if rnd.random() < b.notes_missing_rate:
        alert["investigation_notes"] = None
    elif use_template:
        alert["investigation_notes"] = template_note(rnd)
        if gap_active and b.template_note_rate >= 0.5:
            label = label or "EG-05"
    else:
        alert["investigation_notes"] = free_text_note(rnd, category=category, asset=asset.hostname, source=source, rule=rule, ticket=ticket)
    return alert, label
