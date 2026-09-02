"""Entry point: build the 8-entity, 6-period synthetic dataset plus ground truth."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from satsa.config import Settings
from simulator.alert_factory import Asset, build_assets, generate_period
from simulator.entity_profiles import PERIODS, SECTOR_ASSET_CLASSES, EntityProfile, default_profiles
from simulator.export import EXPORTERS
from simulator.ground_truth import write_ground_truth


@dataclass
class GenerationSummary:
    seed: int
    out_dir: Path
    ground_truth: dict[str, Path]
    files: list[Path] = field(default_factory=list)
    alerts_per_entity_period: dict[tuple[str, str], int] = field(default_factory=dict)

    @property
    def total_alerts(self) -> int:
        return sum(self.alerts_per_entity_period.values())


def generate_dataset(
    settings: Settings,
    *,
    seed: int | None = None,
    out_dir: Path | None = None,
    ground_truth_dir: Path | None = None,
    periods: list[str] | None = None,
    entity_ids: list[str] | None = None,
    profiles: list[EntityProfile] | None = None,
) -> GenerationSummary:
    seed = settings.app.seed if seed is None else seed
    out_dir = Path(out_dir or settings.resolve(settings.paths.synthetic_dir))
    gt_dir = Path(ground_truth_dir or settings.resolve(settings.paths.ground_truth_dir))
    periods = periods or PERIODS
    profiles = profiles or default_profiles()
    if entity_ids:
        profiles = [p for p in profiles if p.entity_id in entity_ids]
    out_dir.mkdir(parents=True, exist_ok=True)

    class_sources = settings.expected_categories.get("default_telemetry_sources") or {}
    summary = GenerationSummary(seed=seed, out_dir=out_dir, ground_truth={})
    all_labels: list[dict] = []

    for p_idx, profile in enumerate(profiles):
        # Independent streams per entity so adding/removing an entity does not reshuffle the others.
        rnd = random.Random(seed * 1000 + p_idx)
        rng = np.random.default_rng(seed * 1000 + p_idx)
        assets: list[Asset] = build_assets(profile, rnd, class_sources, SECTOR_ASSET_CLASSES[profile.sector])
        entity_row = {
            "entity_id": profile.entity_id, "name": profile.name, "sector": profile.sector, "size_band": profile.size_band,
            "documented_soc_tier": profile.soc_tier, "documented_asset_count": len(assets),
        }
        asset_rows = [a.__dict__ for a in assets]
        offset = 0
        for period_idx, period in enumerate(periods):
            out = generate_period(profile, period, period_idx, assets, rnd, rng, offset)
            offset += len(out.alerts) + 10
            all_labels.extend(out.alert_labels)
            tables = {
                "entities": [entity_row],
                "assets": asset_rows,
                "alerts": out.alerts,
                "escalations": out.escalations,
                "incidents": out.incidents,
            }
            summary.files += EXPORTERS[profile.export_format](out_dir, profile.entity_id, period, tables)
            summary.alerts_per_entity_period[(profile.entity_id, period)] = len(out.alerts)

    summary.ground_truth = write_ground_truth(profiles, all_labels, gt_dir, periods)
    return summary
