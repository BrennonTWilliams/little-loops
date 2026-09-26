"""Tests for resolve_confidence_thresholds, shared by next-action and readiness_status (ENH-3604)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.cli.issues.check_readiness import readiness_status, resolve_confidence_thresholds
from little_loops.config import BRConfig

DEFAULTS = (85, 65)


def _cfg(tmp_path: Path, raw: str | None) -> Path:
    path = tmp_path / ".ll" / "ll-config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        path.write_text(raw)
    return path


CASES = [
    ("absent file", None, (85, 65, False)),
    ("malformed json", "{not json", (85, 65, False)),
    ("no commands block", json.dumps({}), (85, 65, False)),
    (
        "partial block keeps default for missing key",
        json.dumps({"commands": {"confidence_gate": {"readiness_threshold": 70}}}),
        (70, 65, False),
    ),
    (
        "partial block, outcome only",
        json.dumps({"commands": {"confidence_gate": {"outcome_threshold": 50, "enabled": True}}}),
        (85, 50, True),
    ),
    (
        "full block",
        json.dumps(
            {
                "commands": {
                    "confidence_gate": {
                        "readiness_threshold": 90,
                        "outcome_threshold": 55,
                        "enabled": True,
                    }
                }
            }
        ),
        (90, 55, True),
    ),
]


@pytest.mark.parametrize(("label", "raw", "expected"), CASES, ids=[c[0] for c in CASES])
def test_helper_per_key_results(
    tmp_path: Path, label: str, raw: str | None, expected: tuple[int, int, bool]
) -> None:
    assert resolve_confidence_thresholds(_cfg(tmp_path, raw), DEFAULTS) == expected


def test_helper_honors_caller_defaults(tmp_path: Path) -> None:
    assert resolve_confidence_thresholds(_cfg(tmp_path, None), (40, 30)) == (40, 30, False)
    partial = json.dumps({"commands": {"confidence_gate": {"readiness_threshold": 70}}})
    assert resolve_confidence_thresholds(_cfg(tmp_path, partial), (40, 30)) == (70, 30, False)


# A malformed file makes BRConfig itself fail to load, so that row exercises the helper only.
BRCONFIG_CASES = [c for c in CASES if c[0] != "malformed json"]


@pytest.mark.parametrize(
    ("label", "raw", "expected"), BRCONFIG_CASES, ids=[c[0] for c in BRCONFIG_CASES]
)
def test_readiness_status_matches_helper(
    tmp_path: Path, label: str, raw: str | None, expected: tuple[int, int, bool]
) -> None:
    for kind in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / kind).mkdir(parents=True, exist_ok=True)
    _cfg(tmp_path, raw)
    (tmp_path / ".issues" / "enhancements" / "P3-ENH-9200-t.md").write_text(
        "---\nid: ENH-9200\nconfidence_score: 80\noutcome_confidence: 60\n---\n\n# ENH-9200: T\n"
    )
    status = readiness_status(BRConfig(tmp_path), "ENH-9200")
    assert status is not None
    assert (status.readiness_threshold, status.outcome_threshold, status.enabled) == expected


def test_readiness_status_overrides_layer_after_helper(tmp_path: Path) -> None:
    for kind in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / kind).mkdir(parents=True, exist_ok=True)
    _cfg(tmp_path, json.dumps({"commands": {"confidence_gate": {"readiness_threshold": 90}}}))
    (tmp_path / ".issues" / "enhancements" / "P3-ENH-9200-t.md").write_text(
        "---\nid: ENH-9200\nconfidence_score: 80\noutcome_confidence: 60\n---\n\n# ENH-9200: T\n"
    )
    status = readiness_status(BRConfig(tmp_path), "ENH-9200", readiness_override=70)
    assert status is not None and status.readiness_threshold == 70
