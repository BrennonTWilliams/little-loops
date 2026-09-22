"""Guard-policy matrix for ``tests.helpers.require_node`` (BUG-3522).

Kept in its own module so ``test_policy_builder_node_gate.py`` stays six
executable conformance/round-trip cases and this file owns the mocked
success/failure/skip matrix shared by all four Node-dependent gates
(``test_node_conformance_suite_passes``, ``test_round_trip_yaml_validates_for_each_mode``,
``TestDashboardNodeRuntimeGate::test_generated_page_runtime_behaviour``, and
``test_smoke_harness_survives_non_string_pageerror_message``) via
``require_node()``. None of these tests shell out to a real ``node`` —
``subprocess.run`` and ``shutil.which`` are mocked so the matrix runs
regardless of whether Node is installed.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from tests import helpers


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


@pytest.fixture(autouse=True)
def _no_real_node_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test controls LL_REQUIRE_NODE explicitly; start unset."""
    monkeypatch.delenv("LL_REQUIRE_NODE", raising=False)


def test_missing_node_skips_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers.shutil, "which", lambda _: None)
    with pytest.raises(pytest.skip.Exception, match="not found"):
        helpers.require_node()


def test_missing_node_fails_with_require_node_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LL_REQUIRE_NODE", "1")
    monkeypatch.setattr(helpers.shutil, "which", lambda _: None)
    with pytest.raises(pytest.fail.Exception, match="not found"):
        helpers.require_node()


def test_node_below_min_major_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(helpers.subprocess, "run", lambda *a, **kw: _proc(0, stdout="v18.19.0\n"))
    with pytest.raises(pytest.skip.Exception, match="Node >= 22"):
        helpers.require_node()


def test_node_below_min_major_fails_with_require_node_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LL_REQUIRE_NODE", "1")
    monkeypatch.setattr(helpers.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(helpers.subprocess, "run", lambda *a, **kw: _proc(0, stdout="v18.19.0\n"))
    with pytest.raises(pytest.fail.Exception, match="Node >= 22"):
        helpers.require_node()


def test_malformed_version_output_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(
        helpers.subprocess, "run", lambda *a, **kw: _proc(0, stdout="not-a-version\n")
    )
    with pytest.raises(pytest.skip.Exception, match="could not parse"):
        helpers.require_node()


def test_malformed_version_output_fails_with_require_node_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LL_REQUIRE_NODE", "1")
    monkeypatch.setattr(helpers.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(
        helpers.subprocess, "run", lambda *a, **kw: _proc(0, stdout="not-a-version\n")
    )
    with pytest.raises(pytest.fail.Exception, match="could not parse"):
        helpers.require_node()


def test_nonzero_probe_exit_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(helpers.subprocess, "run", lambda *a, **kw: _proc(1, stderr="boom"))
    with pytest.raises(pytest.skip.Exception, match="exited 1"):
        helpers.require_node()


def test_nonzero_probe_exit_fails_with_require_node_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LL_REQUIRE_NODE", "1")
    monkeypatch.setattr(helpers.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(helpers.subprocess, "run", lambda *a, **kw: _proc(1, stderr="boom"))
    with pytest.raises(pytest.fail.Exception, match="exited 1"):
        helpers.require_node()


def test_oserror_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers.shutil, "which", lambda _: "/usr/bin/node")

    def _raise(*a: object, **kw: object) -> None:
        raise OSError("no exec permission")

    monkeypatch.setattr(helpers.subprocess, "run", _raise)
    with pytest.raises(pytest.skip.Exception, match="could not be run"):
        helpers.require_node()


def test_oserror_fails_with_require_node_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LL_REQUIRE_NODE", "1")
    monkeypatch.setattr(helpers.shutil, "which", lambda _: "/usr/bin/node")

    def _raise(*a: object, **kw: object) -> None:
        raise OSError("no exec permission")

    monkeypatch.setattr(helpers.subprocess, "run", _raise)
    with pytest.raises(pytest.fail.Exception, match="could not be run"):
        helpers.require_node()


def test_timeout_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers.shutil, "which", lambda _: "/usr/bin/node")

    def _raise(*a: object, **kw: object) -> None:
        raise subprocess.TimeoutExpired(cmd=["node", "--version"], timeout=30)

    monkeypatch.setattr(helpers.subprocess, "run", _raise)
    with pytest.raises(pytest.skip.Exception, match="timed out"):
        helpers.require_node()


def test_timeout_fails_with_require_node_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LL_REQUIRE_NODE", "1")
    monkeypatch.setattr(helpers.shutil, "which", lambda _: "/usr/bin/node")

    def _raise(*a: object, **kw: object) -> None:
        raise subprocess.TimeoutExpired(cmd=["node", "--version"], timeout=30)

    monkeypatch.setattr(helpers.subprocess, "run", _raise)
    with pytest.raises(pytest.fail.Exception, match="timed out"):
        helpers.require_node()


def test_successful_node_returns_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(helpers.subprocess, "run", lambda *a, **kw: _proc(0, stdout="v26.0.0\n"))
    assert helpers.require_node() == "/usr/bin/node"


def test_min_major_none_accepts_any_successfully_probed_major(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(helpers.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(helpers.subprocess, "run", lambda *a, **kw: _proc(0, stdout="v16.20.0\n"))
    assert helpers.require_node(min_major=None) == "/usr/bin/node"


def test_min_major_none_still_fails_when_node_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LL_REQUIRE_NODE", "1")
    monkeypatch.setattr(helpers.shutil, "which", lambda _: None)
    with pytest.raises(pytest.fail.Exception, match="not found"):
        helpers.require_node(min_major=None)


def test_successful_run_prints_the_probed_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Retention requirement: the exact probed version reaches captured
    stdout on success, so junit_logging="system-out" carries it into the
    uploaded pytest-junit.xml artifact on a passing CI run (BUG-3522)."""
    monkeypatch.setattr(helpers.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(helpers.subprocess, "run", lambda *a, **kw: _proc(0, stdout="v26.0.0\n"))
    helpers.require_node()
    assert "v26.0.0" in capsys.readouterr().out
