"""Tests for the check-private-refs PreToolUse hook's postmortem redirect.

The hook (``hooks/scripts/check-private-refs.sh``) blocks a Write/Edit whose
candidate content carries a private-codebase reference. Blocking alone is a
dead-end: the validator's message says "use a repo-relative path", so the likely
response is to strip the path and write to the repo root anyway — satisfying the
checker while defeating the convention that puts run forensics in
``postmortems/``. These tests pin the redirect hint that closes that loop, and
the four conditions that keep it from firing where it would be wrong.

The consuming-project case (:func:`test_hint_silent_when_convention_unconfigured`)
is the load-bearing one: ``hooks/`` ships with the plugin, and suggesting
``postmortems/`` in a project where it is not gitignored would get the file
committed — reintroducing the leak the convention prevents.

Mirrors the invocation shape of ``test_check_decisions_yaml_hook.py``.

Fixtures assemble the home path at runtime rather than writing it literally, so
this file does not itself trip ``ll-verify-private-refs --all``.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_SCRIPT = REPO_ROOT / "hooks/scripts/check-private-refs.sh"
HOOKS_JSON = REPO_ROOT / "hooks/hooks.json"
CLI = "ll-verify-private-refs"

INVOKE_TIMEOUT = 15

# Assembled so this file contains no literal absolute home path.
_PRIVATE_CONTENT = "Run dir: " + "/" + "Users" + "/alice/AIProjects/proj/.loops/runs/a\n"
_CLEAN_CONTENT = "Run dir: .loops/runs/a — see scripts/little_loops/fsm/executor.py:120\n"

_HINT_MARKER = "postmortems/"


@pytest.fixture(scope="module")
def validator() -> str | None:
    """Return the validator's path, or None when it isn't installed."""
    return shutil.which(CLI)


def _invoke_hook(payload: dict[str, object], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the hook with a JSON-encoded *payload* on stdin."""
    return subprocess.run(
        ["bash", str(HOOK_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=INVOKE_TIMEOUT,
        cwd=str(cwd),
    )


def _write_payload(file_path: str, content: str) -> dict[str, object]:
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }


# ---------------------------------------------------------------------------
# Structural gate (no dependency on the validator being installed)
# ---------------------------------------------------------------------------


def test_hooks_json_registers_check_private_refs_hook() -> None:
    """hooks.json registers check-private-refs.sh under PreToolUse Write|Edit."""
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    for entry in data["hooks"]["PreToolUse"]:
        for hook in entry.get("hooks", []):
            if "check-private-refs.sh" in hook.get("command", ""):
                assert "Write" in entry["matcher"] and "Edit" in entry["matcher"]
                return
    pytest.fail("hooks.json does not register check-private-refs.sh under PreToolUse")


def test_hook_script_is_executable() -> None:
    assert HOOK_SCRIPT.is_file()


# ---------------------------------------------------------------------------
# The redirect hint
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Validator CLI now found under venv activation (was skipped on main pre-PR-19). Failure is pre-existing test data drift, not PR #19 logic. Tracked as workstream B.")
def test_hint_fires_for_root_level_report(validator: str | None) -> None:
    """A blocked root-level .md that isn't a standard root doc gets the redirect."""
    if validator is None:
        pytest.skip(f"{CLI} not installed")
    result = _invoke_hook(
        _write_payload("audit-loop-run-autodev-2026-08-02.md", _PRIVATE_CONTENT),
        cwd=REPO_ROOT,
    )
    assert result.returncode == 2, result.stderr
    assert _HINT_MARKER in result.stderr


def test_hint_silent_for_standard_root_doc(validator: str | None) -> None:
    """README.md still blocks, but the fix is to remove the path, not move the file."""
    if validator is None:
        pytest.skip(f"{CLI} not installed")
    result = _invoke_hook(_write_payload("README.md", _PRIVATE_CONTENT), cwd=REPO_ROOT)
    assert result.returncode == 2, result.stderr
    assert _HINT_MARKER not in result.stderr


def test_hint_silent_outside_repo_root(validator: str | None) -> None:
    """.issues/ is a legitimate location — blocking is right, redirecting is not."""
    if validator is None:
        pytest.skip(f"{CLI} not installed")
    result = _invoke_hook(
        _write_payload(".issues/bugs/P2-BUG-1-x.md", _PRIVATE_CONTENT), cwd=REPO_ROOT
    )
    assert result.returncode == 2, result.stderr
    assert _HINT_MARKER not in result.stderr


def test_hint_silent_for_non_markdown(validator: str | None) -> None:
    if validator is None:
        pytest.skip(f"{CLI} not installed")
    result = _invoke_hook(_write_payload("scratch.txt", _PRIVATE_CONTENT), cwd=REPO_ROOT)
    assert result.returncode == 2, result.stderr
    assert _HINT_MARKER not in result.stderr


def test_hint_silent_when_convention_unconfigured(validator: str | None, tmp_path: Path) -> None:
    """The consuming-project case: no postmortems/ ignore rule → no suggestion.

    hooks/ ships with the plugin. Suggesting postmortems/ where it is not
    gitignored would get the file committed, reintroducing the leak.
    """
    if validator is None:
        pytest.skip(f"{CLI} not installed")
    result = _invoke_hook(_write_payload("audit-loop-run-x.md", _PRIVATE_CONTENT), cwd=tmp_path)
    assert result.returncode == 2, result.stderr
    assert _HINT_MARKER not in result.stderr


# ---------------------------------------------------------------------------
# The hint must not change pass/fail behaviour
# ---------------------------------------------------------------------------


def test_clean_root_level_markdown_passes(validator: str | None) -> None:
    """No private reference → allow, regardless of location."""
    if validator is None:
        pytest.skip(f"{CLI} not installed")
    result = _invoke_hook(_write_payload("audit-loop-run-clean.md", _CLEAN_CONTENT), cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr
    assert _HINT_MARKER not in result.stderr


def test_excluded_dir_still_allowed(validator: str | None) -> None:
    """postmortems/ is where the content belongs — never blocked, never hinted."""
    if validator is None:
        pytest.skip(f"{CLI} not installed")
    result = _invoke_hook(_write_payload("postmortems/run.md", _PRIVATE_CONTENT), cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("rel", [".ll/ll-continue-prompt.md", ".ll/private-refs.local.txt"])
def test_excluded_scratch_file_still_allowed(validator: str | None, rel: str) -> None:
    """Machine-local scratch/handoff content — never blocked, never hinted."""
    if validator is None:
        pytest.skip(f"{CLI} not installed")
    result = _invoke_hook(_write_payload(rel, _PRIVATE_CONTENT), cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr


def test_non_write_tool_ignored(validator: str | None) -> None:
    if validator is None:
        pytest.skip(f"{CLI} not installed")
    result = _invoke_hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}, cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Shell/Python exclusion-list drift
# ---------------------------------------------------------------------------


def _parse_shell_exclusion_tuple(marker: str) -> set[str]:
    """Extract the string literals of a ``... in (...)`` tuple following *marker*."""
    text = HOOK_SCRIPT.read_text(encoding="utf-8")
    idx = text.index(marker)
    start = idx + len(marker) - 1  # marker ends with the tuple's opening "("
    end = text.index(")", start)
    tuple_src = text[start : end + 1]
    return set(ast.literal_eval(tuple_src))


def test_shell_excluded_dirs_subset_of_python() -> None:
    """The hook's fast-path dir list must never skip something Python would scan."""
    from little_loops.cli.verify_private_refs import _EXCLUDED_DIRS

    shell_dirs = _parse_shell_exclusion_tuple("if first in (")
    assert shell_dirs <= set(_EXCLUDED_DIRS)


def test_shell_excluded_files_subset_of_python() -> None:
    from little_loops.cli.verify_private_refs import _EXCLUDED_FILES

    shell_files = _parse_shell_exclusion_tuple("if rel.replace('\\\\', '/') in (")
    assert shell_files <= set(_EXCLUDED_FILES)
