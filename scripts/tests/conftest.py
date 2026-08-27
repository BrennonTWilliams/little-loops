"""Pytest fixtures for little-loops tests."""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import tempfile
import threading
import warnings
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest
from hypothesis import settings as _hypothesis_settings

from little_loops.host_runner import HOST_BINARY_NAMES
from little_loops.issue_parser import reset_deprecated_key_warnings

# =============================================================================
# Hypothesis fuzz depth profiles
# =============================================================================
#
# Fast by default so interactive full-suite runs don't burn ~3,600 generated
# examples; LL_FUZZ=full restores full depth (the automated verify gate sets
# it). These profiles govern tests WITHOUT an explicit @settings decorator;
# decorated fuzz tests use tests.helpers.fuzz_max_examples for the same knob
# (an explicit @settings always overrides the loaded profile).
_hypothesis_settings.register_profile("ll-dev", max_examples=25)
_hypothesis_settings.register_profile("ll-full", max_examples=100)
_hypothesis_settings.load_profile("ll-full" if os.environ.get("LL_FUZZ") == "full" else "ll-dev")

# =============================================================================
# macOS "beachball" defense: worker cap + lowered scheduling priority
# =============================================================================
#
# The suite is ~13.7k CPU-bound tests. Two things make a full run freeze the UI:
#   1. xdist runs one worker PER logical core (14/14 on this M4), so every core
#      pins at 100%.
#   2. Even below full core count, the run stays CPU-bound *at normal scheduling
#      priority*, so the macOS compositor (WindowServer) never gets scheduled ->
#      the "beachball of death".
# We defend on both axes: cap the worker count for headroom, AND renice the
# pytest processes so the OS always preempts them for the UI. `nice` costs almost
# no wall-clock when cores are free (it only yields under contention), so the
# suite stays fast while the machine stays responsive.


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    """Cap xdist workers below the core count so the OS keeps CPU headroom.

    `-n logical` (see pyproject.toml addopts) otherwise resolves to one worker
    per logical core (14/14 on Apple Silicon, where logical == physical),
    saturating every core.

    This conftest hook wins over xdist's default implementation, so it applies
    whenever `-n auto` / `-n logical` is used. An explicit `-n <N>` or `-n 0`
    (serial) bypasses it. ``PYTEST_XDIST_AUTO_NUM_WORKERS`` is honored as a
    manual override.
    """
    cpus = os.cpu_count() or 4
    env = os.environ.get("PYTEST_XDIST_AUTO_NUM_WORKERS")
    if env:
        try:
            # Clamp to cpus-2: honor the override's intent but never allow it
            # (e.g. a value inherited from a parent automation env) to
            # oversubscribe every core and re-create the freeze this hook
            # exists to prevent.
            return max(1, min(int(env), cpus - 2))
        except ValueError:
            pass
    # Reserve ~half the cores for the OS/other apps. Individual tests also spawn
    # their own threads/subprocesses (ThreadPoolExecutors, unix sockets, git),
    # so effective load per worker is > 1 core; half keeps real headroom.
    # 14 -> 7, 8 -> 4, 4 -> 2 (floor of 2).
    return max(2, cpus // 2)


def pytest_configure(config: pytest.Config) -> None:
    """Lower the priority of pytest processes so macOS stays responsive.

    Runs once on the controller and once inside every xdist worker (each worker
    is its own process that re-runs pytest_configure), so the whole run drops to
    a lower scheduling priority. This is the actual fix for the UI freeze: a
    fully CPU-bound run at normal priority starves WindowServer; niced, the OS
    preempts the tests for the UI. Opt out with ``LL_TEST_NO_NICE=1``.
    """
    if os.environ.get("LL_TEST_NO_NICE"):
        return
    if not hasattr(os, "nice"):  # non-POSIX (e.g. Windows)
        return
    try:
        # Increment niceness by 10 (lower priority). Requires no privileges.
        # Idempotent enough: each process calls this exactly once.
        os.nice(10)
    except OSError:
        pass


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip ``no_parallel``-marked tests on xdist workers (BUG-2523).

    Some tests are timing-sensitive (e.g. ``subprocess.Popen`` + ``os.kill(SIGINT)``
    + hard ``proc.wait(timeout=...)`` in
    ``scripts/tests/test_fsm_signal_integration.py``) and flake under xdist
    worker contention: 7 workers competing for the same cores can starve the
    spawned loop subprocess's SIGINT handler past its 10s wait, surfacing as
    ``subprocess.TimeoutExpired``. The structural fix is to skip the test on
    workers so it only runs on the controller — but under ``-n N`` the
    controller only collects and distributes work, it never runs tests
    itself. Net effect: a ``no_parallel`` test does **not** run under the
    default ``-n logical`` addopts; it runs only in a serial ``-n 0`` run
    (see ``scripts/tests/test_worktree_utils.py:1228`` for the same warning).

    Detection idiom mirrors
    ``scripts/little_loops/pytest_history_plugin.py:147-150``
    (``hasattr(config, 'workerinput') and config.workerinput``) — the same
    pattern proven correct by ``scripts/tests/test_pytest_history_plugin.py:62-71``.
    """
    if not (hasattr(config, "workerinput") and config.workerinput):
        # Controller (or single-process run) — let marked tests run.
        return
    skip_marker = pytest.mark.skip(reason="no_parallel: cannot run on xdist workers")
    for item in items:
        if "no_parallel" in item.keywords:
            item.add_marker(skip_marker)


# =============================================================================
# Live host-CLI spawn guard + rate-limit ladder guard (FEAT-3329)
# =============================================================================
#
# Two structural gaps this closes, both split out of BUG-3325:
#
# 1. Nothing failed a test that spawned the real host CLI (`claude` et al.) —
#    a passing test could still bill the account. Guarded here at the
#    process-spawn boundary (subprocess.run / subprocess.Popen), not by
#    patching a helper function, because both host_runner.py and
#    subprocess_utils.py `import subprocess` as a module: subprocess.run and
#    subprocess.Popen are process-global attributes, so ONE patch pair covers
#    every call path (blocking, streaming, detached) rather than two
#    independent per-module patches.
# 2. Nothing failed a rate-limit test that omitted the
#    _DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[0] patch convention — it would
#    sleep on the real 300s ladder, which the --timeout=120
#    --timeout-method=thread watchdog cannot kill (the BUG-3208 wedge). See
#    ``_collapse_rate_limit_ladder`` below.
#
# Completeness precondition for guard 1: scripts/little_loops/ contains zero
# occurrences of asyncio.create_subprocess_exec/_shell, os.system, os.exec*,
# os.spawn*, or pty.spawn (verified 2026-08-26) — every process the package
# spawns goes through subprocess.run/Popen. asyncio.create_subprocess_* in
# particular does NOT route through subprocess.Popen and would be a silent
# blind spot; a future change introducing one of these must extend the guard.
# Accepted gap: a `shell=True` string command is a pass-through (argv[0] is
# the whole command line, not a program name) — no production code uses
# shell=True (the only repo occurrence is loops/mechanize-skills.yaml, a
# loop YAML action, not a Python call path).


class _LiveHostCLISpawn(Exception):
    """Raised when guarded subprocess.run/Popen resolves argv[0] to a host CLI."""


_host_cli_lock = threading.Lock()
# (test_id, binary) tuples, one per recorded spawn attempt. Written from FSM
# worker threads as well as the main test thread — always mutate under
# _host_cli_lock.
_host_cli_hits: list[tuple[str, str]] = []
# Monotonic cursor into _host_cli_hits: everything before this index has
# already been reported by _drain_new_hits(). NOT a pre-yield len() snapshot
# (that silently drops hits appended during higher-scope fixture setup or by
# a background thread outside any test's function-fixture window) and NOT a
# bare truthiness check (that cascade-fails every later test on the worker
# once one hit lands). Slice-and-advance reports every hit exactly once and
# attributes an out-of-window hit to the next test to finish.
_reported_upto = 0


def _current_test_id() -> str:
    """Best-effort test id for the collector tuple, from PYTEST_CURRENT_TEST.

    Only feeds the recorded tuple (for the dedupe key and the
    pytest_sessionfinish summary) — attribution of WHICH test's teardown
    fails is by report-cursor position in ``_fail_on_live_host_cli``, not by
    this value, so a placeholder here (collection time, higher-scope fixture
    setup, a background thread) does not break enforcement.
    """
    current = os.environ.get("PYTEST_CURRENT_TEST")
    if not current:
        return "<no active test>"
    return current.split(" ", 1)[0]


def _extract_argv(args: tuple[Any, ...], kwargs: dict[str, Any]) -> list[str] | None:
    """Normalize a subprocess.run/Popen call's command to a list[str], or None.

    Because the patch this feeds is process-global, this function sees every
    subprocess call in the suite — a TypeError/IndexError raised here would
    break unrelated tests in a way that reads as a guard bug, not a test bug.
    Returns None (pass-through, no opinion) for anything not confidently
    resolvable, rather than raising.
    """
    argv = args[0] if args else kwargs.get("args")
    if argv is None:
        return None
    if isinstance(argv, os.PathLike):
        return [os.fspath(argv)]
    if isinstance(argv, (str, bytes)):
        # shell=True string command: argv[0] would be the whole command line,
        # not indexable into a program name. Accepted gap — see module note.
        return None
    try:
        items = list(argv)
    except TypeError:
        return None
    if not items:
        return None
    normalized: list[str] = []
    for item in items:
        if isinstance(item, os.PathLike):
            normalized.append(os.fspath(item))
        elif isinstance(item, str):
            normalized.append(item)
        elif isinstance(item, bytes):
            try:
                normalized.append(item.decode())
            except UnicodeDecodeError:
                return None
        else:
            return None
    return normalized


def _match_host_binary(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[str, list[str]] | None:
    """Return (basename, argv) if this call targets a host CLI binary, else None.

    Applies the ``--version`` carve-out: all six wired
    ``build_version_check()`` implementations emit exactly ``args=["<binary>",
    "--version"]``, which is free (no spend) but would otherwise trip a naive
    argv[0]-basename check.
    """
    argv = _extract_argv(args, kwargs)
    if not argv:
        return None
    binary = os.path.basename(argv[0])
    if binary not in HOST_BINARY_NAMES:
        return None
    if list(argv[1:]) == ["--version"]:
        return None
    return binary, argv


def _record_and_build_error(binary: str, argv: list[str]) -> _LiveHostCLISpawn:
    test_id = _current_test_id()
    with _host_cli_lock:
        _host_cli_hits.append((test_id, binary))
    return _LiveHostCLISpawn(
        f"live host-CLI spawn: this test spawned the real host CLI `{binary}` "
        f"(argv={argv!r}) — mock the spawn instead of calling the real "
        f"binary. Patch subprocess.run / subprocess.Popen (or the "
        f"host_runner.py / subprocess_utils.py helper one level up), the "
        f"way test_host_runner.py::TestRunBlockingJson and "
        f"test_subprocess_utils.py already do. See "
        f"docs/development/TESTING.md."
    )


def _drain_new_hits() -> str | None:
    """Slice-and-advance the report cursor; return a message for new hits, or None.

    Pure module-level helper (not inline in the teardown fixture) so it is
    unit-testable: a test cannot assert that its own teardown fails, and
    test_conftest_cap.py loads conftest.py as a second, independent module
    whose collector is a different object from this one. Dedupes the
    reported slice by (test_id, binary) with a count, since a retry-on-error
    path can re-enter the spawn after the guard raises.
    """
    global _reported_upto
    with _host_cli_lock:
        new_hits = _host_cli_hits[_reported_upto:]
        if not new_hits:
            return None
        _reported_upto = len(_host_cli_hits)
    counts: dict[tuple[str, str], int] = {}
    for hit in new_hits:
        counts[hit] = counts.get(hit, 0) + 1
    lines = [
        f"  - {test_id} spawned `{binary}`" + (f" (x{count})" if count > 1 else "")
        for (test_id, binary), count in counts.items()
    ]
    return (
        "This test spawned the real host CLI — mock the spawn instead of "
        "calling the real binary (patch subprocess.run / subprocess.Popen, "
        "or the helper one level up):\n" + "\n".join(lines)
    )


class _GuardedPopen(subprocess.Popen):
    """subprocess.Popen replacement that fails on a real host-CLI spawn.

    Must be a *subclass* of subprocess.Popen, not a function: a function
    breaks MagicMock(spec=subprocess.Popen) (used in test_subprocess_utils.py
    and test_worker_pool.py — a function spec exposes no Popen attributes, so
    `.poll`/`.wait` raise AttributeError) and subprocess.Popen[str]
    subscripting (used at nine production call sites). Raises before
    super().__init__() runs, which is safe without a defensive
    `self._child_created = False`: `_child_created` is a *class* attribute on
    subprocess.Popen (False), so Popen.__del__ on the partially-initialized
    instance is well-defined and emits no "Exception ignored" noise.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        match = _match_host_binary(args, kwargs)
        if match is not None:
            binary, argv = match
            raise _record_and_build_error(binary, argv)
        super().__init__(*args, **kwargs)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Print-only summary for host-CLI-spawn hits with no next test to attribute to.

    NOT the enforcement mechanism (see ``_fail_on_live_host_cli``) — under
    xdist a worker-mutated ``session.exitstatus`` never reaches the
    controller, so a worker-side sessionfinish cannot fail the run at all.
    This hook only covers the residual reporting gap: the last test on a
    worker, or a spawn during session-/module-fixture teardown, both land
    after the final function-scoped teardown has already advanced the
    report cursor, so nothing would otherwise surface them. Calls the same
    ``_drain_new_hits()`` helper the teardown fixture uses, so the lock, the
    cursor advance, and the dedupe are shared rather than reimplemented.

    ``warnings.warn`` is safe today because ``pyproject.toml`` sets no
    ``filterwarnings`` (verified 2026-08-26), so this cannot escalate to an
    error — but if ``filterwarnings = ["error"]`` is ever added, a
    sessionfinish-time warning could crash a worker confusingly. Noted here
    so that interaction is discovered by reading, not by debugging.
    """
    msg = _drain_new_hits()
    if not msg:
        return
    terminalreporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminalreporter is not None:
        terminalreporter.write_line(msg, red=True)
    warnings.warn(msg, stacklevel=1)


@pytest.fixture(scope="session", autouse=True)
def _install_no_live_host_cli() -> Generator[None, None, None]:
    """Fail any test that spawns a real host CLI binary (FEAT-3329).

    Patches the single process-global choke point every host-CLI spawn path
    shares — ``subprocess.run`` and a ``subprocess.Popen`` subclass — rather
    than a per-module or per-function patch, because both ``host_runner.py``
    and ``subprocess_utils.py`` do a plain ``import subprocess``. Covers the
    blocking (``run_blocking_json``), streaming (``run_claude_command``), and
    detached (``handoff_handler.build_detached``) paths for free.

    A raise alone is insufficient: ``FSMExecutor._evaluate`` swallows an
    evaluator exception into an ``error`` verdict, so a test whose FSM routes
    ``on_error`` to a terminal state would never see the raise propagate.
    Every match is therefore also recorded into a module-level collector
    (``_host_cli_hits``) *before* raising, so ``_fail_on_live_host_cli``'s
    teardown check still surfaces the hit even when the raise itself was
    eaten inside the test body.

    **Must be defined first among session-scoped autouse fixtures in this
    file** — same-scope autouse fixtures set up in definition order, so this
    ordering is what lets the guard observe a spawn during another
    session-scoped fixture's own setup.

    Undone via ``mp.undo()`` in a ``finally`` after ``yield``, following
    ``_guard_real_history_db``'s shape (a raw ``pytest.MonkeyPatch()``
    instance, since the function-scoped ``monkeypatch`` fixture is
    unavailable at session scope).
    """
    real_run = subprocess.run

    def guarded_run(*args: Any, **kwargs: Any) -> Any:
        match = _match_host_binary(args, kwargs)
        if match is not None:
            binary, argv = match
            raise _record_and_build_error(binary, argv)
        return real_run(*args, **kwargs)

    mp = pytest.MonkeyPatch()
    mp.setattr(subprocess, "run", guarded_run)
    mp.setattr(subprocess, "Popen", _GuardedPopen)
    try:
        yield
    finally:
        mp.undo()


@pytest.fixture(autouse=True)
def _fail_on_live_host_cli() -> Generator[None, None, None]:
    """Fail this test's teardown if it (or a background thread) spawned a real host CLI.

    Enforcement mechanism for the guard above — NOT ``pytest_sessionfinish``,
    which cannot reliably fail the run under the default ``-n logical``
    addopts (xdist workers do not propagate a worker-mutated
    ``session.exitstatus`` to the controller). This function-scoped
    teardown-check works identically serially and under xdist because it
    produces an ordinary test report rather than mutating session state.

    Reports as an ERROR at teardown, not a FAILURE — the offending test line
    itself still prints ``passed`` (pytest's standard classification for an
    exception raised in a fixture's post-yield teardown). The run's exit
    status is still nonzero, which is what matters for enforcement; the
    message from ``_drain_new_hits()`` leads with the diagnosis rather than
    with collector/cursor mechanics for exactly this reason.

    **Must be defined first among function-scoped autouse fixtures in this
    file** — function-scoped fixtures tear down in reverse setup order, so
    defining this one first makes its teardown run *last*, catching a spawn
    that happens inside another function-scoped fixture's own teardown
    within the same test.
    """
    yield
    msg = _drain_new_hits()
    if msg:
        pytest.fail(msg)


@pytest.fixture(scope="session", autouse=True)
def _collapse_rate_limit_ladder() -> Generator[None, None, None]:
    """Collapse the rate-limit backoff ladder to zero suite-wide (FEAT-3329).

    Makes the "patch the ladder to [0]" convention structural rather than
    per-test discipline: a rate-limit test that forgets the patch previously
    slept on the real 300s ladder, which the ``--timeout=120
    --timeout-method=thread`` watchdog cannot kill (the BUG-3208 wedge) — now
    it simply runs fast. Session-scoped and suite-wide, not file-local or
    class-scoped: file-locality only protects tests written in one file, and
    there is no class-scoped-autouse precedent in this codebase.

    No marker exemption for the one intentional non-zero ladder
    (``test_fsm_executor.py`` heartbeat test, ``[0.3]``): it patches both
    constants via ``patch.multiple`` inside the test body, which is applied
    after — and therefore wins over — this session-scoped patch. A marker
    exemption would be impossible here anyway: a session-scoped fixture runs
    once and cannot observe per-test markers.
    """
    from little_loops.fsm import executor as fsm_executor

    mp = pytest.MonkeyPatch()
    mp.setattr(fsm_executor, "_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER", [0])
    mp.setattr(fsm_executor, "_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS", 0)
    try:
        yield
    finally:
        mp.undo()


# =============================================================================
# Snapshot Testing Helpers
# =============================================================================


@pytest.fixture
def stable_snapshot_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin determinism controls for snapshot tests.

    Disables ANSI color and fixes terminal width to 80 so golden files are
    stable across environments. Apply explicitly to snapshot test classes via
    ``@pytest.mark.usefixtures("stable_snapshot_env")`` rather than autouse
    to avoid interfering with tests that assert both color-on and color-off.
    """
    monkeypatch.setattr("little_loops.cli.output._USE_COLOR", False)
    monkeypatch.setattr("little_loops.cli.output.terminal_width", lambda **_kw: 80)
    try:
        monkeypatch.setattr("little_loops.cli.loop.layout._USE_COLOR", False)
    except AttributeError:
        pass


# =============================================================================
# Fixture File Helpers
# =============================================================================


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def issue_fixtures(fixtures_dir: Path) -> Path:
    """Path to issue fixture files."""
    return fixtures_dir / "issues"


@pytest.fixture
def fsm_fixtures(fixtures_dir: Path) -> Path:
    """Path to FSM fixture files."""
    return fixtures_dir / "fsm"


def load_fixture(fixtures_dir: Path, *path_parts: str) -> str:
    """Load fixture file content by path parts.

    Args:
        fixtures_dir: Base fixtures directory path.
        path_parts: Path components relative to fixtures_dir.

    Returns:
        Content of the fixture file as a string.
    """
    fixture_path = fixtures_dir.joinpath(*path_parts)
    return fixture_path.read_text()


# =============================================================================
# Doc-Wiring Helpers
# =============================================================================


def doc_wiring_frontmatter(path: Path) -> str:
    """Extract YAML frontmatter block from a markdown file.

    Returns everything between the first ``---`` and the closing ``---``.
    Used by doc-wiring tests to assert on frontmatter fields without false
    positives from body text.

    Args:
        path: Path to a markdown file with YAML frontmatter.

    Returns:
        The frontmatter string including the ``---`` delimiters.
    """
    content = path.read_text()
    end = content.index("---", 3)
    return content[: end + 3]


def doc_wiring_section(content: str, heading: str) -> str:
    """Extract the content under a markdown heading up to the next same-level heading.

    Args:
        content: Full markdown document text.
        heading: The heading text to find (without leading ``## `` markers).

    Returns:
        The content from the heading line to the next heading of the same level,
        or to end of content if it's the last section.
    """
    # Determine heading level from the heading string
    prefix = "## "
    marker = prefix + heading
    start = content.index(marker)
    # Find next heading at the same level after start
    end = content.find("\n" + prefix, start + len(marker))
    if end == -1:
        return content[start:]
    return content[start:end]


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Repository root path (session-scoped, computed once)."""
    return Path(__file__).parent.parent.parent


# =============================================================================
# Project Directory Fixtures
# =============================================================================


@pytest.fixture
def temp_project_dir() -> Generator[Path, None, None]:
    """Create a temporary project directory with .ll folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        ll_dir = project_root / ".ll"
        ll_dir.mkdir(exist_ok=True)
        yield project_root


@pytest.fixture
def make_project(
    tmp_path: Path,
) -> Callable[[dict[str, Any] | None, list[str] | None], tuple[Path, Path]]:
    """Factory fixture for creating temporary project directories with custom configs.

    Each call creates a numbered subdirectory under pytest's ``tmp_path`` so the
    factory can be invoked multiple times in a single test without collisions.
    Cleanup is handled automatically by pytest's ``tmp_path`` teardown.

    Args:
        config: Full config dict written to ``.ll/ll-config.json``.  When
            omitted a minimal ``{"project": {"name": "test-project"}}`` is used.
        extra_dirs: Additional directories to create, given as paths relative to
            the project root (e.g. ``[".issues/completed", ".worktrees"]``).

    Returns:
        ``(project_root, issues_base)`` — project root and the resolved
        ``issues.base_dir`` directory (default ``.issues``).
    """
    _counter = [0]

    def _factory(
        config: dict[str, Any] | None = None,
        extra_dirs: list[str] | None = None,
    ) -> tuple[Path, Path]:
        _counter[0] += 1
        project = tmp_path / f"project_{_counter[0]}"
        project.mkdir()
        ll_dir = project / ".ll"
        ll_dir.mkdir()

        cfg: dict[str, Any] = config or {"project": {"name": "test-project"}}
        (ll_dir / "ll-config.json").write_text(json.dumps(cfg))

        base_dir = cfg.get("issues", {}).get("base_dir", ".issues")
        issues_base = project / base_dir
        categories: dict[str, Any] = cfg.get("issues", {}).get("categories", {})
        for cat_key, cat_val in categories.items():
            cat_dir_name = cat_val.get("dir", cat_key) if isinstance(cat_val, dict) else cat_key
            (issues_base / cat_dir_name).mkdir(parents=True, exist_ok=True)

        for d in extra_dirs or []:
            (project / d).mkdir(parents=True, exist_ok=True)

        return project, issues_base

    return _factory


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """Sample configuration dictionary."""
    return {
        "project": {
            "name": "test-project",
            "src_dir": "src/",
            "test_cmd": "pytest tests/",
            "lint_cmd": "ruff check .",
            "type_cmd": "mypy src/",
            "format_cmd": "ruff format .",
            "build_cmd": None,
            "run_cmd": None,
        },
        "issues": {
            "base_dir": ".issues",
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                "epics": {"prefix": "EPIC", "dir": "epics", "action": "implement"},
            },
            "completed_dir": "completed",
            "deferred_dir": "deferred",
            "priorities": ["P0", "P1", "P2", "P3"],
        },
        "automation": {
            "timeout_seconds": 1800,
            "state_file": ".test-state.json",
            "worktree_base": ".worktrees",
            "max_workers": 2,
            "stream_output": False,
        },
        "parallel": {
            "max_workers": 3,
            "p0_sequential": True,
            "worktree_base": ".worktrees",
            "state_file": ".parallel-state.json",
            "timeout_seconds": 1800,
            "max_merge_retries": 2,
            "stream_output": False,
            "command_prefix": "/ll:",
            "ready_command": "ready-issue {{issue_id}}",
            "manage_command": "manage-issue {{issue_type}} {{action}} {{issue_id}}",
            "use_feature_branches": True,
        },
        "sprints": {
            "sprints_dir": ".sprints",
            "default_timeout": 3600,
            "default_max_workers": 4,
        },
        "orchestration": {},
    }


