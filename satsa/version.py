"""Version identifiers and the code hash written into every audit row."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

__version__ = "0.1.0"

# Bump when any rule condition, threshold semantics or template changes.
RULES_VERSION = "r1"
# Bump when the feature set or any feature formula changes; the pipeline refuses
# to load models trained against a different FEATURE_VERSION.
FEATURE_VERSION = "f1"

_PACKAGE_ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def get_code_hash() -> str:
    """SHA-256 over every .py and .sql file in the satsa package, in sorted path order.

    Recorded in audit_runs.code_hash so a finding can always be traced to the exact
    code that produced it. Cached because the package does not change while running.
    """
    digest = hashlib.sha256()
    files = sorted(p for p in _PACKAGE_ROOT.rglob("*") if p.suffix in {".py", ".sql"} and p.is_file())
    for path in files:
        digest.update(str(path.relative_to(_PACKAGE_ROOT)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
