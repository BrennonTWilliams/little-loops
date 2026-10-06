"""Catalog-presence tests for FEAT-3589 html-webapp-generator.

The loop is a new builtin FSM harness and must be discoverable via the same
catalog surfaces as html-website-generator:

- scripts/little_loops/loops/README.md must contain a `html-webapp-generator`
  catalog row (test_documented_in_loops_readme, mirrors flux-image-generator)
- `ll-loop validate` must exit 0 with no warnings (artifact_versioning_ok +
  scope + gate entries; regression gate for the validator's WarningBudget
  category)
- The loop must appear in `ll-loop list` output

These tests are structural-only — they confirm the wiring is consistent
without exercising the actual generator-evaluator sub-process (covered by
test_html_webapp_generator_viewport_gate.py).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "html-webapp-generator.yaml"
README_FILE = BUILTIN_LOOPS_DIR / "README.md"


def test_loop_file_exists() -> None:
    """Loop YAML must exist at scripts/little_loops/loops/html-webapp-generator.yaml."""
    assert LOOP_FILE.exists(), f"Loop file not found: {LOOP_FILE}"


def test_documented_in_loops_readme() -> None:
    """scripts/little_loops/loops/README.md must contain a `html-webapp-generator` row."""
    readme = README_FILE.read_text()
    assert "`html-webapp-generator`" in readme, (
        "html-webapp-generator must appear in scripts/little_loops/loops/README.md catalog "
        "(mirror of flux-image-generator's test_documented_in_loops_readme)."
    )


def test_ll_loop_validate_exits_zero() -> None:
    """ll-loop validate must exit 0 (no validator warnings; artifact_versioning_ok set)."""
    result = subprocess.run(
        ["ll-loop", "validate", "html-webapp-generator"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent,
    )
    assert result.returncode == 0, (
        f"ll-loop validate failed with rc={result.returncode}: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "WARNING" not in result.stdout, (
        f"ll-loop validate produced a WARNING (ValidatorWarningBudget regression): "
        f"{result.stdout!r}"
    )


def test_appears_in_ll_loop_list() -> None:
    """ll-loop list must show html-webapp-generator."""
    result = subprocess.run(
        ["ll-loop", "list"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent,
    )
    assert result.returncode == 0, (
        f"ll-loop list failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "html-webapp-generator" in result.stdout, (
        f"html-webapp-generator missing from 'll-loop list' output: {result.stdout!r}"
    )