@pytest.fixture
def config_file(temp_project_dir: Path, sample_config: dict[str, Any]) -> Path:
    """Create a config file in the temp project."""
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config, indent=2))
    return config_path


@pytest.fixture
def issues_dir(temp_project_dir: Path) -> Path:
    """Create issue type directories with sample issues.

    Post-ENH-1418: status lives in frontmatter, not in directory location, so
    no ``completed/`` or ``deferred/`` sibling dirs are created here.
    """
    issues_base = temp_project_dir / ".issues"
    bugs_dir = issues_base / "bugs"
    features_dir = issues_base / "features"
    epics_dir = issues_base / "epics"

    bugs_dir.mkdir(parents=True, exist_ok=True)
    features_dir.mkdir(parents=True, exist_ok=True)
    epics_dir.mkdir(parents=True, exist_ok=True)

    # Create sample bug issues
    (bugs_dir / "P0-BUG-001-critical-crash.md").write_text(
        "---\nstatus: open\n---\n# BUG-001: Critical crash on startup\n\n## Summary\nApp crashes on launch."
    )
    (bugs_dir / "P1-BUG-002-slow-query.md").write_text(
        "---\nstatus: open\n---\n# BUG-002: Slow database query\n\n## Summary\nQuery takes too long."
    )
    (bugs_dir / "P2-BUG-003-ui-glitch.md").write_text(
        "---\nstatus: open\n---\n# BUG-003: UI glitch in sidebar\n\n## Summary\nSidebar flickers."
    )

    # Create sample feature issues
    (features_dir / "P1-FEAT-001-dark-mode.md").write_text(
        "---\nstatus: open\n---\n# FEAT-001: Add dark mode\n\n## Summary\nImplement dark theme."
    )
    (features_dir / "P2-FEAT-002-export-csv.md").write_text(
        "---\nstatus: open\n---\n# FEAT-002: Export to CSV\n\n## Summary\nAdd CSV export functionality."
    )

    return issues_base


