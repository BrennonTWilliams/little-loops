"""Tests for cli/config.py - ll-config CLI entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.cli.config import main_config


class TestArgumentParsing:
    """Argparse unit tests via sys.argv, no filesystem."""

    def test_missing_subcommand_exits(self) -> None:
        with patch("sys.argv", ["ll-config"]):
            with pytest.raises(SystemExit):
                main_config()

    def test_missing_key_exits(self) -> None:
        with patch("sys.argv", ["ll-config", "get"]):
            with pytest.raises(SystemExit):
                main_config()


class TestGet:
    """Mocks BRConfig.resolve_variable() directly — no DB/filesystem fixtures."""

    def test_resolves_known_key(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_cfg = MagicMock()
        mock_cfg.resolve_variable.return_value = "-0.2"
        with (
            patch("sys.argv", ["ll-config", "get", "history.go_no_go.correction_penalty"]),
            patch("little_loops.config.BRConfig", return_value=mock_cfg),
        ):
            assert main_config() == 0
        assert capsys.readouterr().out.strip() == "-0.2"
        mock_cfg.resolve_variable.assert_called_once_with("history.go_no_go.correction_penalty")

    def test_unknown_key_prints_nothing(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_cfg = MagicMock()
        mock_cfg.resolve_variable.return_value = None
        mock_cfg.to_dict.return_value = {}
        with (
            patch("sys.argv", ["ll-config", "get", "nonexistent.path.here"]),
            patch("little_loops.config.BRConfig", return_value=mock_cfg),
        ):
            assert main_config() == 0
        assert capsys.readouterr().out.strip() == ""

    def test_never_raises_on_construction_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("sys.argv", ["ll-config", "get", "project.src_dir"]),
            patch("little_loops.config.BRConfig", side_effect=Exception("boom")),
        ):
            assert main_config() == 0
        assert capsys.readouterr().out.strip() == ""


class TestUnknownSectionWarning:
    """ENH-3021: stderr diagnostic when a dot-path's root is not a known config section."""

    def test_unknown_root_warns_on_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_cfg = MagicMock()
        mock_cfg.resolve_variable.return_value = None
        mock_cfg.to_dict.return_value = {"project": {}}
        with (
            patch("sys.argv", ["ll-config", "get", "totally.made.up.path"]),
            patch("little_loops.config.BRConfig", return_value=mock_cfg),
        ):
            assert main_config() == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Warning:" in captured.err
        assert "'totally'" in captured.err
        assert "not a known config section" in captured.err
        assert "totally.made.up.path" in captured.err

    def test_valid_root_unset_leaf_stays_silent(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_cfg = MagicMock()
        mock_cfg.resolve_variable.return_value = None
        mock_cfg.to_dict.return_value = {"project": {"name": "little-loops"}}
        with (
            patch("sys.argv", ["ll-config", "get", "project.nonexistent_key"]),
            patch("little_loops.config.BRConfig", return_value=mock_cfg),
        ):
            assert main_config() == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_known_key_prints_value_with_no_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_cfg = MagicMock()
        mock_cfg.resolve_variable.return_value = "little-loops"
        with (
            patch("sys.argv", ["ll-config", "get", "project.name"]),
            patch("little_loops.config.BRConfig", return_value=mock_cfg),
        ):
            assert main_config() == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "little-loops"
        assert captured.err == ""

    def test_construction_error_emits_no_warning(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with (
            patch("sys.argv", ["ll-config", "get", "totally.made.up.path"]),
            patch("little_loops.config.BRConfig", side_effect=Exception("boom")),
        ):
            assert main_config() == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_install_source_and_dollar_schema_emit_no_warning(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # install_source / $schema are real top-level config keys deliberately
        # excluded from to_dict() (provenance stamps, not user-tunable config).
        mock_cfg = MagicMock()
        mock_cfg.resolve_variable.return_value = None
        mock_cfg.to_dict.return_value = {"project": {}}
        for key in ("install_source", "$schema"):
            with (
                patch("sys.argv", ["ll-config", "get", key]),
                patch("little_loops.config.BRConfig", return_value=mock_cfg),
            ):
                assert main_config() == 0
            captured = capsys.readouterr()
            assert captured.out == ""
            assert captured.err == "", f"unexpected warning for {key!r}: {captured.err!r}"

    def test_exactly_one_brconfig_constructed_per_invocation(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_cfg = MagicMock()
        mock_cfg.resolve_variable.return_value = None
        mock_cfg.to_dict.return_value = {}
        with (
            patch("sys.argv", ["ll-config", "get", "totally.made.up.path"]),
            patch("little_loops.config.BRConfig", return_value=mock_cfg) as mock_ctor,
        ):
            assert main_config() == 0
        mock_ctor.assert_called_once()

    def test_every_to_dict_key_is_a_known_root(self, capsys: pytest.CaptureFixture[str]) -> None:
        from little_loops.config import BRConfig

        real_to_dict = BRConfig(Path.cwd()).to_dict()
        mock_cfg = MagicMock()
        mock_cfg.resolve_variable.return_value = None
        mock_cfg.to_dict.return_value = real_to_dict
        for root in real_to_dict:
            with (
                patch("sys.argv", ["ll-config", "get", f"{root}.__nonexistent_leaf__"]),
                patch("little_loops.config.BRConfig", return_value=mock_cfg),
            ):
                assert main_config() == 0
            err = capsys.readouterr().err
            assert err == "", f"to_dict() root {root!r} unexpectedly warned: {err!r}"

    def test_every_schema_top_level_property_is_a_known_root(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.init.core import _load_schema

        schema_roots = list(_load_schema().get("properties", {}).keys())
        assert schema_roots, "config-schema.json declares no top-level properties"

        mock_cfg = MagicMock()
        mock_cfg.resolve_variable.return_value = None
        mock_cfg.to_dict.return_value = {}
        for root in schema_roots:
            with (
                patch("sys.argv", ["ll-config", "get", f"{root}.__nonexistent_leaf__"]),
                patch("little_loops.config.BRConfig", return_value=mock_cfg),
            ):
                assert main_config() == 0
            err = capsys.readouterr().err
            assert err == "", f"schema root {root!r} unexpectedly warned: {err!r}"
