"""Controlled vocabularies. Source exports are normalised onto these values by ingest/mapping.py."""

from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

    @property
    def rank(self) -> int:
        return SEVERITY_RANK[self]


SEVERITY_RANK = {Severity.CRITICAL: 4, Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1, Severity.INFO: 0}


class AnalystAction(str, Enum):
    NONE = "NONE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATED = "INVESTIGATED"
    ESCALATED = "ESCALATED"
    CLOSED = "CLOSED"

    @property
    def rank(self) -> int:
        return ACTION_RANK[self]


ACTION_RANK = {
    AnalystAction.NONE: 0,
    AnalystAction.ACKNOWLEDGED: 1,
    AnalystAction.INVESTIGATED: 2,
    AnalystAction.ESCALATED: 3,
    AnalystAction.CLOSED: 4,
}
# Actions that imply a human actually looked at the alert (used by AACT rates and EG-06).
INVESTIGATIVE_ACTIONS = {AnalystAction.INVESTIGATED, AnalystAction.ESCALATED}


class ClosureReason(str, Enum):
    FALSE_POSITIVE = "FALSE_POSITIVE"
    BENIGN = "BENIGN"
    DUPLICATE = "DUPLICATE"
    REMEDIATED = "REMEDIATED"
    NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"
    ESCALATED_TO_IR = "ESCALATED_TO_IR"
    UNKNOWN = "UNKNOWN"
    OTHER = "OTHER"


class Criticality(str, Enum):
    TIER1 = "TIER1"  # most critical
    TIER2 = "TIER2"
    TIER3 = "TIER3"


class AssetClass(str, Enum):
    SCADA = "SCADA"
    HMI = "HMI"
    HISTORIAN = "HISTORIAN"
    DOMAIN_CONTROLLER = "DOMAIN_CONTROLLER"
    DB_SERVER = "DB_SERVER"
    WEB_SERVER = "WEB_SERVER"
    ENDPOINT = "ENDPOINT"
    NETWORK_DEVICE = "NETWORK_DEVICE"
    FIREWALL = "FIREWALL"
    OTHER = "OTHER"


class Category(str, Enum):
    MALWARE = "malware"
    BRUTE_FORCE = "brute_force"
    LATERAL_MOVEMENT = "lateral_movement"
    DATA_EXFIL = "data_exfil"
    PHISHING = "phishing"
    RECON = "recon"
    DOS = "dos"
    INSIDER = "insider"
    POLICY_VIOLATION = "policy_violation"
    CONFIG_CHANGE = "config_change"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    OT_ANOMALY = "ot_anomaly"
    UNKNOWN = "unknown"


class Sector(str, Enum):
    POWER = "power"
    OIL_GAS = "oil_gas"
    TELECOM = "telecom"
    BANKING = "banking"
    TRANSPORT = "transport"
    GOVT = "govt"
    HEALTH = "health"


class SizeBand(str, Enum):
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"


# Aliases seen in real SIEM exports -> canonical values. Extend per source in schema_mappings/*.yaml.
SEVERITY_ALIASES: dict[str, Severity] = {
    "critical": Severity.CRITICAL, "crit": Severity.CRITICAL, "p1": Severity.CRITICAL, "4": Severity.CRITICAL,
    "high": Severity.HIGH, "p2": Severity.HIGH, "3": Severity.HIGH,
    "medium": Severity.MEDIUM, "med": Severity.MEDIUM, "moderate": Severity.MEDIUM, "p3": Severity.MEDIUM, "2": Severity.MEDIUM,
    "low": Severity.LOW, "p4": Severity.LOW, "1": Severity.LOW,
    "info": Severity.INFO, "informational": Severity.INFO, "0": Severity.INFO,
}