@pytest.fixture
def sample_ready_issue_output_ready() -> str:
    """Sample ready_issue output for a READY verdict."""
    return """
## VALIDATION RESULT

| Check | Status | Details |
|-------|--------|---------|
| File references | PASS | All referenced files exist |
| Code accuracy | PASS | Code snippets match current implementation |
| Dependencies | PASS | No blocking dependencies |

## VERDICT: **READY**

The issue is ready for implementation.
"""


@pytest.fixture
def sample_ready_issue_output_not_ready() -> str:
    """Sample ready_issue output for a NOT_READY verdict."""
    return """
## VALIDATION RESULT

| Check | Status | Details |
|-------|--------|---------|
| File references | FAIL | Referenced file does not exist: src/missing.py |
| Code accuracy | PASS | Code snippets match |
| Dependencies | WARN | May conflict with ongoing work |

## VERDICT: **NOT_READY**

The issue has validation failures that must be addressed.

## CONCERNS
- Referenced file src/missing.py does not exist
- Potential conflict with PR #42
"""


@pytest.fixture
def sample_ready_issue_output_close() -> str:
    """Sample ready_issue output for a CLOSE verdict."""
    return """
## VALIDATION RESULT

| Check | Status | Details |
|-------|--------|---------|
| File references | N/A | Issue describes already-fixed behavior |
| Code accuracy | N/A | Current code does not have this bug |

## VERDICT: **CLOSE**

## CLOSE_REASON: already_fixed
## CLOSE_STATUS: Closed - Already Fixed

The reported issue has already been resolved in a previous commit.
"""


