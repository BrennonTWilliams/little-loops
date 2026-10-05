"""``next.loop_history.weights`` config resolution and next-loop boundary (FEAT-3681)."""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.cli.loop import main_loop, next_loop
from little_loops.config import BRConfig, NextConfig, NextConfigError
from little_loops.logger import Logger
from tests.test_next_loop_golden import FrozenDatetime, build_history

DEFAULTS = {"frequency": 0.50, "recency": 0.30, "success": 0.20}


def _project(root: Path, base: dict[str, Any] | None = None, local: str | None = None) -> Path:
    (root / ".ll").mkdir(parents=True, exist_ok=True)
    cfg = {"project": {"name": "t"}, "loops": {"loops_dir": ".loops"}}
    cfg.update(base or {})
    (root / ".ll" / "ll-config.json").write_text(json.dumps(cfg))
    if local is not None:
        (root / ".ll" / "ll.local.md").write_text(f"---\n{local}\n---\n")
    return root


def _weights(root: Path) -> dict[str, float]:
    return BRConfig(root).next.resolve_loop_history_weights()


class TestResolution:
    def test_defaults_when_absent(self, tmp_path: Path) -> None:
        weights = _weights(_project(tmp_path))
        assert weights == DEFAULTS
        assert list(weights) == ["frequency", "recency", "success"]

    def test_partial_objects_fill_defaults_in_canonical_order(self, tmp_path: Path) -> None:
        _project(
            tmp_path, {"next": {"loop_history": {"weights": {"success": 0.9, "frequency": 1}}}}
        )
        weights = _weights(tmp_path)
        assert weights == {"frequency": 1.0, "recency": 0.30, "success": 0.9}
        assert list(weights) == ["frequency", "recency", "success"]

    @pytest.mark.parametrize(
        "next_value", [{}, {"loop_history": {}}, {"loop_history": {"weights": {}}}]
    )
    def test_empty_levels_resolve_to_defaults(self, tmp_path: Path, next_value: dict) -> None:
        _project(tmp_path, {"next": next_value})
        assert _weights(tmp_path) == DEFAULTS

    def test_explicit_zero_disables_axis(self, tmp_path: Path) -> None:
        _project(tmp_path, {"next": {"loop_history": {"weights": {"recency": 0}}}})
        assert _weights(tmp_path) == {"frequency": 0.5, "recency": 0.0, "success": 0.2}

    def test_one_key_local_override_preserves_siblings(self, tmp_path: Path) -> None:
        base = {"next": {"loop_history": {"weights": {"frequency": 0.1, "recency": 0.2}}}}
        _project(tmp_path, base, "next:\n  loop_history:\n    weights:\n      recency: 0.9")
        assert _weights(tmp_path) == {"frequency": 0.1, "recency": 0.9, "success": 0.2}

    def test_local_one_key_over_absent_base(self, tmp_path: Path) -> None:
        _project(tmp_path, None, "next:\n  loop_history:\n    weights:\n      success: 0.6")
        assert _weights(tmp_path) == {"frequency": 0.5, "recency": 0.3, "success": 0.6}

    def test_local_null_leaf_restores_default(self, tmp_path: Path) -> None:
        base = {"next": {"loop_history": {"weights": {"recency": 0.9, "success": 0.1}}}}
        _project(tmp_path, base, "next:\n  loop_history:\n    weights:\n      recency: null")
        assert _weights(tmp_path) == {"frequency": 0.5, "recency": 0.3, "success": 0.1}

    @pytest.mark.parametrize(
        "local",
        [
            "next: null",
            "next:\n  loop_history: null",
            "next:\n  loop_history:\n    weights: null",
            "next:\n  loop_history:\n    weights:\n      frequency: null\n      recency: null",
        ],
    )
    def test_local_resets_at_each_ancestor_restore_defaults(
        self, tmp_path: Path, local: str
    ) -> None:
        base = {"next": {"loop_history": {"weights": {"frequency": 0.9, "recency": 0.1}}}}
        _project(tmp_path, base, local)
        assert _weights(tmp_path) == DEFAULTS

    def test_loop_history_null_keeps_sibling_keys_untouched(self, tmp_path: Path) -> None:
        # Only `loop_history` is removed; the (empty) `next` root remains supplied.
        _project(
            tmp_path,
            {"next": {"loop_history": {"weights": {"frequency": 2}}}},
            "next:\n  loop_history: null",
        )
        cfg = BRConfig(tmp_path)
        assert cfg.next.present and cfg.next.to_dict() == {}

    @pytest.mark.parametrize("ancestor", [None, 5, "x"])
    def test_local_null_leaf_under_absent_or_scalar_ancestor(
        self, tmp_path: Path, ancestor: Any
    ) -> None:
        base = {} if ancestor is None else {"next": ancestor}
        _project(
            tmp_path,
            base,
            "next:\n  loop_history:\n    weights:\n      recency: null\n      success: 1",
        )
        assert _weights(tmp_path) == {"frequency": 0.5, "recency": 0.3, "success": 1.0}

    def test_surviving_null_is_invalid(self, tmp_path: Path) -> None:
        _project(tmp_path, {"next": {"loop_history": {"weights": {"recency": None}}}})
        with pytest.raises(NextConfigError, match=r"next\.loop_history\.weights\.recency"):
            _weights(tmp_path)

    def test_base_null_overwritten_or_removed_by_local_is_valid(self, tmp_path: Path) -> None:
        base = {"next": {"loop_history": {"weights": {"recency": None, "success": None}}}}
        _project(
            tmp_path,
            base,
            "next:\n  loop_history:\n    weights:\n      recency: 0.4\n      success: null",
        )
        assert _weights(tmp_path) == {"frequency": 0.5, "recency": 0.4, "success": 0.2}

    @pytest.mark.parametrize(
        ("raw", "needle"),
        [
            (None, "next must be a mapping, got null"),
            ([], "next must be a mapping, got list"),
            ("x", "next must be a mapping, got str"),
            ({"loop_history": None}, "next.loop_history must be a mapping, got null"),
            ({"loop_history": []}, "next.loop_history must be a mapping, got list"),
            ({"loop_history": {"weights": 1}}, "next.loop_history.weights must be a mapping"),
            ({"loop_history": {"weights": None}}, "next.loop_history.weights must be a mapping"),
            ({"verbs": {}}, "next has unknown keys: 'verbs'"),
            ({"loop_history": {"curve": 1}}, "next.loop_history has unknown keys: 'curve'"),
            ({"loop_history": {"weights": {"speed": 1}}}, "unknown keys: 'speed'"),
            ({"loop_history": {"weights": {"recency": True}}}, "recency must be a number"),
            ({"loop_history": {"weights": {"recency": "0.3"}}}, "recency must be a number"),
            (
                {"loop_history": {"weights": {"recency": -0.1}}},
                "recency must be a finite number >= 0",
            ),
            ({"loop_history": {"weights": {"recency": float("nan")}}}, "recency must be a finite"),
            ({"loop_history": {"weights": {"recency": float("inf")}}}, "recency must be a finite"),
            ({"loop_history": {"weights": {"recency": 10**400}}}, "recency is too large"),
            (
                {"loop_history": {"weights": {"frequency": 0, "recency": 0, "success": 0}}},
                "at least one weight must be nonzero",
            ),
        ],
    )
    def test_invalid_shapes_raise_setting_naming_error(self, raw: Any, needle: str) -> None:
        with pytest.raises(NextConfigError, match=needle.replace("(", r"\(")):
            NextConfig(present=True, raw=raw).resolve_loop_history_weights()

    def test_mixed_key_yaml_override_yields_controlled_error(self, tmp_path: Path) -> None:
        _project(
            tmp_path,
            None,
            "next:\n  loop_history:\n    weights:\n      2: 0.2\n      true: 0.1\n"
            "      frequency: 0.5\n      zeta: 3",
        )
        with pytest.raises(NextConfigError) as err:
            _weights(tmp_path)
        assert str(err.value).startswith(
            "next.loop_history.weights has unknown keys: 'zeta', 2, True"
        )

    def test_resolution_returns_fresh_mapping(self, tmp_path: Path) -> None:
        cfg = BRConfig(_project(tmp_path, {"next": {"loop_history": {"weights": {"recency": 1}}}}))
        first = cfg.next.resolve_loop_history_weights()
        first["recency"] = 99.0
        first.pop("success")
        assert cfg.next.resolve_loop_history_weights() == {
            "frequency": 0.5,
            "recency": 1.0,
            "success": 0.2,
        }
        default = BRConfig(_project(tmp_path / "d")).next.resolve_loop_history_weights()
        default["frequency"] = 7.0
        assert NextConfig().resolve_loop_history_weights() == DEFAULTS


