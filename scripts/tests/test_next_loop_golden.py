"""Golden-output characterization for ``ll-loop next-loop`` (FEAT-3681).

Goldens under ``tests/fixtures/next_loop_golden/`` were captured against the
pre-extraction implementation with the module clock frozen, so recency and
rationale see the same instant. They pin the legacy arithmetic: unnormalized
weighted sum, uncapped frequency, future-timestamp recency above 1, timestamp
string ordering, stable ties and mixed statuses.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from little_loops.cli import output
from little_loops.cli.loop import next_loop
from little_loops.config import BRConfig
from little_loops.logger import Logger
from little_loops.utility import weighted_sum

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "next_loop_golden"
NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)


class FrozenDatetime(datetime):
    """``datetime`` stand-in whose ``now`` is pinned to :data:`NOW`."""

    @classmethod
    def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
        return NOW if tz is None else NOW.astimezone(tz)


def _add_run(hist: Path, run_id: str, loop: str, status: str | None, started: str | None) -> None:
    d = hist / f"{run_id}-{loop}"
    d.mkdir()
    data: dict[str, Any] = {}
    if status is not None:
        data["status"] = status
    if started is not None:
        data["started_at"] = started
    (d / "state.json").write_text(json.dumps(data))


def build_history(loops_dir: Path) -> Path:
    """Build the flat ``.loops/.history/<run_id>-<loop>/state.json`` archive."""
    hist = loops_dir / ".history"
    hist.mkdir(parents=True)
    # alpha: >50 runs (uncapped frequency)
    for i in range(60):
        day = f"2026-01-{(i % 28) + 1:02d}"
        _add_run(
            hist, f"{day}T{i // 28:02d}0000", "alpha", "completed", f"{day}T{i // 28:02d}:00:00Z"
        )
    _add_run(hist, "2026-03-14T120000", "alpha", "completed", "2026-03-14T12:00:00Z")
    # beta: offsets whose lexical and chronological order differ, mixed statuses
    _add_run(hist, "2026-03-10T230000", "beta", "completed", "2026-03-10T23:00:00-05:00")
    _add_run(hist, "2026-03-11T010000", "beta", "failed", "2026-03-11T01:00:00+00:00")
    _add_run(hist, "2026-03-11T020000", "beta", "interrupted", None)
    # gamma: malformed + naive timestamps (zero recency)
    _add_run(hist, "2026-03-01T000000", "gamma", "completed", "not-a-date")
    _add_run(hist, "2026-03-02T000000", "gamma", "running", "2026-03-14T10:00:00")
    # delta: future timestamp (recency above 1)
    _add_run(hist, "2026-03-03T000000", "delta", "completed", "2026-03-20T12:00:00Z")
    # tie pair
    for name in ("tie-a", "tie-b"):
        _add_run(hist, "2026-03-05T000000", name, "completed", "2026-03-05T00:00:00Z")
        _add_run(hist, "2026-03-06T000000", name, "failed", "2026-03-06T00:00:00Z")
    # epsilon/zeta: no status or timestamp / unreadable state file
    _add_run(hist, "2026-03-07T000000", "epsilon", None, None)
    bad = hist / "2026-03-08T000000-zeta"
    bad.mkdir()
    (bad / "state.json").write_text("{not json")
    _add_run(hist, "2026-03-15T080000", "today-loop", "completed", "2026-03-15T08:00:00Z")
    _add_run(hist, "2026-03-14T080000", "yday-loop", "completed", "2026-03-14T08:00:00Z")
    return loops_dir


@pytest.fixture
def loops_dir(tmp_path: Path) -> Path:
    return build_history(tmp_path / ".loops")


def _config(root: Path, local_md: str | None = None) -> BRConfig:
    (root / ".ll").mkdir(exist_ok=True)
    if local_md is not None:
        (root / ".ll" / "ll.local.md").write_text(local_md)
    return BRConfig(root)


def _invoke(
    ns: dict[str, Any],
    loops_dir: Path,
    capsys: pytest.CaptureFixture[str],
    config: BRConfig | None = None,
) -> tuple[int, str]:
    args = argparse.Namespace(**ns)
    cfg = config if config is not None else _config(loops_dir.parent)
    with patch.object(next_loop, "datetime", FrozenDatetime):
        rc = next_loop.cmd_next_loop(args, loops_dir, Logger(use_color=False), cfg)
    return rc, capsys.readouterr().out


GOLDEN_CASES = [
    ("text10", {"count": 10, "json": False, "execute": False, "exclude": []}, False),
    ("text10_color", {"count": 10, "json": False, "execute": False, "exclude": []}, True),
    ("json20", {"count": 20, "json": True, "execute": False, "exclude": []}, False),
    ("text1", {"count": 1, "json": False, "execute": False, "exclude": []}, False),
    ("json_excl", {"count": 3, "json": True, "execute": False, "exclude": ["alpha"]}, False),
]


class TestGoldenOutput:
    @pytest.mark.parametrize(
        ("name", "ns", "color"), GOLDEN_CASES, ids=[c[0] for c in GOLDEN_CASES]
    )
    def test_byte_identical(
        self,
        name: str,
        ns: dict[str, Any],
        color: bool,
        loops_dir: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(output, "_USE_COLOR", color)
        rc, out = _invoke(ns, loops_dir, capsys)
        assert rc == 0
        assert out == (GOLDEN_DIR / f"{name}.txt").read_text(encoding="utf-8")


# Raw (pre-rounding) additive scores captured from the legacy implementation.
RAW_SCORES = {
    "alpha": (0.9965540033747178, 1.0, "2026-03-14T12:00:00Z"),
    "beta": (0.4358854590597031, 0.3333333333333333, "2026-03-11T01:00:00+00:00"),
    "delta": (0.7803469307990238, 1.0, "2026-03-20T12:00:00Z"),
    "epsilon": (0.08814571719444105, 0.0, None),
    "gamma": (0.23970765635236108, 0.5, "not-a-date"),
    "tie-a": (0.3568140336757176, 0.5, "2026-03-06T00:00:00Z"),
    "tie-b": (0.3568140336757176, 0.5, "2026-03-06T00:00:00Z"),
    "today-loop": (0.583235296927698, 1.0, "2026-03-15T08:00:00Z"),
    "yday-loop": (0.5554153326365427, 1.0, "2026-03-14T08:00:00Z"),
    "zeta": (0.08814571719444105, 0.0, None),
}


DEFAULT_WEIGHTS = {"frequency": 0.50, "recency": 0.30, "success": 0.20}


def _scan(loops_dir: Path) -> dict[str, list[dict[str, Any]]]:
    return next_loop._scan_history(loops_dir)


class TestRawScores:
    def test_raw_additive_scores_match_legacy(self, loops_dir: Path) -> None:
        history = _scan(loops_dir)
        assert set(history) == set(RAW_SCORES)
        for name, runs in history.items():
            got = next_loop._score_loop(runs, as_of=NOW, weights=DEFAULT_WEIGHTS)
            assert got == RAW_SCORES[name], name

    def test_empty_runs_fast_path(self) -> None:
        assert next_loop._score_loop([], as_of=NOW, weights=DEFAULT_WEIGHTS) == (0.0, 1.0, None)

    def test_extreme_future_timestamp_overflows(self) -> None:
        runs = [{"status": "completed", "started_at": "9999-12-31T00:00:00Z"}]
        with pytest.raises(OverflowError):
            next_loop._score_loop(runs, as_of=NOW, weights=DEFAULT_WEIGHTS)

    def test_weight_order_is_preserved_left_to_right(self) -> None:
        scores = {"frequency": 0.1, "recency": 0.2, "success": 0.3}
        expected = 0.50 * 0.1 + 0.30 * 0.2 + 0.20 * 0.3
        assert weighted_sum(scores, DEFAULT_WEIGHTS) == expected


class TestClockInjection:
    def test_command_captures_clock_once(
        self, loops_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls: list[Any] = []

        class CountingDatetime(FrozenDatetime):
            @classmethod
            def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
                calls.append(tz)
                return super().now(tz)

        args = argparse.Namespace(count=3, json=True, execute=False, exclude=[])
        cfg = _config(loops_dir.parent)
        with patch.object(next_loop, "datetime", CountingDatetime):
            next_loop.cmd_next_loop(args, loops_dir, Logger(use_color=False), cfg)
        capsys.readouterr()
        assert calls == [UTC]

    def test_build_rationale_uses_injected_instant(self) -> None:
        text = next_loop._build_rationale(2, 1.0, "2026-03-10T12:00:00Z", "", as_of=NOW)
        assert "last run 5d ago" in text