# =============================================================================
# FSM Loop Test Fixtures
# =============================================================================


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory for loop tests."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir(exist_ok=True)
    (project_dir / ".loops").mkdir(exist_ok=True)
    return project_dir


@pytest.fixture
def valid_loop_file(temp_project: Path) -> Path:
    """Create a valid loop YAML file for testing."""
    loop_file = temp_project / ".loops" / "valid-loop.yaml"
    loop_content = """
name: test-loop
initial: start
states:
  start:
    action: echo "hello"
    on_yes: done
  done:
    terminal: true
"""
    loop_file.write_text(loop_content)
    return loop_file


@pytest.fixture
def invalid_loop_file(temp_project: Path) -> Path:
    """Create an invalid loop YAML file for testing."""
    loop_file = temp_project / ".loops" / "invalid-loop.yaml"
    loop_content = """
name: test-loop
initial: nonexistent
states:
  start:
    action: echo "hello"
    on_yes: done
  done:
    terminal: true
"""
    loop_file.write_text(loop_content)
    return loop_file


@pytest.fixture
def loops_dir(tmp_path: Path) -> Path:
    """Create a .loops directory with test loop files."""
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir(exist_ok=True)
    (loops_dir / "loop1.yaml").write_text(
        "name: loop1\ninitial: start\nstates:\n  start:\n    terminal: true"
    )
    (loops_dir / "loop2.yaml").write_text(
        "name: loop2\ninitial: start\nstates:\n  start:\n    terminal: true"
    )
    return loops_dir


