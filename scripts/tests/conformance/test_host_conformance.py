"""Host conformance harness for little-loops orchestration golden paths.

Parametrized over every host registered in ``_HOST_RUNNER_REGISTRY``.  Each
test case verifies that ``resolve_host() + build_streaming()`` produces a
valid ``HostInvocation`` for one of the four orchestration golden paths:
``ll-auto``, ``ll-sprint``, ``ll-loop``, ``ll-action``.

Run all conformance tests::

    pytest -m conformance scripts/tests/

Run for a specific host only::

    pytest -m conformance --conformance-host codex scripts/tests/

Deselect conformance tests from a full suite run::

    pytest -m "not conformance" scripts/tests/

Skip conditions (SKIP, not FAIL):
- Binary unavailable on PATH (e.g. ``claude`` not installed)
- Stub runner: ``build_streaming`` raises ``HostNotConfigured``

The PASS/SKIP matrix maps directly to the "Orchestration CLI" table in
``docs/reference/HOST_COMPATIBILITY.md``:  PASS → ✓, SKIP(stub) → stub[^orch].
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from little_loops.host_runner import (
    _HOST_RUNNER_REGISTRY,
    HostNotConfigured,
    resolve_host,
)

# Representative prompt for each orchestration tool golden path.  Content is
# illustrative — conformance only validates that a HostInvocation is
# constructable; it does not execute the prompt against a live host.
_GOLDEN_PATHS: list[tuple[str, str]] = [
    ("ll-auto", "Process the next open issue from the backlog using /ll:manage-issue."),
    ("ll-sprint", "Execute the current sprint plan using /ll:review-sprint."),
    ("ll-loop", "Run one FSM loop iteration using /ll:audit-loop-run."),
    ("ll-action", "/ll:check-code"),
]

# Binary name for each registered host — used to probe PATH availability.
_HOST_BINARY: dict[str, str] = {
    "claude-code": "claude",
    "codex": "codex",
    "opencode": "opencode",
    "pi": "pi",
    "gemini": "gemini",
    "omp": "omp",
}


@pytest.mark.conformance
@pytest.mark.parametrize("host", list(_HOST_RUNNER_REGISTRY.keys()))
@pytest.mark.parametrize(
    "golden_path,prompt",
    _GOLDEN_PATHS,
    ids=[p[0] for p in _GOLDEN_PATHS],
)
def test_golden_path_invocation(
    host: str,
    golden_path: str,
    prompt: str,
    tmp_path: Path,
    isolated_env: None,
    request: pytest.FixtureRequest,
) -> None:
    """``resolve_host() + build_streaming()`` produces a valid ``HostInvocation``.

    A PASS means the host runner is wired and can construct an invocation for
    the given golden path.  A SKIP means the host binary is absent or the
    runner is a stub (``HostNotConfigured``).

    Args:
        host: Registered host key (e.g. ``"codex"``, ``"claude-code"``).
        golden_path: Orchestration tool label (e.g. ``"ll-auto"``).
        prompt: Representative prompt string passed to ``build_streaming``.
        tmp_path: Temporary directory used as ``working_dir``.
        isolated_env: Clears ``LL_HOST_CLI`` / ``LL_HOOK_HOST`` before the test.
        request: Pytest fixture request (used to read the ``--host`` option).
    """
    # Honour the --conformance-host filter when supplied on the command line.
    host_filter: str | None = request.config.getoption("--conformance-host", default=None)
    if host_filter is not None and host != host_filter:
        pytest.skip(f"--host filter {host_filter!r} excludes {host!r}")

    # Skip when the host binary is not available on this machine.
    binary = _HOST_BINARY.get(host)
    if binary is not None and shutil.which(binary) is None:
        pytest.skip(f"{host!r} binary ({binary!r}) not found on PATH")

    runner = resolve_host(env={"LL_HOST_CLI": host})

    # Skip stub runners that raise HostNotConfigured on build_streaming().
    try:
        invocation = runner.build_streaming(prompt=prompt, working_dir=tmp_path)
    except HostNotConfigured as exc:
        pytest.skip(f"{host!r} is a stub runner: {exc}")

    assert invocation.binary, f"[{host}/{golden_path}] HostInvocation.binary must not be empty"
    assert invocation.args, f"[{host}/{golden_path}] HostInvocation.args must not be empty"
