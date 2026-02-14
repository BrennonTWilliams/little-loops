"""Tests for cli/messages.py _save_combined helper."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from little_loops.cli.messages import _save_combined


class TestSaveCombined:
    """Tests for _save_combined helper."""

    def test_saves_to_explicit_path(self, tmp_path: Path) -> None:
        """Saves items to explicit output path."""
        output_file = tmp_path / "output.jsonl"
        items = [
            MagicMock(to_dict=lambda: {"msg": "hello", "ts": "2026-01-01"}),
            MagicMock(to_dict=lambda: {"msg": "world", "ts": "2026-01-02"}),
        ]

        result_path = _save_combined(items, output_file)

        assert result_path == output_file
        assert output_file.exists()
        lines = output_file.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["msg"] == "hello"
        assert json.loads(lines[1])["msg"] == "world"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Creates parent directories if they don't exist."""
        output_file = tmp_path / "subdir" / "deep" / "output.jsonl"
        items = [MagicMock(to_dict=lambda: {"msg": "test"})]

        result_path = _save_combined(items, output_file)

        assert result_path == output_file
        assert output_file.exists()

    def test_generates_default_path(self, tmp_path: Path) -> None:
        """Generates timestamped default path when no path given."""
        items = [MagicMock(to_dict=lambda: {"msg": "test"})]

        # Use tmp_path as working directory
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result_path = _save_combined(items)
        finally:
            os.chdir(original_cwd)

        assert result_path.exists()
        assert "user-messages-" in result_path.name
        assert result_path.suffix == ".jsonl"
        assert result_path.parent.name == ".claude"

    def test_empty_items_writes_empty_file(self, tmp_path: Path) -> None:
        """Empty items list creates an empty file."""
        output_file = tmp_path / "empty.jsonl"

        _save_combined([], output_file)

        assert output_file.exists()
        assert output_file.read_text() == ""
