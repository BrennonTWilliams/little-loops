"""Static interpolation guard for builtin loop YAMLs.

The FSM template engine (``little_loops.fsm.interpolation.interpolate``) does a
whole-body regex pass over every action string and rejects any ``${...}``
reference that is not a valid ``namespace.path`` (or escaped as ``$${...}``).
A bare shell variable such as ``${COMMIT_EVERY}`` therefore crashes the *entire*
state at parse time, regardless of which shell branch would actually run.

Regression context: ``recursive-refine.yaml`` shipped a bare
``echo "...${COMMIT_EVERY}..."`` on 2026-06-13 (commit 176fe300) that crashed
``parse_input`` on *every* invocation — breaking recursive-refine and its three
callers (auto-refine-and-implement, sprint-refine-and-implement,
issue-refinement) for ~2 weeks. ``ll-loop validate`` reported the loop "valid"
and the full suite passed because nothing interpolated action bodies against the
real engine. This test closes that gap: it runs every builtin loop's action and
evaluate strings through ``interpolate()`` so a bare ``${VAR}`` fails CI.

The check is grammar-only: a stub context returns ``""`` for any well-formed
``namespace.path`` (so missing values are *not* errors) but lets the engine's
"expected namespace.path" grammar error and unknown-namespace error surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from little_loops.fsm.interpolation import (
    InterpolationContext,
    InterpolationError,
    interpolate,
)

LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"

# Namespaces the engine knows how to resolve. A reference into any other
# namespace is a genuine authoring error and should fail this guard.
KNOWN_NAMESPACES = {
    "context",
    "captured",
    "prev",
    "result",
    "state",
    "loop",
    "env",
    "messages",
    "param",
}


class _PermissiveContext(InterpolationContext):
    """Resolve any well-formed reference to "" so only grammar/namespace errors surface.

    We do not care whether ``context.foo`` actually has a value here — only that
    the reference is *shaped* correctly. Returning "" for every known namespace
    suppresses missing-value noise while preserving the engine's grammar check
    (raised before ``resolve`` is ever called) and unknown-namespace check.
    """

    def resolve(self, namespace: str, path: str) -> Any:  # noqa: D102
        if namespace not in KNOWN_NAMESPACES:
            raise InterpolationError(f"Unknown namespace: {namespace}")
        return ""


def _builtin_loop_files() -> list[Path]:
    """Every runnable builtin loop YAML (including oracles/ and lib/ fragments).

    Excludes runtime artifact dirs (.history/, .running/) which contain captured
    event logs, not loop definitions.
    """
    files: list[Path] = []
    for path in sorted(LOOPS_DIR.rglob("*.yaml")):
        if any(part.startswith(".") for part in path.relative_to(LOOPS_DIR).parts):
            continue
        files.append(path)
    return files


def _iter_strings(node: Any):
    """Yield every string scalar reachable from a loaded-YAML node."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_strings(item)


@pytest.mark.parametrize(
    "loop_file",
    _builtin_loop_files(),
    ids=lambda p: str(p.relative_to(LOOPS_DIR)),
)
def test_builtin_loop_has_no_bare_variable_references(loop_file: Path) -> None:
    """Every ${...} in a builtin loop must be a valid namespace.path or escaped."""
    data = yaml.safe_load(loop_file.read_text())
    if not isinstance(data, dict):
        pytest.skip(f"{loop_file.name} is not a mapping")

    # Action/evaluate/with strings live under states (and fragments, for lib/).
    scopes = [data.get("states"), data.get("fragments")]
    ctx = _PermissiveContext()

    for scope in scopes:
        if scope is None:
            continue
        for text in _iter_strings(scope):
            if "${" not in text:
                continue
            try:
                interpolate(text, ctx)
            except InterpolationError as exc:
                pytest.fail(
                    f"{loop_file.relative_to(LOOPS_DIR)} contains an invalid "
                    f"template reference: {exc}\n"
                    f"Offending string:\n{text}\n"
                    "Bare shell variables must be escaped as $${VAR} or written "
                    "as a ${namespace.path} reference."
                )
