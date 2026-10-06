"""Tests for resolve_confidence_thresholds, shared by next-action and readiness_status (ENH-3604)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.cli.issues.check_readiness import (
    confidence_thresholds_from_gate,
    readiness_status,
    resolve_confidence_thresholds,
)
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


# --- BUG-3760: BRConfig-backed readers honor the loaded, merged configuration ---------------

NONCANONICAL = (40, 30)

HELPER_TABLE = [
    ("empty", {}, (40, 30, False)),
    ("readiness only", {"readiness_threshold": 70}, (70, 30, False)),
    ("outcome only", {"outcome_threshold": 50}, (40, 50, False)),
    (
        "full",
        {"readiness_threshold": 90, "outcome_threshold": 55, "enabled": True},
        (90, 55, True),
    ),
    ("enabled false", {"enabled": False}, (40, 30, False)),
    ("enabled true", {"enabled": True}, (40, 30, True)),
    ("zero thresholds present", {"readiness_threshold": 0, "outcome_threshold": 0}, (0, 0, False)),
    ("legacy threshold alias ignored", {"threshold": 90}, (40, 30, False)),
]


@pytest.mark.parametrize(
    ("label", "gate", "expected"), HELPER_TABLE, ids=[c[0] for c in HELPER_TABLE]
)
def test_pure_helper_table(label: str, gate: dict, expected: tuple[int, int, bool]) -> None:
    assert confidence_thresholds_from_gate(gate, NONCANONICAL) == expected


def _project(
    tmp_path: Path, base: dict | None, local: str | None = None, *, root: bool = False
) -> None:
    for kind in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / kind).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ll").mkdir(exist_ok=True)
    if base is not None:
        target = tmp_path / "ll-config.json" if root else tmp_path / ".ll" / "ll-config.json"
        target.write_text(json.dumps(base))
    if local is not None:
        (tmp_path / ".ll" / "ll.local.md").write_text(f"---\n{local}\n---\n\n# notes\n")


def _issue(tmp_path: Path, confidence: int = 90, outcome: int = 70) -> None:
    (tmp_path / ".issues" / "enhancements" / "P3-ENH-9200-t.md").write_text(
        f"---\nid: ENH-9200\nconfidence_score: {confidence}\noutcome_confidence: {outcome}\n"
        "---\n\n# ENH-9200: T\n"
    )


def _gate(**kw: object) -> dict:
    return {"commands": {"confidence_gate": kw}}


def _status(tmp_path: Path, **kw: object):  # type: ignore[no-untyped-def]
    status = readiness_status(
        BRConfig(tmp_path), "ENH-9200", default_readiness=40, default_outcome=30, **kw
    )
    assert status is not None
    return status


def test_local_override_wins_over_base(tmp_path: Path) -> None:
    _project(
        tmp_path,
        _gate(outcome_threshold=65, enabled=False),
        "commands:\n  confidence_gate:\n    outcome_threshold: 75\n    enabled: true",
    )
    _issue(tmp_path)
    s = _status(tmp_path)
    assert (s.outcome_threshold, s.enabled) == (75, True)


def test_local_lower_than_base(tmp_path: Path) -> None:
    _project(
        tmp_path,
        _gate(outcome_threshold=75),
        "commands:\n  confidence_gate:\n    outcome_threshold: 65",
    )
    _issue(tmp_path)
    assert _status(tmp_path).outcome_threshold == 65


REMOVALS = [
    (
        "leaf",
        "commands:\n  confidence_gate:\n    readiness_threshold: null\n    outcome_threshold: null\n    enabled: null",
    ),
    ("gate", "commands:\n  confidence_gate: null"),
    ("ancestor", "commands: null"),
]


@pytest.mark.parametrize(("label", "local"), REMOVALS, ids=[r[0] for r in REMOVALS])
def test_local_null_restores_caller_defaults(tmp_path: Path, label: str, local: str) -> None:
    _project(
        tmp_path,
        _gate(readiness_threshold=75, outcome_threshold=75, enabled=True),
        local,
    )
    _issue(tmp_path)
    s = _status(tmp_path)
    assert (s.readiness_threshold, s.outcome_threshold, s.enabled) == (40, 30, False)


def test_local_only_configuration(tmp_path: Path) -> None:
    _project(
        tmp_path,
        None,
        "commands:\n  confidence_gate:\n    outcome_threshold: 75\n    enabled: true",
    )
    _issue(tmp_path)
    s = _status(tmp_path)
    assert (s.readiness_threshold, s.outcome_threshold, s.enabled) == (40, 75, True)


def test_root_level_config_is_honored(tmp_path: Path) -> None:
    _project(tmp_path, _gate(readiness_threshold=80), root=True)
    _issue(tmp_path)
    assert _status(tmp_path).readiness_threshold == 80


def test_explicit_override_beats_local_config_including_zero(tmp_path: Path) -> None:
    _project(tmp_path, None, "commands:\n  confidence_gate:\n    readiness_threshold: 90")
    _issue(tmp_path)
    assert _status(tmp_path, readiness_override=0).readiness_threshold == 0


def test_supplied_config_is_a_snapshot(tmp_path: Path) -> None:
    _project(tmp_path, _gate(outcome_threshold=75))
    _issue(tmp_path)
    config = BRConfig(tmp_path)
    (tmp_path / ".ll" / "ll-config.json").write_text(json.dumps(_gate(outcome_threshold=65)))
    status = readiness_status(config, "ENH-9200")
    assert status is not None and status.outcome_threshold == 75


def test_confidence_gate_raw_is_detached(tmp_path: Path) -> None:
    _project(tmp_path, _gate(readiness_threshold=75, extra={"a": 1}))
    config = BRConfig(tmp_path)
    raw = config.confidence_gate_raw()
    raw["readiness_threshold"] = 1
    raw["extra"]["a"] = 2
    assert config.confidence_gate_raw() == {"readiness_threshold": 75, "extra": {"a": 1}}


@pytest.mark.parametrize("base", [None, {}, _gate()], ids=str)
def test_confidence_gate_raw_empty_when_absent(tmp_path: Path, base: dict | None) -> None:
    _project(tmp_path, base)
    assert BRConfig(tmp_path).confidence_gate_raw() == {}