@pytest.fixture
def events_file(tmp_path: Path) -> Path:
    """Create an events JSONL file for history tests."""
    events_path = tmp_path / "events.jsonl"
    events = [
        '{"timestamp": "2025-01-01T00:00:00", "state": "start", "action": "echo test"}',
        '{"timestamp": "2025-01-01T00:01:00", "state": "done", "action": ""}',
    ]
    events_path.write_text("\n".join(events))
    return events_path


@pytest.fixture
def many_events_file(tmp_path: Path) -> Path:
    """Create an events JSONL file with 10 events for tail tests."""
    events_path = tmp_path / "events.jsonl"
    events = [
        f'{{"timestamp": "2025-01-01T00:0{i}:00", "state": "state{i}", "action": "action{i}"}}'
        for i in range(10)
    ]
    events_path.write_text("\n".join(events))
    return events_path


# =============================================================================
# DB Isolation Fixtures (BUG-1995)
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def _isolate_history_db_session(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[None, None, None]:
    """Set LL_HISTORY_DB for the entire session so no module-level or session-scoped
    code accidentally opens the real .ll/history.db before function-scoped fixtures run.
    """
    session_db_dir = tmp_path_factory.mktemp("session_db") / ".ll"
    session_db_dir.mkdir(exist_ok=True)
    os.environ["LL_HISTORY_DB"] = str(session_db_dir / "history.db")
    yield
    os.environ.pop("LL_HISTORY_DB", None)


_isolation_seq = itertools.count()


@pytest.fixture(scope="session")
def _isolation_base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One real mkdir per (xdist worker) process for all per-test DB paths.

    Under xdist each worker has its own ``basetemp/popen-gwN`` subtree, so this
    base is globally unique with no cross-worker coordination.
    """
    return tmp_path_factory.mktemp("isolation")


@pytest.fixture(autouse=True)
def _isolate_history_db(
    request: pytest.FixtureRequest,
    _isolation_base: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Redirect all session-store DB opens to a per-test temp path.

    Sets LL_HISTORY_DB so cli_event_context and resolve_history_db route
    writes away from the real .ll/history.db.

    Deliberately does NOT request ``tmp_path``: an autouse tmp_path forces
    pytest to materialize (and later rmtree) a numbered directory for every
    test, and at ~13.7k tests that directory churn is what drives macOS
    launchservicesd/fseventsd to saturate cores (the "beachball").

    Two cases:
    - The test itself requests ``tmp_path``: point LL_HISTORY_DB at
      ``tmp_path/.ll/history.db``. Many such tests construct that exact path
      and expect the env override to coincide with it (``_resolve_db_path``
      routes any default-shaped ``.ll/history.db`` argument through the env
      var). The directory is materialized for them anyway, so this costs
      nothing extra.
    - Otherwise: a unique path STRING under a single session-scoped base —
      never materialized here; only tests that actually open a DB pay a mkdir
      (ensure_db() creates parents on first open). The .ll/ segment keeps
      ensure_db's legacy migration (session.db → history.db) from ever seeing
      a session.db sibling.
    """
    if "tmp_path" in request.fixturenames:
        base: Path = request.getfixturevalue("tmp_path")
    else:
        base = _isolation_base / f"t{next(_isolation_seq)}"
    monkeypatch.setenv("LL_HISTORY_DB", str(base / ".ll" / "history.db"))
    yield


@pytest.fixture(scope="session", autouse=True)
def _guard_real_history_db() -> Generator[None, None, None]:
    """Fail fast if any test opens the real .ll/history.db without isolation.

    Intercepts the single choke point every DB open routes through —
    ``little_loops.session_store.sqlite3.connect`` (used by ``ensure_db``,
    ``connect``, ``SessionStore._connect``, and vacuum) — and raises if a test
    targets the production database. Unlike the previous mtime/size snapshot,
    this is immune to concurrent external writers (live ``ll-auto`` / ``ll-loop``
    runs touch ``.ll/history.db`` continuously) and attributes a genuine leak to
    the actual offending test rather than the last test in the session.

    ``LL_HISTORY_DB`` is set per-test by ``_isolate_history_db``, so legitimate
    DB opens resolve to ``tmp_path/.ll/history.db`` and pass straight through.
    """
    import sqlite3

    from little_loops import session_store

    real_db = (Path(__file__).parent.parent.parent / ".ll" / "history.db").resolve()
    real_connect = sqlite3.connect

    def guarded_connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        try:
            resolved = Path(database).resolve()
        except TypeError:
            # Non-path targets (e.g. ":memory:") never alias the real DB.
            return real_connect(database, *args, **kwargs)
        assert resolved != real_db, (
            f"A test opened the production database without isolation: {resolved}. "
            f"Route the open through LL_HISTORY_DB / resolve_history_db() so it "
            f"lands in the per-test tmp_path instead of {real_db}."
        )
        return real_connect(database, *args, **kwargs)

    mp = pytest.MonkeyPatch()
    mp.setattr(session_store.sqlite3, "connect", guarded_connect)
    try:
        yield
    finally:
        mp.undo()


# =============================================================================
# Session-log directory isolation (BUG-2489)
# =============================================================================


@pytest.fixture(scope="session")
def _shared_fake_home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One empty fake home per (xdist worker) process.

    Shared across tests because production ``Path.home()`` consumers
    (``user_messages.py``, ``cli/logs.py``) only read/glob under home — nothing
    writes — so an always-empty shared dir cannot cross-contaminate tests.
    Sharing it avoids a per-test tmp_path + mkdir for all ~13.7k tests (see
    ``_isolate_history_db`` for why that churn matters).
    """
    return tmp_path_factory.mktemp("fake_home")


@pytest.fixture(autouse=True)
def _isolate_session_log_dir(
    _shared_fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    """Redirect host session-log resolution away from the real ~/.claude/projects dir.

    BUG-2489: ``get_current_session_jsonl`` → ``get_project_folder`` resolves the
    live host's session directory under ``Path.home()``. Tests that exercise
    lifecycle emitters (e.g. ``complete_issue_lifecycle`` →
    ``append_session_log_entry``) would otherwise glob/stat the *real* JSONL files
    the live Claude Code process is actively writing, producing a TOCTOU flake that
    only surfaces under some xdist shardings.

    ``get_project_folder`` is imported *by reference* into six modules, so the single
    true choke point they all share is ``pathlib.Path.home`` (via
    ``_get_claude_project_folder`` / ``_get_codex_project_folder``). Pointing it at an
    empty per-test temp home makes resolution return ``None`` instead of racing the
    host. This mirrors the BUG-1995 ``_isolate_history_db`` convention.

    Function-scoped and monkeypatch-based so per-test ``Path.home`` overrides
    (e.g. ``TestSessionLogHostAware`` and the ``test_ll_logs.py`` host-aware tests)
    run *after* this fixture and win — composition, not conflict. Only the
    (empty, read-only-by-convention) home directory itself is session-scoped.
    """
    monkeypatch.setattr(Path, "home", lambda: _shared_fake_home)
    yield


# =============================================================================
# cmd_run env-var isolation (BUG-2011 follow-up)
# =============================================================================

# Env vars scrubbed for the duration of every test.  Two distinct hazards:
#
# 1. Leak-out (BUG-2011): cmd_run() writes these directly via os.environ (not
#    monkeypatch), so a test calling cmd_run() with --handoff-threshold,
#    --context-limit, or --worktree leaks the written value into later tests.
# 2. Leak-in: LL_AUTOMATION is exported into the whole descendant process tree
#    by host_runner (automation_profile -> env["LL_AUTOMATION"]="1"), so a
#    `python -m pytest` run from inside an ll-auto / FSM-loop session inherits
#    it.  The ENH-2714 pruning gates in hooks/session_start.py and
#    cli/history_context.py then suppress their output, breaking 48 tests that
#    assert the ordinary non-automation behaviour.  Tests that *want* the gate
#    monkeypatch.setenv() it in the test body, which still wins over this.
#
# The setenv("") + delenv() pattern registers a teardown for the var even when
# it was absent before the test, so a direct write is always undone at cleanup.
_CMD_RUN_ENV_VARS = (
    "LL_HANDOFF_THRESHOLD",
    "LL_CONTEXT_LIMIT",
    "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR",
    "LL_HOST_CLI",
    "LL_HOOK_HOST",
    "LL_AUTOMATION",
    "LL_AUTOMATION_PROFILE",
    "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS",
)


@pytest.fixture(autouse=True)
def _restore_cmd_run_env_vars(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Scrub env vars that leak into or out of a test via raw os.environ."""
    for var in _CMD_RUN_ENV_VARS:
        monkeypatch.setenv(var, "")
        monkeypatch.delenv(var)
    yield


# =============================================================================
# Deprecated-frontmatter-key warning ledger
# =============================================================================


@pytest.fixture(autouse=True)
def _reset_deprecated_key_warnings() -> Generator[None, None, None]:
    """Clear ``issue_parser``'s once-per-process deprecated-key warning ledger.

    The ledger suppresses repeat warnings for a path already reported, so
    without this reset the first test to parse a given file would swallow the
    warning for every later test that parses the same path — making
    warning-assertion tests order-dependent.
    """
    reset_deprecated_key_warnings()
    yield
    reset_deprecated_key_warnings()
