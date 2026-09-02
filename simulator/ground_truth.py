"""Write the labels the validation harness scores against."""

from __future__ import annotations

import csv
from pathlib import Path

from simulator.entity_profiles import PERIODS, EntityProfile


def write_ground_truth(profiles: list[EntityProfile], alert_labels: list[dict], out_dir: Path, periods: list[str] | None = None) -> dict[str, Path]:
    periods = periods or PERIODS
    out_dir.mkdir(parents=True, exist_ok=True)
    ep_path = out_dir / "entity_period_labels.csv"
    ef_path = out_dir / "expected_findings.csv"
    al_path = out_dir / "alert_labels.csv"

    with ep_path.open("w", newline="", encoding="utf-8") as fh, ef_path.open("w", newline="", encoding="utf-8") as fh2:
        w = csv.writer(fh)
        w.writerow(["entity_id", "submission_period", "profile", "is_execution_gap", "is_negative_space", "injected_patterns"])
        w2 = csv.writer(fh2)
        w2.writerow(["entity_id", "submission_period", "rule_id"])
        for p in profiles:
            for idx, period in enumerate(periods):
                affected = p.affected(idx)
                rules = list(p.expected_rules) if affected else []
                w.writerow([
                    p.entity_id, period, p.profile,
                    int(p.profile == "EXEC_GAP" and affected),
                    int(p.profile == "NEG_SPACE" and affected),
                    ";".join(rules),
                ])
                for r in rules:
                    w2.writerow([p.entity_id, period, r])

    with al_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["alert_id", "entity_id", "submission_period", "injected_pattern"])
        w.writeheader()
        w.writerows(alert_labels)

    return {"entity_period_labels": ep_path, "expected_findings": ef_path, "alert_labels": al_path}
