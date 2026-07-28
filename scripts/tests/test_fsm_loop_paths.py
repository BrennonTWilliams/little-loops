"""Tests for little_loops.fsm.loop_paths (ENH-2773)."""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.fsm.loop_paths import get_builtin_loops_dir, resolve_loop_path


def test_get_builtin_loops_dir_resolves_to_bundled_loops():
    builtin_dir = get_builtin_loops_dir()
    assert builtin_dir.name == "loops"
    assert builtin_dir.parent.name == "little_loops"
    assert builtin_dir.is_dir()


def test_resolve_loop_path_literal_path_that_exists(tmp_path):
    loop_file = tmp_path / "some-loop.yaml"
    loop_file.write_text("states: {}\n")

    resolved = resolve_loop_path(str(loop_file), tmp_path)

    assert resolved == loop_file


def test_resolve_loop_path_fsm_yaml_in_loops_dir(tmp_path):
    (tmp_path / "my-loop.fsm.yaml").write_text("states: {}\n")

    resolved = resolve_loop_path("my-loop", tmp_path)

    assert resolved == tmp_path / "my-loop.fsm.yaml"


def test_resolve_loop_path_yaml_in_loops_dir(tmp_path):
    (tmp_path / "my-loop.yaml").write_text("states: {}\n")

    resolved = resolve_loop_path("my-loop", tmp_path)

    assert resolved == tmp_path / "my-loop.yaml"


def test_resolve_loop_path_falls_back_to_builtin(tmp_path):
    builtin_dir = get_builtin_loops_dir()
    builtin_names = [p.stem for p in builtin_dir.glob("*.yaml")]
    assert builtin_names, "expected at least one bundled built-in loop for this test"

    resolved = resolve_loop_path(builtin_names[0], tmp_path)

    assert resolved == builtin_dir / f"{builtin_names[0]}.yaml"


def test_resolve_loop_path_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_loop_path("definitely-does-not-exist-loop", tmp_path)


def test_cli_helpers_reexports_resolve_loop_path_and_builtin_dir():
    from little_loops.cli.loop import _helpers

    assert _helpers.resolve_loop_path is resolve_loop_path
    assert _helpers.get_builtin_loops_dir is get_builtin_loops_dir