class TestConstructionAndSerialization:
    @pytest.mark.parametrize(
        "raw",
        [
            None,
            {},
            {"loop_history": None},
            {"loop_history": {"weights": {"recency": 0.1}}},
            {"loop_history": {"weights": {"frequency": 2, "recency": 0, "success": 1}}},
            {"loop_history": {"weights": {"recency": None}}},
            {"loop_history": "bad", "extra": [1, {"x": None}]},
            [1, 2],
            "text",
        ],
        ids=[
            "null",
            "empty",
            "history-null",
            "partial",
            "nondefault",
            "leaf-null",
            "malformed",
            "list",
            "str",
        ],
    )
    def test_supplied_value_round_trips_verbatim(self, tmp_path: Path, raw: Any) -> None:
        _project(tmp_path, {"next": raw})
        cfg = BRConfig(tmp_path)  # construction never raises for invalid next
        assert cfg.next.present is True
        assert cfg.to_dict()["next"] == raw
        # Idempotent: serialize -> reload -> serialize.
        again = tmp_path / "again"
        _project(again, {"next": cfg.to_dict()["next"]})
        assert BRConfig(again).to_dict()["next"] == raw

    def test_absent_root_serializes_default_tree(self, tmp_path: Path) -> None:
        cfg = BRConfig(_project(tmp_path))
        assert cfg.next.present is False
        assert cfg.to_dict()["next"] == {"loop_history": {"weights": DEFAULTS}}

    def test_local_null_removes_root_so_it_serializes_as_absent(self, tmp_path: Path) -> None:
        _project(tmp_path, {"next": {"loop_history": {"weights": {"recency": 0.1}}}}, "next: null")
        cfg = BRConfig(tmp_path)
        assert cfg.next.present is False
        assert cfg.to_dict()["next"] == {"loop_history": {"weights": DEFAULTS}}

    def test_mutating_serialized_subtree_does_not_change_state(self, tmp_path: Path) -> None:
        raw = {"loop_history": {"weights": {"recency": 0.1}}}
        cfg = BRConfig(_project(tmp_path, {"next": raw}))
        dumped = cfg.to_dict()["next"]
        dumped["loop_history"]["weights"]["recency"] = 50
        dumped["extra"] = 1
        assert cfg.to_dict()["next"] == raw
        assert cfg.next.resolve_loop_history_weights()["recency"] == 0.1
        default_dump = BRConfig(_project(tmp_path / "d")).to_dict()["next"]
        default_dump["loop_history"]["weights"]["frequency"] = 9
        assert NextConfig().to_dict()["loop_history"]["weights"]["frequency"] == 0.5

    def test_raw_is_isolated_from_the_loaded_config(self, tmp_path: Path) -> None:
        cfg = BRConfig(
            _project(tmp_path, {"next": {"loop_history": {"weights": {"recency": 0.1}}}})
        )
        cfg._raw_config["next"]["loop_history"]["weights"]["recency"] = 5
        assert cfg.next.resolve_loop_history_weights()["recency"] == 0.1

    def test_invalid_next_does_not_break_unrelated_config(self, tmp_path: Path) -> None:
        cfg = BRConfig(_project(tmp_path, {"next": {"nonsense": [1]}}))
        assert cfg.project.name == "t"
        assert cfg.loops.loops_dir == ".loops"
        assert cfg.to_dict()["project"]["name"] == "t"


