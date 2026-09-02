"""The eight synthetic Critical Sector Entities and the behaviours injected into each.

Profiles map directly onto the validation plan: two healthy, two execution-gap, two
negative-space, and two noisy controls that must NOT be flagged. Every injected behaviour
names the rule it is meant to trigger so ground truth can be written alongside the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PERIODS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]

BASE_VOLUME = {"S": 120, "M": 200, "L": 300, "XL": 420}
ASSET_COUNT = {"S": 25, "M": 45, "L": 70, "XL": 110}
ANALYSTS = {"S": 3, "M": 5, "L": 7, "XL": 10}

SECTOR_ASSET_CLASSES: dict[str, dict[str, float]] = {
    "power": {"SCADA": 0.18, "HMI": 0.12, "HISTORIAN": 0.06, "DOMAIN_CONTROLLER": 0.05, "DB_SERVER": 0.08, "WEB_SERVER": 0.06, "ENDPOINT": 0.25, "NETWORK_DEVICE": 0.12, "FIREWALL": 0.08},
    "oil_gas": {"SCADA": 0.20, "HMI": 0.12, "HISTORIAN": 0.06, "DOMAIN_CONTROLLER": 0.05, "DB_SERVER": 0.07, "WEB_SERVER": 0.05, "ENDPOINT": 0.25, "NETWORK_DEVICE": 0.12, "FIREWALL": 0.08},
    "telecom": {"DOMAIN_CONTROLLER": 0.06, "DB_SERVER": 0.12, "WEB_SERVER": 0.14, "ENDPOINT": 0.28, "NETWORK_DEVICE": 0.30, "FIREWALL": 0.10},
    "banking": {"DOMAIN_CONTROLLER": 0.08, "DB_SERVER": 0.18, "WEB_SERVER": 0.16, "ENDPOINT": 0.38, "NETWORK_DEVICE": 0.12, "FIREWALL": 0.08},
    "transport": {"SCADA": 0.10, "HMI": 0.08, "DOMAIN_CONTROLLER": 0.06, "DB_SERVER": 0.10, "WEB_SERVER": 0.10, "ENDPOINT": 0.34, "NETWORK_DEVICE": 0.14, "FIREWALL": 0.08},
    "govt": {"DOMAIN_CONTROLLER": 0.08, "DB_SERVER": 0.14, "WEB_SERVER": 0.16, "ENDPOINT": 0.42, "NETWORK_DEVICE": 0.12, "FIREWALL": 0.08},
    "health": {"DOMAIN_CONTROLLER": 0.06, "DB_SERVER": 0.16, "WEB_SERVER": 0.12, "ENDPOINT": 0.46, "NETWORK_DEVICE": 0.12, "FIREWALL": 0.08},
}

SECTOR_CATEGORY_WEIGHTS: dict[str, dict[str, float]] = {
    "power": {"malware": 0.16, "brute_force": 0.12, "lateral_movement": 0.07, "data_exfil": 0.05, "phishing": 0.14, "recon": 0.12, "privilege_escalation": 0.05, "ot_anomaly": 0.12, "config_change": 0.10, "policy_violation": 0.05, "dos": 0.02},
    "oil_gas": {"malware": 0.16, "brute_force": 0.12, "lateral_movement": 0.07, "data_exfil": 0.05, "phishing": 0.13, "recon": 0.12, "privilege_escalation": 0.05, "ot_anomaly": 0.13, "config_change": 0.10, "policy_violation": 0.05, "dos": 0.02},
    "telecom": {"malware": 0.16, "brute_force": 0.14, "lateral_movement": 0.07, "data_exfil": 0.06, "phishing": 0.12, "recon": 0.14, "dos": 0.10, "privilege_escalation": 0.06, "config_change": 0.10, "policy_violation": 0.05},
    "banking": {"malware": 0.16, "brute_force": 0.15, "lateral_movement": 0.07, "data_exfil": 0.07, "phishing": 0.16, "recon": 0.10, "dos": 0.05, "insider": 0.06, "privilege_escalation": 0.06, "policy_violation": 0.12},
    "transport": {"malware": 0.17, "brute_force": 0.13, "lateral_movement": 0.07, "data_exfil": 0.05, "phishing": 0.15, "recon": 0.13, "privilege_escalation": 0.05, "ot_anomaly": 0.08, "config_change": 0.12, "policy_violation": 0.05},
    "govt": {"malware": 0.18, "brute_force": 0.14, "lateral_movement": 0.06, "data_exfil": 0.06, "phishing": 0.18, "recon": 0.10, "insider": 0.06, "privilege_escalation": 0.06, "policy_violation": 0.16},
    "health": {"malware": 0.18, "brute_force": 0.13, "lateral_movement": 0.06, "data_exfil": 0.07, "phishing": 0.18, "recon": 0.10, "insider": 0.06, "privilege_escalation": 0.06, "policy_violation": 0.16},
}

SEVERITY_MIX = {"CRITICAL": 0.05, "HIGH": 0.15, "MEDIUM": 0.40, "LOW": 0.33, "INFO": 0.07}


@dataclass
class Behaviour:
    """Knobs the alert factory reads. Defaults describe a healthy SOC."""

    volume_factor: float = 1.0
    # workflow
    ack_only_rate: float = 0.02            # EG-01 when high
    fast_close_rate: float = 0.03          # EG-02 when high (applies to CRITICAL/HIGH)
    critical_no_escalation_rate: float = 0.12  # EG-03 when high
    template_note_rate: float = 0.08       # EG-05 when high
    notes_missing_rate: float = 0.04       # EG-06 / V-12 when high
    closure_collapse: bool = False         # EG-08: most closures share one reason
    repeat_no_remediation_assets: int = 0  # EG-07: assets with k>=3 unremediated repeats
    escalation_rate_critical: float = 0.75
    escalation_rate_high: float = 0.30
    fp_rate: float = 0.35
    ttc_sigma: float = 0.6                 # lognormal spread of closure times
    burst_days: int = 0                    # legitimate activity bursts (noisy control)
    # negative space
    silent_tier1_count: int = 0            # NS-01: tier-1 assets that go quiet
    silent_from_period_idx: int | None = None
    dropped_sources: tuple[str, ...] = ()  # NS-02
    dropped_from_period_idx: int | None = None
    missing_categories: tuple[str, ...] = ()  # NS-03
    # data quality
    unknown_asset_rate: float = 0.0        # V-07
    bad_timestamp_rate: float = 0.0        # V-02
    duplicate_ids: int = 0                 # V-09


@dataclass
class EntityProfile:
    entity_id: str
    name: str
    sector: str
    size_band: str
    soc_tier: int
    profile: str  # HEALTHY | EXEC_GAP | NEG_SPACE | NOISY
    export_format: str  # csv | json | sqlite
    behaviour: Behaviour = field(default_factory=Behaviour)
    gap_from_period_idx: int = 0  # index in PERIODS from which execution-gap behaviour starts
    expected_rules: tuple[str, ...] = ()  # rules that should fire in affected periods

    @property
    def n_assets(self) -> int:
        return ASSET_COUNT[self.size_band]

    @property
    def base_volume(self) -> int:
        return int(BASE_VOLUME[self.size_band] * self.behaviour.volume_factor)

    def affected(self, period_idx: int) -> bool:
        if self.profile == "EXEC_GAP":
            return period_idx >= self.gap_from_period_idx
        if self.profile == "NEG_SPACE":
            b = self.behaviour
            starts = [i for i in (b.silent_from_period_idx, b.dropped_from_period_idx) if i is not None]
            if b.missing_categories or b.volume_factor < 0.8 or b.unknown_asset_rate > 0:
                return True
            return bool(starts) and period_idx >= min(starts)
        return False


def default_profiles() -> list[EntityProfile]:
    return [
        EntityProfile("E01", "Northern Grid Transmission", "power", "L", 2, "HEALTHY", "csv"),
        EntityProfile("E02", "Meridian Cooperative Bank", "banking", "M", 2, "HEALTHY", "csv"),
        EntityProfile(
            "E03", "Sagar Telecom Services", "telecom", "L", 3, "EXEC_GAP", "csv",
            behaviour=Behaviour(fast_close_rate=0.45, template_note_rate=0.85, critical_no_escalation_rate=0.55, escalation_rate_critical=0.30, ttc_sigma=0.4),
            gap_from_period_idx=2,
            expected_rules=("EG-02", "EG-03", "EG-05"),
        ),
        EntityProfile(
            "E04", "Continental Payments Corp", "banking", "XL", 3, "EXEC_GAP", "csv",
            behaviour=Behaviour(ack_only_rate=0.28, repeat_no_remediation_assets=14, closure_collapse=True, fp_rate=0.85),
            gap_from_period_idx=0,
            expected_rules=("EG-01", "EG-07", "EG-08"),
        ),
        EntityProfile(
            "E05", "Western Power Generation", "power", "XL", 2, "NEG_SPACE", "json",
            behaviour=Behaviour(silent_tier1_count=6, silent_from_period_idx=3, dropped_sources=("ot_ids",), dropped_from_period_idx=3),
            expected_rules=("NS-01", "NS-02"),
        ),
        EntityProfile(
            "E06", "Coastal Refining Ltd", "oil_gas", "M", 2, "NEG_SPACE", "json",
            behaviour=Behaviour(volume_factor=0.55, missing_categories=("lateral_movement", "data_exfil"), unknown_asset_rate=0.22, notes_missing_rate=0.38, bad_timestamp_rate=0.01, duplicate_ids=3),
            expected_rules=("NS-03", "NS-04", "NS-06", "EG-06"),
        ),
        EntityProfile(
            "E07", "State Revenue Department", "govt", "L", 2, "NOISY", "sqlite",
            behaviour=Behaviour(volume_factor=1.8, fp_rate=0.65, template_note_rate=0.15),
        ),
        EntityProfile(
            "E08", "Metro Rail Authority", "transport", "S", 1, "NOISY", "sqlite",
            behaviour=Behaviour(ttc_sigma=1.3, burst_days=2, notes_missing_rate=0.12),
        ),
    ]
