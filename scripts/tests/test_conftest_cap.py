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

    def test_invalid_env_var_falls_back_to_cpu_half(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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

    def test_fourteen_cpu_count_yields_seven(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
