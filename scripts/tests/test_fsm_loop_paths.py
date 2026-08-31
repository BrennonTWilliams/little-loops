"""Tests for little_loops.fsm.loop_paths (ENH-2773)."""

from __future__ import annotations

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


def test_resolve_loop_path_error_enumerates_candidates_tried(tmp_path):
    with pytest.raises(FileNotFoundError) as exc_info:
        resolve_loop_path("nope", tmp_path)

    message = str(exc_info.value)
    assert str(tmp_path / "nope.fsm.yaml") in message
    assert str(tmp_path / "nope.yaml") in message
    assert str(tmp_path / "runs" / "nope" / "workflow.yaml") in message


def test_cli_helpers_reexports_resolve_loop_path_and_builtin_dir():
    from little_loops.cli.loop import _helpers

    assert _helpers.resolve_loop_path is resolve_loop_path
    assert _helpers.get_builtin_loops_dir is get_builtin_loops_dir


# ---------------------------------------------------------------------------
# BUG-3367: workflow-generator draft resolution fallbacks
# ---------------------------------------------------------------------------


def test_resolve_loop_path_resolves_instance_folder_name(tmp_path):
    run_dir = tmp_path / "runs" / "workflow-generator-20260830T220024"
    run_dir.mkdir(parents=True)
    workflow = run_dir / "workflow.yaml"
    workflow.write_text("name: sample-brand-kit-synth\ninitial: done\nstates: {done: {}}\n")

    resolved = resolve_loop_path("workflow-generator-20260830T220024", tmp_path)

    assert resolved == workflow


def test_resolve_loop_path_resolves_internal_name_scan(tmp_path):
    run_dir = tmp_path / "runs" / "workflow-generator-20260830T220024"
    run_dir.mkdir(parents=True)
    workflow = run_dir / "workflow.yaml"
    workflow.write_text("name: sample-brand-kit-synth\ninitial: done\nstates: {done: {}}\n")

    resolved = resolve_loop_path("sample-brand-kit-synth", tmp_path)

    assert resolved == workflow


def test_resolve_loop_path_internal_name_scan_dedups_to_latest_mtime(tmp_path, capsys):
    old_dir = tmp_path / "runs" / "workflow-generator-old"
    old_dir.mkdir(parents=True)
    old_workflow = old_dir / "workflow.yaml"
    old_workflow.write_text("name: dup-name\ninitial: done\nstates: {done: {}}\n")

    new_dir = tmp_path / "runs" / "workflow-generator-new"
    new_dir.mkdir(parents=True)
    new_workflow = new_dir / "workflow.yaml"
    new_workflow.write_text("name: dup-name\ninitial: done\nstates: {done: {}}\n")

    import os
    import time

    now = time.time()
    os.utime(old_workflow, (now - 100, now - 100))
    os.utime(new_workflow, (now, now))

    resolved = resolve_loop_path("dup-name", tmp_path)

    assert resolved == new_workflow
    assert "dup-name" in capsys.readouterr().err


def test_resolve_loop_path_existing_checks_take_priority_over_draft_fallback(tmp_path):
    (tmp_path / "my-loop.yaml").write_text("states: {}\n")
    run_dir = tmp_path / "runs" / "my-loop"
    run_dir.mkdir(parents=True)
    (run_dir / "workflow.yaml").write_text("name: my-loop\ninitial: done\nstates: {done: {}}\n")

    resolved = resolve_loop_path("my-loop", tmp_path)

    assert resolved == tmp_path / "my-loop.yaml"
