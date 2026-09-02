"""Save/load joblib artifacts with a meta.json describing exactly how they were produced."""

from __future__ import annotations

import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn

from satsa.audit.hashing import hash_bytes, hash_file


def library_versions() -> dict[str, str]:
    import pandas

    out = {"python": platform.python_version(), "numpy": np.__version__, "pandas": pandas.__version__, "scikit-learn": sklearn.__version__}
    try:
        import hdbscan  # type: ignore

        out["hdbscan"] = getattr(hdbscan, "__version__", "present")
    except Exception:
        out["hdbscan"] = "absent"
    try:
        import shap

        out["shap"] = shap.__version__
    except Exception:
        out["shap"] = "absent"
    return out


def version_for(training_data_hash: str, config_hash: str, seed: int) -> str:
    return f"{datetime.now():%Y%m%d}_{hash_bytes(f'{training_data_hash}:{config_hash}:{seed}'.encode())[:8]}"


def save_artifact(models_dir: Path, name: str, version: str, obj: Any, meta: dict[str, Any]) -> tuple[Path, str]:
    folder = models_dir / name / version
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "model.joblib"
    joblib.dump(obj, path)
    digest = hash_file(path)
    meta = {**meta, "model_name": name, "version": version, "artifact_hash": digest, "saved_at": datetime.now().isoformat(timespec="seconds"), "library_versions": library_versions()}
    (folder / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path, digest


def load_artifact(path: Path | str, expected_hash: str | None = None) -> Any:
    path = Path(path)
    if expected_hash and hash_file(path) != expected_hash:
        raise RuntimeError(f"artifact hash mismatch for {path}; refusing to load a modified model")
    return joblib.load(path)
