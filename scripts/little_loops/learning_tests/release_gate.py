"""Pre-release audit gate for learning test records (ENH-2214).

Checks whether any actively-imported packages have stale or refuted learning
test records. Returns 0 (pass) or 1 (block) based on the ``release_gate``
config value.

Called from ``/ll:manage-release`` before creating a git tag.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from little_loops.config.core import resolve_config_path
from little_loops.config.features import LearningTestsConfig
from little_loops.learning_tests import list_records
from little_loops.learning_tests.gate import is_record_stale
from little_loops.learning_tests.import_scan import get_imported_packages


def _load_lt_config(cwd: Path) -> LearningTestsConfig:
    config_path = resolve_config_path(cwd)
    if config_path is None:
        return LearningTestsConfig()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LearningTestsConfig()
    if not isinstance(data, dict):
        return LearningTestsConfig()
    return LearningTestsConfig.from_dict(data.get("learning_tests", {}))


def run_release_gate(cwd: Path, *, base_dir: Path | None = None) -> int:
    """Run the learning-test pre-release audit gate.

    Args:
        cwd: Project root used to load config and resolve ``scan_dirs``.
        base_dir: Override for the ``.ll/learning-tests`` directory (useful in tests).

    Returns:
        0 if the gate passes (no issues, ``release_gate="warn"``, or ``enabled=False``).
        1 if ``release_gate="block"`` and stale/refuted active packages are found.
    """
    lt_config = _load_lt_config(cwd)

    if not lt_config.enabled:
        return 0

    resolved_base = base_dir if base_dir is not None else cwd / ".ll" / "learning-tests"
    records = list_records(base_dir=resolved_base)

    problem_records = [
        r for r in records
        if r.status == "refuted" or is_record_stale(r, lt_config.stale_after_days)
    ]

    if not problem_records:
        return 0

    source_dirs = [cwd / d for d in lt_config.scan_dirs]
    imported_packages = get_imported_packages(source_dirs)

    hits = [r for r in problem_records if r.target in imported_packages]

    if not hits:
        return 0

    today = datetime.date.today()
    print("")
    print("⚠ Learning Test Pre-Release Audit")
    print(f"{'Package':<30} {'Status':<10} {'Record Date':<14} Days Since Proven")
    print("-" * 70)
    for record in hits:
        status = "refuted" if record.status == "refuted" else "stale"
        try:
            record_date = datetime.date.fromisoformat(record.date)
            age = str((today - record_date).days)
        except (ValueError, TypeError):
            age = "?"
        print(f"{record.target:<30} {status:<10} {record.date:<14} {age}")
    print("")

    if lt_config.release_gate == "block":
        print(
            "✗ Release blocked: fix or re-prove the above records, "
            "or set release_gate: warn to proceed."
        )
        return 1

    print(
        "⚠ Continuing with warning "
        "(set release_gate: block to abort on stale/refuted records)."
    )
    return 0