CATEGORY_ALIASES: dict[str, Category] = {
    "malware": Category.MALWARE, "virus": Category.MALWARE, "trojan": Category.MALWARE, "ransomware": Category.MALWARE,
    "brute force": Category.BRUTE_FORCE, "brute_force": Category.BRUTE_FORCE, "bruteforce": Category.BRUTE_FORCE,
    "credential access": Category.BRUTE_FORCE, "password spray": Category.BRUTE_FORCE,
    "lateral movement": Category.LATERAL_MOVEMENT, "lateral_movement": Category.LATERAL_MOVEMENT,
    "exfiltration": Category.DATA_EXFIL, "data exfil": Category.DATA_EXFIL, "data_exfil": Category.DATA_EXFIL,
    "phishing": Category.PHISHING, "spam": Category.PHISHING,
    "recon": Category.RECON, "reconnaissance": Category.RECON, "scan": Category.RECON, "port scan": Category.RECON,
    "dos": Category.DOS, "ddos": Category.DOS, "denial of service": Category.DOS,
    "insider": Category.INSIDER, "insider threat": Category.INSIDER,
    "policy violation": Category.POLICY_VIOLATION, "policy_violation": Category.POLICY_VIOLATION, "policy": Category.POLICY_VIOLATION,
    "config change": Category.CONFIG_CHANGE, "config_change": Category.CONFIG_CHANGE, "configuration change": Category.CONFIG_CHANGE,
    "privilege escalation": Category.PRIVILEGE_ESCALATION, "privilege_escalation": Category.PRIVILEGE_ESCALATION, "privesc": Category.PRIVILEGE_ESCALATION,
    "ot anomaly": Category.OT_ANOMALY, "ot_anomaly": Category.OT_ANOMALY, "ics anomaly": Category.OT_ANOMALY, "ot": Category.OT_ANOMALY,
}

ACTION_ALIASES: dict[str, AnalystAction] = {
    "none": AnalystAction.NONE, "new": AnalystAction.NONE, "open": AnalystAction.NONE, "": AnalystAction.NONE,
    "acknowledged": AnalystAction.ACKNOWLEDGED, "ack": AnalystAction.ACKNOWLEDGED, "assigned": AnalystAction.ACKNOWLEDGED,
    "investigated": AnalystAction.INVESTIGATED, "investigating": AnalystAction.INVESTIGATED, "in progress": AnalystAction.INVESTIGATED,
    "escalated": AnalystAction.ESCALATED,
    "closed": AnalystAction.CLOSED, "resolved": AnalystAction.CLOSED, "done": AnalystAction.CLOSED,
}

CLOSURE_ALIASES: dict[str, ClosureReason] = {
    "false positive": ClosureReason.FALSE_POSITIVE, "false_positive": ClosureReason.FALSE_POSITIVE, "fp": ClosureReason.FALSE_POSITIVE,
    "benign": ClosureReason.BENIGN, "benign positive": ClosureReason.BENIGN, "expected": ClosureReason.BENIGN,
    "duplicate": ClosureReason.DUPLICATE, "dup": ClosureReason.DUPLICATE,
    "remediated": ClosureReason.REMEDIATED, "fixed": ClosureReason.REMEDIATED, "contained": ClosureReason.REMEDIATED, "true positive": ClosureReason.REMEDIATED,
    "no action required": ClosureReason.NO_ACTION_REQUIRED, "no_action_required": ClosureReason.NO_ACTION_REQUIRED, "no action": ClosureReason.NO_ACTION_REQUIRED,
    "escalated to ir": ClosureReason.ESCALATED_TO_IR, "escalated_to_ir": ClosureReason.ESCALATED_TO_IR, "escalated": ClosureReason.ESCALATED_TO_IR,
    "unknown": ClosureReason.UNKNOWN, "": ClosureReason.UNKNOWN,
    "other": ClosureReason.OTHER,
}


def normalise(value: object, aliases: dict[str, Enum], default: Enum) -> Enum:
    """Map a raw export value onto an enum via the alias table (case/whitespace-insensitive)."""
    if value is None:
        return default
    key = str(value).strip().lower()
    if key in aliases:
        return aliases[key]
    # already canonical?
    enum_cls = type(default)
    for member in enum_cls:
        if key == member.value.lower():
            return member
    return default
