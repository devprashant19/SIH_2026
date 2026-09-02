"""Plain-language rationale templates, one per rule. Rendered with the rule's evidence dict."""

from __future__ import annotations

from typing import Any

from jinja2 import Environment


def _pct(v: Any, digits: int = 0) -> str:
    return "n/a" if v is None else f"{float(v) * 100:.{digits}f}%"


def _num(v: Any, digits: int = 1) -> str:
    return "n/a" if v is None else f"{float(v):,.{digits}f}"


def _minutes(v: Any) -> str:
    if v is None:
        return "n/a"
    v = float(v)
    if v < 60:
        return f"{v:.0f} min"
    if v < 1440:
        return f"{v / 60:.1f} h"
    return f"{v / 1440:.1f} days"


def _join(items: Any, k: int = 5) -> str:
    items = list(items or [])
    if not items:
        return "none"
    shown = ", ".join(str(i) for i in items[:k])
    return shown + (f" (+{len(items) - k} more)" if len(items) > k else "")


ENV = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)
ENV.filters.update({"pct": _pct, "num": _num, "minutes": _minutes, "join_k": _join})

TEMPLATES: dict[str, str] = {
    "EG-01": (
        "{{ n_hit }} of {{ n }} alerts ({{ rate|pct }}) were acknowledged but show no investigation, escalation or closure "
        "after {{ stale_hours }} hours. The peer median is {{ peer_rate|pct }}. Sample alerts: {{ sample_ids|join_k }}."
    ),
    "EG-02": (
        "{{ rate|pct }} of {{ severity|lower }} alerts were closed within {{ tau|num(0) }} minutes against a peer median of {{ peer_rate|pct }}. "
        "Median closure time for {{ severity|lower }} alerts was {{ ttc_median|minutes }} (peer median {{ peer_ttc|minutes }}). "
        "Sample alerts: {{ sample_ids|join_k }}."
    ),
    "EG-03": (
        "{{ n_hit }} of {{ n }} closed critical alerts ({{ rate|pct }}) were closed without escalation, most often as '{{ top_reason }}'. "
        "The critical escalation ratio is {{ esc_ratio|pct }} against a peer median of {{ peer_esc|pct }}. "
        "Sample alerts: {{ sample_ids|join_k }}."
    ),
    "EG-04": (
        "Closure times for {{ severity|lower }} alerts are unusually uniform (coefficient of variation {{ cv|num(2) }}; "
        "P10 to P90 {{ p10|minutes }} to {{ p90|minutes }} over {{ n }} closures), which is characteristic of scripted or template closures."
    ),
    "EG-05": (
        "{{ dup_share|pct }} of investigation notes are near-duplicates and the templating score is {{ score|num(2) }} "
        "(peer median {{ peer_score|num(2) }}). The most repeated note appears {{ top_count }} times: \"{{ top_note }}\"."
    ),
    "EG-06": (
        "{{ rate|pct }} of alerts marked investigated, escalated or closed carry no substantive investigation note "
        "(peer median {{ peer_rate|pct }}); {{ n_hit }} of {{ n }} such alerts. Sample alerts: {{ sample_ids|join_k }}."
    ),
    "EG-07": (
        "{{ n_groups }} asset/category pairs raised {{ k_min }} or more alerts this period that were neither dismissed as "
        "false positives nor remediated ({{ rate|pct }} of repeat groups; peer median {{ peer_rate|pct }}), including "
        "{{ n_tier1 }} Tier-1 assets. Example: {{ example_asset }} raised {{ example_k }} '{{ example_category }}' alerts closed as "
        "'{{ example_reason }}'."
    ),
    "EG-08": (
        "{% if top_share is not none %}{{ top_share|pct }} of closures use the single reason '{{ top_reason }}' "
        "(closure-reason diversity {{ entropy|num(2) }}, peer median {{ peer_entropy|num(2) }}). {% endif %}"
        "{% if fp_rate_critical is not none %}{{ fp_rate_critical|pct }} of critical alerts were closed as false positives "
        "(peer median {{ peer_fp|pct }}). {% endif %}This pattern satisfies closure metrics without demonstrating risk reduction."
    ),
    "EG-09": (
        "{{ n_window }} alerts ({{ share|pct }} of the period's closures) were closed inside a single {{ window }}-minute window "
        "starting {{ window_start }}, involving {{ n_analysts }} analyst(s)."
    ),
    "EG-10": (
        "Only {{ entity_rate|pct }} of '{{ category }}' alerts were investigated over the trailing 30 days, against {{ global_rate|pct }} "
        "across all entities (gap {{ gap|pct }}, n={{ n }}).{% if slope is not none %} The daily investigated rate is trending at "
        "{{ slope_per_week|pct(1) }} per week.{% endif %}"
    ),
    "EG-11": (
        "{% if without_record_rate is not none %}{{ n_without }} escalated alerts ({{ without_record_rate|pct }}) have no corresponding "
        "escalation record. {% endif %}{% if incident_link_rate is not none %}Only {{ incident_link_rate|pct }} of escalated critical "
        "alerts are linked to an incident (peer median {{ peer_link|pct }}). {% endif %}Sample alerts: {{ sample_ids|join_k }}."
    ),
    "NS-01": (
        "{{ n_silent }} of {{ n_tier1 }} Tier-1 assets produced no alerts this period; {{ n_new }} of them were active in at least two "
        "of the previous five periods (for example {{ example_asset }}). Silent-asset rate {{ rate|pct }} against a peer median of "
        "{{ peer_rate|pct }}."
    ),
    "NS-02": (
        "{% if dropped %}Telemetry source(s) {{ dropped|join_k }} were active in earlier periods but produced nothing this period although "
        "{{ n_declaring }} assets declare them and roughly {{ expected_alerts|num(0) }} alerts were expected through them. {% endif %}"
        "{% if gap_tier1 %}{{ gap_tier1|pct }} of the telemetry sources expected for Tier-1 assets produced no alerts "
        "(missing: {{ missing|join_k }}). {% endif %}"
    ),
    "NS-03": (
        "Alert categories {{ missing|join_k }} are expected for a {{ sector }} entity with this asset mix and are reported by "
        "{{ peer_share|pct }} of peers on average, but are absent from this submission (weighted coverage gap {{ score|pct }})."
        "{% if newly_missing %} {{ newly_missing|join_k }} were present in earlier periods and have disappeared.{% endif %}"
    ),
    "NS-04": (
        "Alert volume of {{ actual|num(0) }} is well below the {{ predicted|num(0) }} expected for a {{ size_band }} {{ sector }} entity "
        "with {{ n_assets }} documented assets ({{ z|num(1) }} standard deviations below the peer model). Under-reporting or missing "
        "telemetry is likely."
    ),
    "NS-05": (
        "Alert volume fell {{ delta|pct }} from the previous period ({{ prev|num(0) }} to {{ current|num(0) }})"
        "{% if z_self is not none %}, {{ z_self|num(1) }} standard deviations below the entity's own recent history{% endif %}. "
        "Largest drops: {{ top_drops|join_k }}."
    ),
    "NS-06": (
        "The submission for {{ period }} {{ problem }}: {{ details }}. This limits supervisory visibility and is itself treated as a "
        "negative-space signal."
    ),
    "NS-07": (
        "Assets of class {{ asset_class }} ({{ n_assets }} assets) generated {{ rate|num(1) }} alerts per asset against a peer median of "
        "{{ peer_rate|num(1) }}; this class appears unmonitored or under-instrumented."
    ),
    "NS-08": (
        "Tier-1 assets generate {{ r1|num(1) }} alerts per asset versus {{ r3|num(1) }} for Tier-3 (ratio {{ ratio|num(2) }}, "
        "peer median {{ peer_ratio|num(2) }}), suggesting critical systems are monitored less closely than routine ones."
    ),
}


def render(rule_id: str, evidence: dict[str, Any]) -> str:
    template = TEMPLATES.get(rule_id)
    if template is None:
        return f"{rule_id} triggered."
    return ENV.from_string(template).render(**evidence).strip()
