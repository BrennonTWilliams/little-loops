"""Tests for cli/config.py - ll-config CLI entry point."""

from __future__ import annotations

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
        mock_cfg.resolve_variable.assert_called_once_with(
            "history.go_no_go.correction_penalty"
        )

    def test_unknown_key_prints_nothing(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_cfg = MagicMock()
        mock_cfg.resolve_variable.return_value = None
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
