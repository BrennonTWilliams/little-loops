"""Tests for ll-next-id CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


class TestNextIdArgumentParsing:
    """Tests for ll-next-id argument parsing."""

    def _parse_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_next_id."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--config", type=Path, default=None)
        return parser.parse_args(args)

    def test_default_args(self) -> None:
        """Default values when no arguments provided."""
        args = self._parse_args([])
        assert args.config is None

    def test_config_flag(self) -> None:
        """Test --config flag."""
        args = self._parse_args(["--config", "/custom/path"])
        assert args.config == Path("/custom/path")


class TestMainNextIdIntegration:
    """Integration tests for main_next_id entry point."""

    def test_empty_project(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with empty issue directories returns 001."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)

        with patch.object(sys, "argv", ["ll-next-id", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_next_id

            result = main_next_id()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "001"

    def test_with_existing_issues(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with existing issues returns correct next number."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        features_dir = temp_project_dir / ".issues" / "features"
        bugs_dir.mkdir(parents=True)
        features_dir.mkdir(parents=True)

        (bugs_dir / "P0-BUG-003-test.md").write_text("# BUG-003")
        (features_dir / "P2-FEAT-007-test.md").write_text("# FEAT-007")

        with patch.object(sys, "argv", ["ll-next-id", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_next_id

            result = main_next_id()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "008"

    def test_three_digit_padding(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that output is zero-padded to 3 digits."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        (bugs_dir / "P1-BUG-042-test.md").write_text("# BUG-042")

        with patch.object(sys, "argv", ["ll-next-id", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_next_id

            result = main_next_id()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "043"
