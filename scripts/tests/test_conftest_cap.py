"""Regression tests for ``scripts/tests/conftest.py`` cap+nice hooks (BUG-2501).

The conftest enforces two things that prevent the macOS "beachball of death"
during ``python -m pytest scripts/tests/``:

- ``pytest_xdist_auto_num_workers`` caps xdist workers to ``cpus // 2`` (floor 2)
  so the suite does not pin every logical core at 100 % CPU.
- ``pytest_configure`` calls ``os.nice(10)`` so pytest processes yield to the
  macOS compositor when WindowServer is under contention.

Both knobs have explicit override environment variables
(``PYTEST_XDIST_AUTO_NUM_WORKERS`` and ``LL_TEST_NO_NICE``) and these tests
pin that contract.

Note: ``scripts/tests/conftest.py`` is not normally importable as a module —
it is loaded by pytest as a ``conftest`` plugin. Load it explicitly via
``importlib.util.spec_from_file_location``.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_CONFTEST_PATH = Path(__file__).parent / "conftest.py"
_spec = importlib.util.spec_from_file_location("conftest_under_test", _CONFTEST_PATH)
assert _spec is not None and _spec.loader is not None
conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conftest)


class TestXdistAutoNumWorkers:
    """``pytest_xdist_auto_num_workers`` returns the worker count to spawn.

    Behavior under test (see ``scripts/tests/conftest.py:30-53``):

    - ``PYTEST_XDIST_AUTO_NUM_WORKERS=<N>`` env var wins, parsed as int.
    - Invalid env var falls back to ``max(2, cpus // 2)``.
    - ``cpus // 2`` has a floor of 2 (so even 1-CPU hosts spawn 2 workers).
    """

    def test_env_var_overrides_cpu_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``PYTEST_XDIST_AUTO_NUM_WORKERS=<N>`` returns N verbatim."""
        monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", "3")
        assert conftest.pytest_xdist_auto_num_workers(MagicMock()) == 3

    def test_invalid_env_var_falls_back_to_cpu_half(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-integer env var is ignored; ``cpus // 2`` wins."""
        monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", "notanumber")
        with patch("os.cpu_count", return_value=14):
            assert conftest.pytest_xdist_auto_num_workers(MagicMock()) == 7

    def test_zero_cpu_count_floors_at_two(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``os.cpu_count() == 0`` must floor to 2, not crash."""
        monkeypatch.delenv("PYTEST_XDIST_AUTO_NUM_WORKERS", raising=False)
        with patch("os.cpu_count", return_value=0):
            assert conftest.pytest_xdist_auto_num_workers(MagicMock()) == 2

    def test_one_cpu_count_floors_at_two(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``os.cpu_count() == 1`` (single-core) must floor to 2."""
        monkeypatch.delenv("PYTEST_XDIST_AUTO_NUM_WORKERS", raising=False)
        with patch("os.cpu_count", return_value=1):
            assert conftest.pytest_xdist_auto_num_workers(MagicMock()) == 2

    def test_four_cpu_count_yields_two(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``os.cpu_count() == 4`` → 4 // 2 == 2."""
        monkeypatch.delenv("PYTEST_XDIST_AUTO_NUM_WORKERS", raising=False)
        with patch("os.cpu_count", return_value=4):
            assert conftest.pytest_xdist_auto_num_workers(MagicMock()) == 2

    def test_fourteen_cpu_count_yields_seven(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``os.cpu_count() == 14`` (M4) → 14 // 2 == 7 (no env override)."""
        monkeypatch.delenv("PYTEST_XDIST_AUTO_NUM_WORKERS", raising=False)
        with patch("os.cpu_count", return_value=14):
            assert conftest.pytest_xdist_auto_num_workers(MagicMock()) == 7


class TestPytestConfigureNice:
    """``pytest_configure`` lowers pytest scheduling priority via ``os.nice``.

    Behavior under test (see ``scripts/tests/conftest.py:56-74``):

    - ``LL_TEST_NO_NICE=1`` short-circuits — no ``os.nice`` call.
    - Default path calls ``os.nice(10)`` exactly once.
    - Non-POSIX (no ``os.nice`` attribute) returns silently.
    - ``OSError`` from ``os.nice`` is swallowed (already niced processes can
      raise on some platforms).
    """

    def test_no_nice_env_short_circuits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``LL_TEST_NO_NICE=1`` must NOT call ``os.nice``."""
        monkeypatch.setenv("LL_TEST_NO_NICE", "1")
        with patch("os.nice") as mock_nice:
            conftest.pytest_configure(MagicMock())
        mock_nice.assert_not_called()

    def test_default_path_calls_nice_with_ten(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default path calls ``os.nice(10)``."""
        monkeypatch.delenv("LL_TEST_NO_NICE", raising=False)
        with patch("os.nice", return_value=10) as mock_nice:
            conftest.pytest_configure(MagicMock())
        mock_nice.assert_called_once_with(10)

    def test_non_posix_returns_silently(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When ``os.nice`` is absent (non-POSIX), pytest_configure does nothing.

        Exercises the ``hasattr(os, "nice")`` gate at ``conftest.py:67``.
        Patching ``os.nice`` is insufficient because ``hasattr`` would still
        see the Mock attribute; the test must physically delete the attribute
        so the gate fires.
        """
        import os as _os

        monkeypatch.delenv("LL_TEST_NO_NICE", raising=False)
        monkeypatch.delattr(_os, "nice", raising=False)
        assert not hasattr(_os, "nice"), "test setup: os.nice must be absent"
        # Must not raise; ``hasattr(os, "nice")`` gate is exercised.
        conftest.pytest_configure(MagicMock())

    def test_os_error_from_nice_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``OSError`` from ``os.nice`` (e.g. permission, or already-niced)
        is swallowed — pytest must still configure cleanly."""
        monkeypatch.delenv("LL_TEST_NO_NICE", raising=False)
        with patch("os.nice", side_effect=OSError("EPERM")):
            # Must not raise.
            conftest.pytest_configure(MagicMock())


class TestNoParallelMarkerRouting:
    """``pytest_collection_modifyitems`` skips ``no_parallel``-marked tests on
    xdist workers (BUG-2523).

    Behavior under test (see ``scripts/tests/conftest.py``):

    - Controller (no ``workerinput`` attribute or falsy) → marked tests are
      collected unchanged, no skip marker is added.
    - xdist worker (``workerinput={"workerid": "gw0"}``) → each item with the
      ``no_parallel`` keyword receives a ``pytest.mark.skip`` marker.
    """

    @staticmethod
    def _make_item(*, marked: bool) -> MagicMock:
        item = MagicMock()
        item.keywords = {"no_parallel"} if marked else set()
        return item

    def test_xdist_worker_skips_no_parallel_item(self) -> None:
        """On an xdist worker, a ``no_parallel``-marked item receives a skip marker."""
        config = MagicMock()
        config.workerinput = {"workerid": "gw0"}  # xdist-worker signal
        item = self._make_item(marked=True)

        conftest.pytest_collection_modifyitems(config, [item])

        # At least one add_marker call must be a skip with the no_parallel reason.
        skip_calls = [
            call_args
            for call_args in item.add_marker.call_args_list
            if call_args.args
            and isinstance(call_args.args[0], pytest.MarkDecorator)
            and call_args.args[0].mark.name == "skip"
            and "no_parallel" in call_args.args[0].mark.kwargs.get("reason", "")
        ]
        assert skip_calls, (
            "expected no_parallel-marked item to receive a skip marker on an xdist worker"
        )

    def test_xdist_worker_does_not_skip_unmarked_item(self) -> None:
        """On an xdist worker, an unmarked item is left untouched."""
        config = MagicMock()
        config.workerinput = {"workerid": "gw0"}
        item = self._make_item(marked=False)

        conftest.pytest_collection_modifyitems(config, [item])

        item.add_marker.assert_not_called()

    def test_controller_does_not_skip_no_parallel_item(self) -> None:
        """On the controller (no ``workerinput``), the hook leaves items unmarked.

        The hook returns early without mutating items — but under ``-n N``
        the controller only collects and distributes work, it never runs
        tests itself. So this "not skipped" is only actually exercised in a
        serial ``-n 0`` run; under default addopts the item is skipped on
        every worker it lands on.
        """
        # No `workerinput` attribute at all → controller.
        config = MagicMock(spec=["pluginmanager"])
        assert not hasattr(config, "workerinput"), (
            "test setup: controller config must not expose workerinput"
        )
        item = self._make_item(marked=True)

        conftest.pytest_collection_modifyitems(config, [item])

        item.add_marker.assert_not_called()

    def test_controller_with_falsy_workerinput_does_not_skip(self) -> None:
        """A ``workerinput`` attribute set to a falsy value behaves like a controller."""
        config = MagicMock()
        config.workerinput = None  # attribute exists but is falsy
        item = self._make_item(marked=True)

        conftest.pytest_collection_modifyitems(config, [item])

        item.add_marker.assert_not_called()


class TestNoLiveHostCLIGuard:
    """Live host-CLI spawn guard (FEAT-3329).

    Unit-tests the pure helpers directly rather than a real teardown: a test
    cannot assert that its own teardown fails (by the time
    ``_fail_on_live_host_cli``'s post-yield body runs, the test body has
    already completed), and this file's standalone-loaded ``conftest``
    module holds a *separate* collector instance from the live plugin's, so
    seeding one has no effect on the other either way.
    """

    @pytest.fixture(autouse=True)
    def _reset_collector(self) -> None:
        conftest._host_cli_hits.clear()
        conftest._reported_upto = 0
        yield
        conftest._host_cli_hits.clear()
        conftest._reported_upto = 0

    # -- _extract_argv: normalize every argv form CPython accepts -----------

    def test_extract_argv_list(self) -> None:
        assert conftest._extract_argv((["claude", "-p", "hi"],), {}) == [
            "claude",
            "-p",
            "hi",
        ]

    def test_extract_argv_tuple(self) -> None:
        assert conftest._extract_argv((("claude", "-p"),), {}) == ["claude", "-p"]

    def test_extract_argv_shell_true_string_is_pass_through(self) -> None:
        """Accepted gap: a shell=True string command is not a program name."""
        assert conftest._extract_argv(("claude -p hi",), {"shell": True}) is None

    def test_extract_argv_pathlike_program(self) -> None:
        assert conftest._extract_argv((Path("/usr/bin/claude"),), {}) == ["/usr/bin/claude"]

    def test_extract_argv_pathlike_element(self) -> None:
        assert conftest._extract_argv(([Path("/usr/bin/claude"), "-p"],), {}) == [
            "/usr/bin/claude",
            "-p",
        ]

    def test_extract_argv_empty_sequence(self) -> None:
        assert conftest._extract_argv(([],), {}) is None

    def test_extract_argv_args_keyword(self) -> None:
        assert conftest._extract_argv((), {"args": ["claude", "-p"]}) == [
            "claude",
            "-p",
        ]

    def test_extract_argv_nothing_provided(self) -> None:
        assert conftest._extract_argv((), {}) is None

    def test_extract_argv_non_subscriptable_first_arg(self) -> None:
        assert conftest._extract_argv((42,), {}) is None

    # -- _match_host_binary: basename check + --version carve-out -----------

    def test_match_host_binary_matches_known_binary(self) -> None:
        assert conftest._match_host_binary((["claude", "-p", "hi"],), {}) == (
            "claude",
            ["claude", "-p", "hi"],
        )

    def test_match_host_binary_none_for_unrelated_binary(self) -> None:
        assert conftest._match_host_binary((["git", "status"],), {}) is None

    def test_match_host_binary_carve_out_version_check_list(self) -> None:
        assert conftest._match_host_binary((["claude", "--version"],), {}) is None

    def test_match_host_binary_carve_out_version_check_tuple(self) -> None:
        """argv may arrive as a tuple; the carve-out must coerce via list()."""
        assert conftest._match_host_binary((("claude", "--version"),), {}) is None

    def test_match_host_binary_does_not_carve_out_other_flags(self) -> None:
        assert conftest._match_host_binary((["claude", "-p", "hi"],), {}) is not None

    # -- _record_and_build_error / _drain_new_hits: collector + cursor ------

    def test_record_and_build_error_records_hit_and_builds_exception(self) -> None:
        err = conftest._record_and_build_error("claude", ["claude", "-p"])
        assert isinstance(err, conftest._LiveHostCLISpawn)
        assert "claude" in str(err)
        assert len(conftest._host_cli_hits) == 1

    def test_drain_new_hits_returns_message_then_none(self) -> None:
        """The _evaluate-swallow property in durable form: a recorded hit
        surfaces even when nothing propagated the raise."""
        conftest._record_and_build_error("claude", ["claude", "-p"])

        first = conftest._drain_new_hits()
        assert first is not None
        assert "claude" in first

        assert conftest._drain_new_hits() is None

    def test_drain_new_hits_no_hits_returns_none(self) -> None:
        assert conftest._drain_new_hits() is None

    def test_drain_new_hits_dedupes_repeated_spawns_with_count(self) -> None:
        conftest._record_and_build_error("claude", ["claude", "-p"])
        conftest._record_and_build_error("claude", ["claude", "-p"])
        conftest._record_and_build_error("claude", ["claude", "-p"])

        msg = conftest._drain_new_hits()

        assert msg is not None
        assert msg.count("spawned `claude`") == 1
        assert "(x3)" in msg

    def test_drain_new_hits_two_tests_one_spawner_reports_once(self) -> None:
        """Two consecutive tests where only the first spawns must produce
        exactly one report, not a cascade across the rest of the worker."""
        conftest._record_and_build_error("claude", ["claude", "-p"])
        conftest._drain_new_hits()  # first test's teardown drains it

        # Second test spawns nothing; its teardown finds nothing new.
        assert conftest._drain_new_hits() is None

    def test_drain_new_hits_orphaned_entry_reported_by_next_call(self) -> None:
        """A hit appended outside any test's function-fixture window (a
        higher-scope fixture, a background thread) is still reported exactly
        once, attributed to the next call — the property a pre-yield len()
        snapshot silently loses."""
        conftest._host_cli_hits.append(("<no active test>", "codex"))

        msg = conftest._drain_new_hits()

        assert msg is not None
        assert "codex" in msg
        assert conftest._drain_new_hits() is None

    # -- _GuardedPopen: subclass-shaped, raises before super().__init__ -----

    def test_guarded_popen_is_a_popen_subclass(self) -> None:
        # Not `issubclass(conftest._GuardedPopen, subprocess.Popen)`: this
        # very test runs under the LIVE plugin's own `_install_no_live_host_cli`
        # session fixture, so by execution time `subprocess.Popen` is already
        # that fixture's own `_GuardedPopen` — a different class from this
        # standalone-loaded module's. Check the immediate base directly
        # instead of the live-patched module attribute.
        base = conftest._GuardedPopen.__mro__[1]
        assert base.__module__ == "subprocess"
        assert base.__name__ == "Popen"

    def test_guarded_popen_spec_mock_resolves_poll(self) -> None:
        """A function replacement would break this: a function spec exposes
        no Popen attributes, so .poll/.wait raise AttributeError."""
        mock = MagicMock(spec=conftest._GuardedPopen)
        assert mock.poll is not None
        assert mock.wait is not None

    def test_guarded_popen_is_subscriptable(self) -> None:
        """subprocess.Popen[str] subscripting must still work (nine
        production call sites depend on it); a function is not subscriptable."""
        assert conftest._GuardedPopen[str] is not None

    def test_guarded_popen_raises_and_records_before_init(self) -> None:
        with pytest.raises(conftest._LiveHostCLISpawn):
            conftest._GuardedPopen(["claude", "-p", "hi"])
        assert len(conftest._host_cli_hits) == 1

    def test_guarded_popen_passes_through_non_host_argv(self) -> None:
        """A non-host argv must fall through to the real Popen — verified via
        a command guaranteed to exist and exit immediately, never a host CLI."""
        proc = conftest._GuardedPopen([sys.executable, "-c", "pass"], stdout=subprocess.DEVNULL)
        proc.wait(timeout=5)
        assert proc.returncode == 0

    # -- pytest_sessionfinish: print-only summary, never load-bearing -------

    def test_sessionfinish_noop_when_nothing_to_report(self) -> None:
        session = MagicMock()
        conftest.pytest_sessionfinish(session, 0)
        session.config.pluginmanager.get_plugin.assert_not_called()

    def test_sessionfinish_reports_orphaned_hit_via_terminalreporter_and_warning(
        self,
    ) -> None:
        conftest._host_cli_hits.append(("tests/x.py::test_a", "claude"))
        session = MagicMock()
        terminalreporter = MagicMock()
        session.config.pluginmanager.get_plugin.return_value = terminalreporter

        with pytest.warns(UserWarning):
            conftest.pytest_sessionfinish(session, 0)

        terminalreporter.write_line.assert_called_once()
        assert "claude" in terminalreporter.write_line.call_args.args[0]
        # Draining is shared with the teardown fixture's helper, so a second
        # call finds nothing left to report.
        assert conftest._drain_new_hits() is None

    def test_sessionfinish_tolerates_missing_terminalreporter(self) -> None:
        conftest._host_cli_hits.append(("tests/x.py::test_a", "claude"))
        session = MagicMock()
        session.config.pluginmanager.get_plugin.return_value = None

        with pytest.warns(UserWarning):
            conftest.pytest_sessionfinish(session, 0)  # must not raise

    # -- Installer fixture: monkeypatches subprocess, restores on teardown --

    def test_install_fixture_patches_and_restores_subprocess(self) -> None:
        original_popen = subprocess.Popen
        original_run = subprocess.run

        gen = conftest._install_no_live_host_cli.__wrapped__()
        next(gen)
        try:
            assert subprocess.Popen is conftest._GuardedPopen
            assert subprocess.run is not original_run
        finally:
            with pytest.raises(StopIteration):
                next(gen)

        assert subprocess.Popen is original_popen
        assert subprocess.run is original_run

    def test_install_fixture_guarded_run_raises_on_host_binary(self) -> None:
        gen = conftest._install_no_live_host_cli.__wrapped__()
        next(gen)
        try:
            with pytest.raises(conftest._LiveHostCLISpawn):
                subprocess.run(["claude", "-p", "hi"])
        finally:
            with pytest.raises(StopIteration):
                next(gen)


class TestRateLimitLadderCollapsed:
    """The rate-limit ladder collapse fixture (FEAT-3329) is suite-wide.

    A direct assertion on the patched constants, not a sleep-observing
    probe: a probe's failure mode when this fixture regresses is a 300s
    sleep the thread-method watchdog cannot kill (the exact BUG-3208 wedge
    this issue exists to prevent), planted deliberately in the suite.
    """

    def test_ladder_and_max_wait_collapsed_by_default(self) -> None:
        from little_loops.fsm import executor as fsm_executor

        assert fsm_executor._DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER == [0]
        assert fsm_executor._DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS == 0