def _args(**kw: Any) -> argparse.Namespace:
    base = {"count": 20, "json": True, "execute": False, "exclude": []}
    base.update(kw)
    return argparse.Namespace(**base)


def _run(root: Path, args: argparse.Namespace) -> int:
    with patch.object(next_loop, "datetime", FrozenDatetime):
        return next_loop.cmd_next_loop(
            args, root / ".loops", Logger(use_color=False), BRConfig(root)
        )


class TestNondefaultWeights:
    def _top(self, root: Path, capsys: pytest.CaptureFixture[str], **kw: Any) -> list[dict]:
        assert _run(root, _args(**kw)) == 0
        return json.loads(capsys.readouterr().out)

    def test_frequency_only_weights_change_ranking(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build_history(tmp_path / ".loops")
        _project(
            tmp_path,
            None,
            "next:\n  loop_history:\n    weights:\n      recency: 0\n      success: 0",
        )
        got = self._top(tmp_path, capsys)
        assert [c["loop"] for c in got][:2] == ["alpha", "beta"]
        assert got[0]["score"] == round(0.5 * math.log1p(61) / math.log1p(50), 4)

    def test_zero_weight_does_not_affect_unrelated_axis(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build_history(tmp_path / ".loops")
        _project(
            tmp_path,
            None,
            "next:\n  loop_history:\n    weights:\n      frequency: 0\n      success: 0\n      recency: 1",
        )
        got = self._top(tmp_path, capsys)
        assert got[0]["loop"] == "delta"  # future timestamp -> recency > 1


class TestErrorBoundary:
    BAD = {"next": {"loop_history": {"weights": {"recency": "high"}}}}

    @pytest.mark.parametrize("as_json", [False, True])
    def test_invalid_config_exit_2_before_scan_or_execute(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], as_json: bool
    ) -> None:
        build_history(tmp_path / ".loops")
        _project(tmp_path, self.BAD)
        with (
            patch.object(next_loop, "_scan_history", MagicMock()) as scan,
            patch("little_loops.cli.loop.run.cmd_run", MagicMock()) as run,
        ):
            rc = _run(tmp_path, _args(json=as_json, execute=True))
        out = capsys.readouterr()
        assert rc == 2
        assert out.out == ""
        assert out.err.count("\n") == 1
        assert "next.loop_history.weights.recency" in out.err
        assert "Traceback" not in out.err
        scan.assert_not_called()
        run.assert_not_called()

    def test_precedence_over_no_history_and_all_excluded(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / ".loops").mkdir()
        _project(tmp_path, self.BAD)
        assert _run(tmp_path, _args()) == 2  # no history
        build_history(tmp_path / ".loops")
        everything = [
            "alpha",
            "beta",
            "gamma",
            "delta",
            "tie-a",
            "tie-b",
            "epsilon",
            "zeta",
            "today-loop",
            "yday-loop",
        ]
        assert _run(tmp_path, _args(exclude=everything)) == 2
        assert capsys.readouterr().out == ""

    def test_all_zero_weights_exit_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build_history(tmp_path / ".loops")
        _project(
            tmp_path,
            None,
            "next:\n  loop_history:\n    weights:\n      frequency: 0\n      recency: 0\n      success: 0",
        )
        assert _run(tmp_path, _args()) == 2
        assert "at least one weight must be nonzero" in capsys.readouterr().err

    def test_additive_overflow_is_a_controlled_exit_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build_history(tmp_path / ".loops")
        _project(
            tmp_path,
            {
                "next": {
                    "loop_history": {
                        "weights": {"frequency": 1e308, "recency": 1e308, "success": 1e308}
                    }
                }
            },
        )
        with patch("little_loops.cli.loop.run.cmd_run", MagicMock()) as run:
            rc = _run(tmp_path, _args(json=False, execute=True))
        out = capsys.readouterr()
        assert rc == 2
        assert out.out == ""
        assert "next.loop_history.weights" in out.err and "overflow" in out.err
        run.assert_not_called()

    def test_legacy_curve_overflow_is_not_relabelled(self, tmp_path: Path) -> None:
        hist = tmp_path / ".loops" / ".history" / "2026-03-01T000000-far"
        hist.mkdir(parents=True)
        (hist / "state.json").write_text(
            json.dumps({"status": "completed", "started_at": "9999-12-31T00:00:00Z"})
        )
        _project(tmp_path)
        with pytest.raises(OverflowError):
            _run(tmp_path, _args())

    def test_existing_no_history_and_excluded_exits_unchanged(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / ".loops").mkdir()
        _project(tmp_path)
        assert _run(tmp_path, _args()) == 1
        assert json.loads(capsys.readouterr().out) == []
        assert _run(tmp_path, _args(json=False)) == 1
        assert "No loop history" in capsys.readouterr().out
        build_history(tmp_path / ".loops")
        assert (
            _run(
                tmp_path,
                _args(
                    exclude=["alpha"]
                    + [
                        "beta",
                        "gamma",
                        "delta",
                        "tie-a",
                        "tie-b",
                        "epsilon",
                        "zeta",
                        "today-loop",
                        "yday-loop",
                    ],
                    json=False,
                ),
            )
            == 1
        )
        assert "No candidates" in capsys.readouterr().out

    def test_json_execute_does_not_dispatch(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build_history(tmp_path / ".loops")
        _project(tmp_path)
        with patch("little_loops.cli.loop.run.cmd_run", MagicMock()) as run:
            assert _run(tmp_path, _args(json=True, execute=True, count=1)) == 0
        run.assert_not_called()
        assert json.loads(capsys.readouterr().out)[0]["loop"] == "alpha"

    def test_text_execute_returns_dispatched_result(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build_history(tmp_path / ".loops")
        _project(tmp_path)
        with patch("little_loops.cli.loop.run.cmd_run", MagicMock(return_value=7)) as run:
            assert _run(tmp_path, _args(json=False, execute=True, count=1)) == 7
        assert run.call_args.args[0] == "alpha"
        capsys.readouterr()


class TestRealEntryPoint:
    """``ll-loop next-loop`` through ``main_loop`` (telemetry context stubbed)."""

    @pytest.mark.parametrize("flags", [[], ["--json"]])
    def test_invalid_config_text_and_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        flags: list[str],
    ) -> None:
        build_history(tmp_path / ".loops")
        _project(
            tmp_path, None, "next:\n  loop_history:\n    weights:\n      2: 0.2\n      true: 1"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "little_loops.cli.loop.cli_event_context", lambda *a, **k: contextlib.nullcontext()
        )
        scan = MagicMock()
        monkeypatch.setattr(next_loop, "_scan_history", scan)
        with patch.object(sys, "argv", ["ll-loop", "next-loop", *flags]):
            rc = main_loop()
        out = capsys.readouterr()
        assert rc == 2
        assert out.out == ""
        assert out.err.count("\n") == 1
        assert "next.loop_history.weights has unknown keys: 2, True" in out.err
        assert "Traceback" not in out.err
        scan.assert_not_called()

    def test_invalid_next_does_not_break_unrelated_command(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _project(tmp_path, {"next": "garbage"})
        (tmp_path / ".loops").mkdir(exist_ok=True)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "little_loops.cli.loop.cli_event_context", lambda *a, **k: contextlib.nullcontext()
        )
        with patch.object(sys, "argv", ["ll-loop", "list"]):
            assert main_loop() == 0
        capsys.readouterr()
