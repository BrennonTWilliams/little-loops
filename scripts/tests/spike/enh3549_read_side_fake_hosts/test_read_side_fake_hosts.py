"""AC suite for the ENH-3549 read-side divergent-fake spike.

Retires the issue's flagged risk: "no precedent injects a fake host into
session discovery" -- and no test drives the read side of the seam with two
divergently shaped hosts. Every test drives the *real* ``detect_sessions`` /
``iter_events`` / ``explain_no_sessions`` against fixture homes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from scripts.tests.spike.enh3549_read_side_fake_hosts.fake_read_hosts import (
    FAKE_HOSTS,
    install_fake_read_hosts,
    read_prompts,
    write_fake_minimal_session,
    write_fake_session,
)

from little_loops.session_store import sessions
from little_loops.session_store.sessions import NoSessionsCause, detect_sessions, iter_events

PROMPTS = ["first prompt", "second prompt"]


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Path]:
    cwd = tmp_path / "project"
    cwd.mkdir()
    return tmp_path / "home", cwd


class TestDiscovery:
    def test_fakes_unknown_to_seam_without_install(self, workspace):
        home, cwd = workspace
        write_fake_session(home, cwd, "s1", PROMPTS)
        assert detect_sessions(cwd, "fake", home=home) == []
        assert "fake" not in sessions._REGISTERED_HOSTS

    def test_both_fakes_discovered_via_real_detect_sessions(self, workspace, monkeypatch):
        home, cwd = workspace
        install_fake_read_hosts(monkeypatch)
        write_fake_session(home, cwd, "s1", PROMPTS)
        write_fake_minimal_session(home, cwd, "s2", PROMPTS)

        for host, sid in (("fake", "s1"), ("fake-minimal", "s2")):
            [handle] = detect_sessions(cwd, host, home=home)
            assert (handle.host, handle.session_id, handle.cwd) == (host, sid, cwd)

    def test_union_discovery_carries_both_fake_hosts(self, workspace, monkeypatch):
        home, cwd = workspace
        install_fake_read_hosts(monkeypatch)
        write_fake_session(home, cwd, "s1", PROMPTS)
        write_fake_minimal_session(home, cwd, "s2", PROMPTS)

        hosts = {h.host for h in detect_sessions(cwd, None, home=home)}
        assert hosts == set(FAKE_HOSTS)


class TestHostAgnosticRead:
    def test_divergent_shapes_yield_same_observation(self, workspace, monkeypatch):
        home, cwd = workspace
        install_fake_read_hosts(monkeypatch)
        write_fake_session(home, cwd, "s1", PROMPTS)
        write_fake_minimal_session(home, cwd, "s2", PROMPTS)

        observed = {
            host: read_prompts(detect_sessions(cwd, host, home=home)) for host in FAKE_HOSTS
        }
        assert observed["fake"] == observed["fake-minimal"] == PROMPTS

    def test_raw_payloads_really_diverge(self, workspace, monkeypatch):
        home, cwd = workspace
        install_fake_read_hosts(monkeypatch)
        write_fake_session(home, cwd, "s1", PROMPTS)
        write_fake_minimal_session(home, cwd, "s2", PROMPTS)

        keys = {
            host: frozenset(next(iter_events(detect_sessions(cwd, host, home=home)[0])).payload)
            for host in FAKE_HOSTS
        }
        assert keys["fake"] != keys["fake-minimal"]

    def test_real_hosts_still_resolve_with_fakes_installed(self, workspace, monkeypatch):
        home, cwd = workspace
        install_fake_read_hosts(monkeypatch)
        assert detect_sessions(cwd, "codex", home=home) == []
        assert detect_sessions(cwd, "qwen", home=home) == []


class TestNamedCause:
    def test_explain_no_sessions_survives_fake_registration(self, workspace, monkeypatch):
        home, cwd = workspace
        install_fake_read_hosts(monkeypatch)
        cause, message = sessions.explain_no_sessions(cwd, None, home=home)
        assert isinstance(cause, NoSessionsCause)
        assert message

    def test_fake_host_absence_is_named_not_empty(self, workspace, monkeypatch):
        home, cwd = workspace
        install_fake_read_hosts(monkeypatch)
        cause, message = sessions.explain_no_sessions(cwd, "fake", home=home)
        assert isinstance(cause, NoSessionsCause)
        assert message


class TestIsolation:
    def test_patches_undone_after_test(self):
        assert "fake" not in sessions._PARSERS
        assert "fake" not in sessions._REGISTERED_HOSTS
        assert "fake" not in sessions._LAYOUT_HOSTS

    def test_guard_spike_does_not_edit_production_registries(self):
        """Regression guard: the spike only ever touches registries via monkeypatch."""
        src = Path(__file__).with_name("fake_read_hosts.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        offenders = []
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            for t in targets:
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute):
                    if t.value.attr in ("_PARSERS", "_REGISTERED_HOSTS", "_LAYOUT_HOSTS"):
                        offenders.append(node.lineno)
                if isinstance(t, ast.Attribute) and t.attr in (
                    "_PARSERS",
                    "_REGISTERED_HOSTS",
                    "_LAYOUT_HOSTS",
                ):
                    offenders.append(node.lineno)
        assert offenders == []
