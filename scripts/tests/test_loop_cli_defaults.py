"""Tests for ll-loop run persistent default flags via config (ENH-2109)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


class TestLoopRunDefaults:
    """Tests that ll-loop run backfills args from loops.run_defaults config."""

    def _write_config(self, tmp_path: Path, run_defaults: dict) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config = {"loops": {"run_defaults": run_defaults}}
        (ll_dir / "ll-config.json").write_text(json.dumps(config))

    def test_clear_default_applied_from_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config clear:true backfills args.clear when --clear is not passed on CLI."""
        self._write_config(tmp_path, {"clear": True})
        monkeypatch.chdir(tmp_path)

        with (
            patch.object(sys, "argv", ["ll-loop", "run", "my-loop"]),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            main_loop()

        args = mock_run.call_args[0][1]
        assert args.clear is True

    def test_explicit_clear_not_overridden_by_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit --clear on CLI is not affected by config clear:false."""
        self._write_config(tmp_path, {"clear": False})
        monkeypatch.chdir(tmp_path)

        with (
            patch.object(sys, "argv", ["ll-loop", "run", "my-loop", "--clear"]),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            main_loop()

        args = mock_run.call_args[0][1]
        assert args.clear is True

    def test_show_diagrams_default_applied_from_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config show_diagrams:'clean' backfills args.show_diagrams when flag not passed."""
        self._write_config(tmp_path, {"show_diagrams": "clean"})
        monkeypatch.chdir(tmp_path)

        with (
            patch.object(sys, "argv", ["ll-loop", "run", "my-loop"]),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            main_loop()

        args = mock_run.call_args[0][1]
        assert args.show_diagrams == "clean"

    def test_explicit_show_diagrams_overrides_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit --show-diagrams on CLI is not replaced by config show_diagrams."""
        self._write_config(tmp_path, {"show_diagrams": "clean"})
        monkeypatch.chdir(tmp_path)

        with (
            patch.object(
                sys,
                "argv",
                ["ll-loop", "run", "my-loop", "--show-diagrams", "detailed"],
            ),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            main_loop()

        args = mock_run.call_args[0][1]
        assert args.show_diagrams == "detailed"

    def test_show_diagrams_default_sentinel_maps_to_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config show_diagrams:'default' backfills args.show_diagrams=True (bare flag)."""
        self._write_config(tmp_path, {"show_diagrams": "default"})
        monkeypatch.chdir(tmp_path)

        with (
            patch.object(sys, "argv", ["ll-loop", "run", "my-loop"]),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            main_loop()

        args = mock_run.call_args[0][1]
        assert args.show_diagrams is True

    def test_invalid_show_diagrams_in_config_raises_value_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid show_diagrams value in config raises ValueError at config load."""
        self._write_config(tmp_path, {"show_diagrams": "not-a-valid-mode"})
        monkeypatch.chdir(tmp_path)

        with patch.object(sys, "argv", ["ll-loop", "run", "my-loop"]):
            from little_loops.cli import main_loop

            with pytest.raises(ValueError, match="show_diagrams"):
                main_loop()


class TestLoopRunDefaultsDataclass:
    """Tests for LoopRunDefaults dataclass parsing."""

    def test_from_dict_defaults(self) -> None:
        """Empty dict gives all-default LoopRunDefaults."""
        from little_loops.config.features import LoopRunDefaults

        result = LoopRunDefaults.from_dict({})
        assert result.clear is False
        assert result.show_diagrams is None
        assert result.mode is None

    def test_from_dict_clear_true(self) -> None:
        """clear:true is parsed correctly."""
        from little_loops.config.features import LoopRunDefaults

        result = LoopRunDefaults.from_dict({"clear": True})
        assert result.clear is True

    def test_from_dict_show_diagrams_valid(self) -> None:
        """Valid show_diagrams values are accepted."""
        from little_loops.config.features import LoopRunDefaults

        for value in ("layered", "neighborhood", "inline", "detailed", "summary", "clean",
                      "local", "slim", "oneline", "default"):
            result = LoopRunDefaults.from_dict({"show_diagrams": value})
            assert result.show_diagrams == value

    def test_from_dict_show_diagrams_invalid_raises(self) -> None:
        """Invalid show_diagrams values raise ValueError."""
        from little_loops.config.features import LoopRunDefaults

        with pytest.raises(ValueError, match="show_diagrams"):
            LoopRunDefaults.from_dict({"show_diagrams": "bad-value"})

    def test_loops_config_includes_run_defaults(self) -> None:
        """LoopsConfig.from_dict parses run_defaults block."""
        from little_loops.config.features import LoopsConfig

        result = LoopsConfig.from_dict({"run_defaults": {"clear": True, "show_diagrams": "clean"}})
        assert result.run_defaults.clear is True
        assert result.run_defaults.show_diagrams == "clean"
