"""Attach ML attributions to combined findings.

TreeExplainer (SHAP) on the IsolationForest is used when shap is importable; otherwise a
z-score attribution (feature deviation from the peer median, in the risky direction) stands
in and is labelled as such. Either way the finding records which method produced it.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from satsa.analytics.anomaly import MODULE_A_FEATURES
from satsa.config import Settings
from satsa.db.repo import to_json
from satsa.features.build import FeatureBuildResult
from satsa.features.registry import REGISTRY
from satsa.models.registry import ModelBundle
from satsa.models.train import ensemble_frame

try:
    import shap  # type: ignore

    SHAP_AVAILABLE = True
except Exception:  # pragma: no cover
    shap = None
    SHAP_AVAILABLE = False


def _label(col: str) -> str:
    base = col[2:] if col.startswith("z_") else col
    meta = REGISTRY.get(base)
    return (meta.label if meta else base) + (" (peer z)" if col.startswith("z_") else "")


def explain_findings(findings: list[dict[str, Any]], fb: FeatureBuildResult, bundle: ModelBundle | None, settings: Settings) -> int:
    combined = [f for f in findings if f["module"] == "A" and f["rule_id"] is None and f["decision"] != "AUTO_CLEAR"]
    if not combined:
        return 0
    zmap = {r.entity_id: json.loads(r.peer_z_json) for r in fb.rows.itertuples()}
    shap_values, base, cols = None, None, []
    if bundle is not None and bundle.available and SHAP_AVAILABLE:
        try:
            ef = ensemble_frame(fb)
            Z = bundle.ensemble.preprocessor.transform(ef.values)
            explainer = shap.TreeExplainer(bundle.ensemble.iforest)
            sv = explainer.shap_values(Z)
            shap_values = {eid: -np.asarray(sv[i]) for i, eid in enumerate(ef.index)}  # negate: higher = more anomalous
            ev = explainer.expected_value
            base = float(-(ev if np.ndim(ev) == 0 else ev[0]))
            cols = list(ef.columns)
        except Exception:  # pragma: no cover - degrade gracefully
            shap_values = None
    n = 0
    for f in combined:
        eid = f["entity_id"]
        feats = fb.values[eid]
        if shap_values is not None:
            contribs = sorted(((cols[i], float(v)) for i, v in enumerate(shap_values[eid])), key=lambda kv: -abs(kv[1]))[:8]
            out = []
            for c, s in contribs:
                raw = c[2:] if c.startswith("z_") else c
                out.append({"feature": c, "label": _label(c), "shap": s, "value": feats[raw].value if raw in feats else None, "peer_median": None})
            payload = {"method": "shap_tree_isolation_forest", "base_value": base, "output": float(np.sum(shap_values[eid])) + (base or 0.0), "contributions": out}
        else:
            z = zmap.get(eid, {})
            risky = []
            for name in MODULE_A_FEATURES:
                zv = z.get(name)
                if zv is None or name not in REGISTRY:
                    continue
                risky.append((name, zv if REGISTRY[name].higher_is_worse else -zv))
            risky.sort(key=lambda kv: -kv[1])
            payload = {"method": "zscore_attribution", "base_value": 0.0, "output": f["p_final"], "contributions": [{"feature": n_, "label": _label(n_), "shap": s, "value": feats[n_].value, "peer_median": None} for n_, s in risky[:8]]}
        f["shap_json"] = to_json(payload)
        extra = what_would_change(payload)
        if extra:
            f["rationale"] = f["rationale"] + " " + extra
        n += 1
    return n


def what_would_change(payload: dict[str, Any]) -> str:
    top = [c for c in payload["contributions"] if c["shap"] > 0][:2]
    if not top:
        return ""
    names = " and ".join(c["label"].lower() for c in top)
    return f"The strongest contributors are {names}; bringing these back to the peer median would most reduce the score."
