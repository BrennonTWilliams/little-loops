"""ENH-3281: generalized this-repo-hardcode gate across all built-in loops.

BUG-3276 fixed one built-in loop (``incremental-refactor.yaml``) that hardcoded
this repo's own test path as a bare ``context.test_cmd`` default. That is a
class of defect, not a one-off: any built-in loop shipped to consuming
projects (``.claude/CLAUDE.md`` § Distribution) can hardcode a this-repo path
in exec-time content — a state's ``action`` body or a top-level ``context:``
default — and it will run silently wrong everywhere but here. This module
promotes the single-loop assertion in
``test_builtin_loops.py::TestIncrementalRefactorLoop::test_no_state_hardcodes_this_repo_test_path``
to a parametrized gate over every built-in loop file.

Scope is deliberately narrow: ``states[*].action`` bodies and top-level
``context:`` values only. ``scope:`` list entries, ``description:`` fields,
``#`` comments, and ``states[*].evaluate.prompt``/``.source`` are excluded —
not exec-time content in the same way (see the issue's Scope Boundaries /
Decision Rules for the full reasoning). The match pattern set is the survey
grep, not a definition of the defect class: a bare ``scripts/`` does not
match. The one instance (``dead-code-cleanup.yaml``'s
``scope: ["scripts/"]``) was fixed by ENH-3292; ``scope:`` entries remain
out of this gate's scope by design.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"

# Survey grep (re-verified 2026-08-22, see ENH-3281): scripts/tests,
# scripts/little_loops, ruff check scripts, mypy scripts. Narrow on purpose
# to keep false positives at zero on first landing.
_HARDCODE_PATTERNS = (
    "scripts/tests",
    "scripts/little_loops",
    "ruff check scripts",
    "mypy scripts",
)

# Exemption keys are repo-relative paths (matching test_bug3269's
# _relative()-keyed _EXEMPT), not basenames.
#
# cli-anything-bootstrap.yaml:453 — a package-internal task-template path
# inside a states[*].action body, not a consuming-project layout guess.
# Arguably should resolve via importlib.resources instead; that is a
# separate change.
#
# loop-specialist-eval.yaml:23 — a genuine this-repo eval fixture path
# (scripts/tests/fixtures/fsm/broken-verify-loop.yaml) in a top-level
# context: default. The loop only makes sense run against this repo.
_EXEMPT = {
    "cli-anything-bootstrap.yaml",
    "loop-specialist-eval.yaml",
}


def _hardcode_hits(text: str) -> list[str]:
    """Return the this-repo hardcode patterns found in one string, empty when clean."""
    return [pattern for pattern in _HARDCODE_PATTERNS if pattern in text]


def _scanned_strings(data: dict) -> Iterator[tuple[str, str]]:
    """Yield (location_label, text) for every in-scope string in one parsed loop.

    In scope: each states[*].action body and each top-level context: value.
    Guards non-string/absent action values (terminal states have none) and
    non-string context: values (ints, bools, and lists appear across the
    corpus).
    """
    states = data.get("states")
    if isinstance(states, dict):
        for state_name, state in states.items():
            if not isinstance(state, dict):
                continue
            action = state.get("action", "")
            if isinstance(action, str) and action:
                yield f"states.{state_name}.action", action

    context = data.get("context")
    if isinstance(context, dict):
        for key, value in context.items():
            if isinstance(value, str) and value:
                yield f"context.{key}", value


def _all_loop_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(BUILTIN_LOOPS_DIR.glob("**/*.yaml")):
        if any(part.startswith(".") for part in path.relative_to(BUILTIN_LOOPS_DIR).parts):
            continue
        files.append(path)
    return files


def _relative(path: Path) -> str:
    return str(path.relative_to(BUILTIN_LOOPS_DIR))


ALL_LOOP_FILES = _all_loop_files()


@pytest.mark.parametrize("loop_file", ALL_LOOP_FILES, ids=_relative)
def test_no_this_repo_hardcode(loop_file: Path) -> None:
    rel = _relative(loop_file)
    if rel in _EXEMPT:
        pytest.skip(f"{rel} is an exempted site — see module docstring")

    data: Any = yaml.safe_load(loop_file.read_text())
    if not isinstance(data, dict):
        return

    offenses = []
    for location, text in _scanned_strings(data):
        hits = _hardcode_hits(text)
        if hits:
            offenses.append(f"{location} contains {hits}")

    assert not offenses, (
        f"{rel} hardcodes this repo's own layout (ENH-3281 / BUG-3276): "
        f"{'; '.join(offenses)}. Built-in loops run unmodified against arbitrary "
        "consuming projects (.claude/CLAUDE.md § Distribution) — resolve project "
        "commands via context-first + `ll-config get`, never a bare this-repo literal."
    )


def test_hardcode_hits_detects_this_repo_path() -> None:
    """Negative test: _hardcode_hits() must fire on an inline hardcoded string.

    A fixture YAML cannot live under scripts/little_loops/loops/ — that
    directory is this gate's own parametrize corpus, so a fixture there would
    fail the gate instead of testing it (see ENH-3281 Integration Map).
    """
    assert _hardcode_hits('action: "python -m pytest scripts/tests/ -v"') == ["scripts/tests"]
    assert _hardcode_hits('action: "echo hello world"') == []


def test_permanent_exemptions_still_exist() -> None:
    """Guard against a stale exemption list: every listed file must exist,
    so a file rename or deletion doesn't leave a dangling entry behind."""
    for rel in _EXEMPT:
        assert (BUILTIN_LOOPS_DIR / rel).exists(), (
            f"_EXEMPT lists {rel!r}, which no longer exists under "
            f"{BUILTIN_LOOPS_DIR} — remove the dangling entry."
        )
