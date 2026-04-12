"""Tests for cli/create_extension.py - ll-create-extension CLI entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from little_loops.cli.create_extension import main_create_extension


class TestMainCreateExtensionDryRun:
    """Tests for ll-create-extension --dry-run mode."""

    def test_dry_run_returns_0(self) -> None:
        """Returns 0 in dry-run mode when target does not exist."""
        with (
            patch("sys.argv", ["ll-create-extension", "my-ext", "--dry-run"]),
            patch("little_loops.cli.create_extension._target_exists", return_value=False),
            patch("little_loops.cli.create_extension._get_cwd", return_value=Path("/fake")),
        ):
            result = main_create_extension()
        assert result == 0

    def test_dry_run_existing_target_returns_1(self) -> None:
        """Returns 1 when target directory already exists, even in dry-run mode."""
        with (
            patch("sys.argv", ["ll-create-extension", "my-ext", "--dry-run"]),
            patch("little_loops.cli.create_extension._target_exists", return_value=True),
            patch("little_loops.cli.create_extension._get_cwd", return_value=Path("/fake")),
        ):
            result = main_create_extension()
        assert result == 1

    def test_dry_run_does_not_write_files(self) -> None:
        """Dry-run mode never calls _write_scaffold."""
        with (
            patch("sys.argv", ["ll-create-extension", "my-ext", "--dry-run"]),
            patch("little_loops.cli.create_extension._target_exists", return_value=False),
            patch("little_loops.cli.create_extension._get_cwd", return_value=Path("/fake")),
            patch("little_loops.cli.create_extension._write_scaffold") as mock_write,
        ):
            main_create_extension()
        mock_write.assert_not_called()


class TestMainCreateExtensionApply:
    """Tests for ll-create-extension apply mode (no --dry-run)."""

    def test_apply_returns_0_on_success(self) -> None:
        """Returns 0 when scaffold is created successfully."""
        with (
            patch("sys.argv", ["ll-create-extension", "my-ext"]),
            patch("little_loops.cli.create_extension._target_exists", return_value=False),
            patch("little_loops.cli.create_extension._get_cwd", return_value=Path("/fake")),
            patch("little_loops.cli.create_extension._write_scaffold"),
        ):
            result = main_create_extension()
        assert result == 0

    def test_existing_target_returns_1(self) -> None:
        """Returns 1 when target directory already exists."""
        with (
            patch("sys.argv", ["ll-create-extension", "my-ext"]),
            patch("little_loops.cli.create_extension._target_exists", return_value=True),
            patch("little_loops.cli.create_extension._get_cwd", return_value=Path("/fake")),
        ):
            result = main_create_extension()
        assert result == 1

    def test_apply_calls_write_scaffold(self) -> None:
        """Calls _write_scaffold with correct target and four scaffold files."""
        with (
            patch("sys.argv", ["ll-create-extension", "my-ext"]),
            patch("little_loops.cli.create_extension._target_exists", return_value=False),
            patch("little_loops.cli.create_extension._get_cwd", return_value=Path("/fake")),
            patch("little_loops.cli.create_extension._write_scaffold") as mock_write,
        ):
            main_create_extension()
        mock_write.assert_called_once()
        target_arg, files_arg = mock_write.call_args[0]
        assert target_arg == Path("/fake/my-ext")
        assert len(files_arg) == 4

    def test_apply_scaffolds_correct_paths(self) -> None:
        """Scaffolded files have expected paths relative to target."""
        with (
            patch("sys.argv", ["ll-create-extension", "my-ext"]),
            patch("little_loops.cli.create_extension._target_exists", return_value=False),
            patch("little_loops.cli.create_extension._get_cwd", return_value=Path("/fake")),
            patch("little_loops.cli.create_extension._write_scaffold") as mock_write,
        ):
            main_create_extension()
        _, files_arg = mock_write.call_args[0]
        paths = {str(p.relative_to(Path("/fake/my-ext"))) for p in files_arg}
        assert paths == {
            "pyproject.toml",
            "my_ext/__init__.py",
            "my_ext/extension.py",
            "tests/test_extension.py",
        }

    def test_extension_py_contains_event_schema_comment(self) -> None:
        """Generated extension.py includes link to EVENT-SCHEMA.md."""
        with (
            patch("sys.argv", ["ll-create-extension", "my-ext"]),
            patch("little_loops.cli.create_extension._target_exists", return_value=False),
            patch("little_loops.cli.create_extension._get_cwd", return_value=Path("/fake")),
            patch("little_loops.cli.create_extension._write_scaffold") as mock_write,
        ):
            main_create_extension()
        _, files_arg = mock_write.call_args[0]
        ext_content = next(v for k, v in files_arg.items() if k.name == "extension.py")
        assert "docs/reference/EVENT-SCHEMA.md" in ext_content

    def test_pyproject_has_entry_point(self) -> None:
        """Generated pyproject.toml includes little_loops.extensions entry point."""
        with (
            patch("sys.argv", ["ll-create-extension", "my-ext"]),
            patch("little_loops.cli.create_extension._target_exists", return_value=False),
            patch("little_loops.cli.create_extension._get_cwd", return_value=Path("/fake")),
            patch("little_loops.cli.create_extension._write_scaffold") as mock_write,
        ):
            main_create_extension()
        _, files_arg = mock_write.call_args[0]
        pyproject_content = next(v for k, v in files_arg.items() if k.name == "pyproject.toml")
        assert '[project.entry-points."little_loops.extensions"]' in pyproject_content

    def test_test_file_uses_lltestbus(self) -> None:
        """Generated test file includes LLTestBus example."""
        with (
            patch("sys.argv", ["ll-create-extension", "my-ext"]),
            patch("little_loops.cli.create_extension._target_exists", return_value=False),
            patch("little_loops.cli.create_extension._get_cwd", return_value=Path("/fake")),
            patch("little_loops.cli.create_extension._write_scaffold") as mock_write,
        ):
            main_create_extension()
        _, files_arg = mock_write.call_args[0]
        test_content = next(v for k, v in files_arg.items() if k.name == "test_extension.py")
        assert "LLTestBus" in test_content
