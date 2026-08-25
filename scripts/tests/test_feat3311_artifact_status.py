"""Tests for FEAT-3311 Phase 3: `ll-artifact status` + lockfile staleness detection."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.artifact.lockfile import write_lockfile
from little_loops.cli.artifact.render import cmd_render
from little_loops.cli.artifact.status import (
    StatusResult,
    _exit_code_for,
    cmd_status,
)
from little_loops.logger import Logger

_FIXTURES = Path(__file__).parent / "fixtures" / "artifact_templates"


def _make_config(project_root: Path, artifacts_extra: dict | None = None):
    from little_loops.config.core import BRConfig

    config_dir = project_root / ".ll"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if artifacts_extra:
        cfg["artifacts"] = artifacts_extra
    (config_dir / "ll-config.json").write_text(json.dumps(cfg))
    return BRConfig(project_root)


def _copy_fixture(name: str, dest: Path) -> Path:
    target = dest / f"{name}.llat"
    shutil.copytree(_FIXTURES / f"{name}.llat", target)
    return target


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# _exit_code_for
# ---------------------------------------------------------------------------


class TestExitCodeFor:
    def test_empty_list_is_zero(self) -> None:
        assert _exit_code_for([]) == 0

    def test_all_fresh_is_zero(self) -> None:
        results = [StatusResult("t", "s1", "FRESH"), StatusResult("t", "s2", "FRESH")]
        assert _exit_code_for(results) == 0

    @pytest.mark.parametrize("state", ["STALE", "SOURCE-MISSING", "OUTPUT-MISSING", "NO-LOCK"])
    def test_any_non_fresh_is_one(self, state: str) -> None:
        results = [StatusResult("t", "s1", "FRESH"), StatusResult("t", "s2", state)]
        assert _exit_code_for(results) == 1


# ---------------------------------------------------------------------------
# cmd_status: five-state classification, end to end
# ---------------------------------------------------------------------------


class TestCmdStatus:
    def _setup_template(self, tmp_path: Path) -> tuple[Path, Path]:
        """Copy the `simple` fixture and a source doc into tmp_path, return (root, source)."""
        root = _copy_fixture("simple", tmp_path)
        source = tmp_path / "docs" / "risk-register.md"
        source.parent.mkdir(parents=True)
        source.write_text("Q3 risk register v1")
        return root, source

    def _write_lock(self, root: Path, source: Path, tmp_path: Path, output: Path) -> None:
        from little_loops.cli.artifact.lockfile import lock_path_for, relativize_path

        write_lockfile(
            lock_path_for(root),
            {
                relativize_path(source, tmp_path): {
                    "sha256": _sha256(source),
                    "rendered_at": "2026-08-25T04:12:33Z",
                    "output": relativize_path(output, tmp_path),
                }
            },
        )

    def test_fresh(self, tmp_path: Path, capsys) -> None:
        root, source = self._setup_template(tmp_path)
        _make_config(tmp_path)
        out_file = tmp_path / "out" / "report.html"
        out_file.parent.mkdir(parents=True)
        out_file.write_text("rendered")
        self._write_lock(root, source, tmp_path, out_file)

        args = argparse.Namespace(template=[str(root)])
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_status(args, Logger(use_color=False, verbose=True))
        assert code == 0

    def test_stale(self, tmp_path: Path) -> None:
        root, source = self._setup_template(tmp_path)
        _make_config(tmp_path)
        out_file = tmp_path / "out" / "report.html"
        out_file.parent.mkdir(parents=True)
        out_file.write_text("rendered")
        self._write_lock(root, source, tmp_path, out_file)

        source.write_text("Q3 risk register v2 -- changed")

        args = argparse.Namespace(template=[str(root)])
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_status(args, Logger(use_color=False, verbose=True))
        assert code == 1

    def test_source_missing(self, tmp_path: Path) -> None:
        root, source = self._setup_template(tmp_path)
        _make_config(tmp_path)
        out_file = tmp_path / "out" / "report.html"
        out_file.parent.mkdir(parents=True)
        out_file.write_text("rendered")
        self._write_lock(root, source, tmp_path, out_file)

        source.unlink()

        args = argparse.Namespace(template=[str(root)])
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_status(args, Logger(use_color=False, verbose=True))
        assert code == 1

    def test_output_missing(self, tmp_path: Path) -> None:
        """Delete the rendered artifact, leave the source untouched -> OUTPUT-MISSING."""
        root, source = self._setup_template(tmp_path)
        _make_config(tmp_path)
        out_file = tmp_path / "out" / "report.html"
        out_file.parent.mkdir(parents=True)
        out_file.write_text("rendered")
        self._write_lock(root, source, tmp_path, out_file)

        out_file.unlink()

        args = argparse.Namespace(template=[str(root)])
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_status(args, Logger(use_color=False, verbose=True))
        assert code == 1

    def test_no_lock_missing_lockfile(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        _make_config(tmp_path)

        args = argparse.Namespace(template=[str(root)])
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_status(args, Logger(use_color=False, verbose=True))
        assert code == 1

    def test_no_lock_empty_renders(self, tmp_path: Path) -> None:
        from little_loops.cli.artifact.lockfile import lock_path_for

        root = _copy_fixture("simple", tmp_path)
        _make_config(tmp_path)
        write_lockfile(lock_path_for(root), {})

        args = argparse.Namespace(template=[str(root)])
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_status(args, Logger(use_color=False, verbose=True))
        assert code == 1

    def test_malformed_lockfile_exits_1_not_a_state(self, tmp_path: Path) -> None:
        from little_loops.cli.artifact.lockfile import lock_path_for

        root = _copy_fixture("simple", tmp_path)
        _make_config(tmp_path)
        lock_path_for(root).write_text("not: [valid, yaml: structure")

        args = argparse.Namespace(template=[str(root)])
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_status(args, Logger(use_color=False, verbose=True))
        assert code == 1


# ---------------------------------------------------------------------------
# Discovery mode
# ---------------------------------------------------------------------------


class TestCmdStatusDiscovery:
    def test_skips_lockfile_less_templates(self, tmp_path: Path) -> None:
        templates_dir = tmp_path / "artifacts" / "templates"
        templates_dir.mkdir(parents=True)
        tracked = templates_dir / "tracked.llat"
        shutil.copytree(_FIXTURES / "simple.llat", tracked)
        untracked = templates_dir / "untracked.llat"
        shutil.copytree(_FIXTURES / "simple.llat", untracked)

        _make_config(tmp_path)

        source = tmp_path / "docs" / "src.md"
        source.parent.mkdir(parents=True)
        source.write_text("v1")
        out_file = tmp_path / "out" / "report.html"
        out_file.parent.mkdir(parents=True)
        out_file.write_text("rendered")

        from little_loops.cli.artifact.lockfile import lock_path_for, relativize_path

        write_lockfile(
            lock_path_for(tracked),
            {
                relativize_path(source, tmp_path): {
                    "sha256": _sha256(source),
                    "rendered_at": "2026-08-25T04:12:33Z",
                    "output": relativize_path(out_file, tmp_path),
                }
            },
        )

        args = argparse.Namespace(template=[])
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_status(args, Logger(use_color=False, verbose=True))
        # Only the tracked (FRESH) template is reported; untracked is skipped, not NO-LOCK.
        assert code == 0

    def test_empty_templates_dir_exits_zero_and_logs(self, tmp_path: Path) -> None:
        _make_config(tmp_path)
        args = argparse.Namespace(template=[])
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_status(args, Logger(use_color=False, verbose=True))
        assert code == 0


# ---------------------------------------------------------------------------
# Path resolution: subdirectory cwd, out-of-root absolute source
# ---------------------------------------------------------------------------


class TestPathResolution:
    def test_relative_entries_resolve_against_project_root_not_cwd(self, tmp_path: Path) -> None:
        """Unit-level: `_classify_entries`/`_resolve_stored` must key off the *project_root*
        argument, never `Path.cwd()` — the exact property that makes `status` invoked from a
        project subdirectory still resolve entries it wrote itself. `BRConfig` itself has no
        upward-search from cwd (each CLI entry point takes `Path.cwd()` as the literal project
        root today), so this is exercised at the classification-function level rather than by
        mocking `Path.cwd()` to a subdirectory and expecting `cmd_status`'s own `BRConfig(
        Path.cwd())` call to find a config file it was never pointed at.
        """
        from little_loops.cli.artifact.status import _classify_entries

        project_root = tmp_path / "project"
        project_root.mkdir()
        source = project_root / "docs" / "risk-register.md"
        source.parent.mkdir(parents=True)
        source.write_text("v1")
        out_file = project_root / "out" / "report.html"
        out_file.parent.mkdir(parents=True)
        out_file.write_text("rendered")

        renders = {
            "docs/risk-register.md": {
                "sha256": _sha256(source),
                "output": "out/report.html",
            }
        }

        # Simulate an unrelated cwd (a subdirectory) to prove classification never
        # consults it: no `Path.cwd` patching is installed for this call at all, so if
        # the implementation ever read cwd instead of project_root it would use the
        # real test-runner cwd and fail to resolve these relative entries.
        results = _classify_entries("simple.llat", renders, project_root)
        assert len(results) == 1
        assert results[0].state == "FRESH"

    def test_out_of_root_absolute_source(self, tmp_path: Path) -> None:
        project_root = tmp_path / "project"
        project_root.mkdir()
        root = _copy_fixture("simple", project_root)
        _make_config(project_root)

        outside = tmp_path / "outside"
        outside.mkdir()
        source = outside / "src.md"
        source.write_text("v1")
        out_file = project_root / "out" / "report.html"
        out_file.parent.mkdir(parents=True)
        out_file.write_text("rendered")

        from little_loops.cli.artifact.lockfile import lock_path_for, relativize_path

        write_lockfile(
            lock_path_for(root),
            {
                str(source.resolve()): {
                    "sha256": _sha256(source),
                    "rendered_at": "2026-08-25T04:12:33Z",
                    "output": relativize_path(out_file, project_root),
                }
            },
        )

        args = argparse.Namespace(template=[str(root)])
        with patch("pathlib.Path.cwd", return_value=project_root):
            code = cmd_status(args, Logger(use_color=False, verbose=True))
        assert code == 0


# ---------------------------------------------------------------------------
# render --source
# ---------------------------------------------------------------------------


class TestRenderSource:
    def test_missing_source_exits_1_no_artifact_written(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        _make_config(tmp_path)
        out_dir = tmp_path / "out"
        args = argparse.Namespace(
            template=str(root),
            data=None,
            output=str(out_dir),
            source="does/not/exist.md",
        )
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_render(args, Logger(use_color=False, verbose=True))
        assert code == 1
        assert not out_dir.exists()

    def test_writes_correct_lockfile_entry(self, tmp_path: Path) -> None:
        from little_loops.cli.artifact.lockfile import load_lockfile, lock_path_for

        root = _copy_fixture("simple", tmp_path)
        _make_config(tmp_path)
        source = tmp_path / "docs" / "risk-register.md"
        source.parent.mkdir(parents=True)
        source.write_text("Q3 risk register")
        out_dir = tmp_path / "out"

        args = argparse.Namespace(
            template=str(root),
            data=None,
            output=str(out_dir),
            source=str(source),
        )
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_render(args, Logger(use_color=False, verbose=True))
        assert code == 0

        lock_data = load_lockfile(lock_path_for(root))
        entry = lock_data["renders"]["docs/risk-register.md"]
        assert entry["sha256"] == _sha256(source)
        assert entry["output"] == "out/report.html"
        assert entry["rendered_at"].endswith("Z")

    def test_bare_render_writes_no_lockfile(self, tmp_path: Path) -> None:
        from little_loops.cli.artifact.lockfile import lock_path_for

        root = _copy_fixture("simple", tmp_path)
        _make_config(tmp_path)
        out_dir = tmp_path / "out"
        args = argparse.Namespace(template=str(root), data=None, output=str(out_dir))
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_render(args, Logger(use_color=False, verbose=True))
        assert code == 0
        assert not lock_path_for(root).exists()
