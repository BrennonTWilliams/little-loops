"""Tests for atomic_write() in file_utils — ENH-1280."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.file_utils import atomic_write


class TestAtomicWrite:
    """Verify atomic_write() uses os.replace and leaves no orphaned tmp files."""

    def test_writes_content_to_target(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        atomic_write(target, "hello world")
        assert target.read_text() == "hello world"

    def test_uses_os_replace_exactly_once(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        replace_calls: list[tuple[str, str]] = []
        original_replace = os.replace

        def capture(src: str, dst: str) -> None:
            replace_calls.append((str(src), str(dst)))
            original_replace(src, dst)

        with patch("os.replace", side_effect=capture):
            atomic_write(target, "content")

        assert len(replace_calls) == 1, "os.replace must be called exactly once"
        assert Path(replace_calls[0][1]) == target

    def test_no_tmp_files_on_success(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        atomic_write(target, "content")
        assert list(tmp_path.glob("*.tmp")) == []

    def test_preserves_existing_file_on_replace_failure(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        target.write_text("original")

        with patch("os.replace", side_effect=OSError("simulated disk full")):
            with pytest.raises(OSError):
                atomic_write(target, "new content")

        assert target.read_text() == "original"

    def test_no_tmp_orphan_on_replace_failure(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        with patch("os.replace", side_effect=OSError("simulated disk full")):
            with pytest.raises(OSError):
                atomic_write(target, "content")
        assert list(tmp_path.glob("*.tmp")) == []

    def test_respects_encoding(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        content = "héllo wörld"
        atomic_write(target, content, encoding="utf-8")
        assert target.read_text(encoding="utf-8") == content

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        target.write_text("old")
        atomic_write(target, "new")
        assert target.read_text() == "new"
