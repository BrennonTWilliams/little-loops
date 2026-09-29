"""Conformance coverage for divergent fake session readers (ENH-3649).

Retires the issue's flagged risk: "no precedent injects a fake host into
session discovery" -- and no test drives the read side of the seam with two
divergently shaped hosts. Every test drives the *real* ``detect_sessions`` /
``iter_events`` / ``explain_no_sessions`` against fixture homes.
"""

from __future__ import annotations

import ast
import json
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.session_store import sessions
from little_loops.session_store.sessions import NoSessionsCause, detect_sessions, iter_events
from little_loops.user_messages import (
    _USER_MESSAGE_READERS,
    encode_project_path,
    extract_user_messages,
)
from tests.conformance.fake_read_hosts import (
    FAKE_HOSTS,
    install_fake_read_hosts,
    read_prompts,
    write_fake_minimal_session,
    write_fake_session,
)

pytestmark = pytest.mark.conformance

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
            host: frozenset(
                next(iter_events(detect_sessions(cwd, host, home=home)[0])).payload["raw"]
            )
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


class TestConsumerReadback:
    def test_extract_user_messages_dispatches_both_fake_hosts(self, workspace, monkeypatch):
        home, cwd = workspace
        install_fake_read_hosts(monkeypatch)
        write_fake_session(home, cwd, "s1", PROMPTS)
        write_fake_minimal_session(home, cwd, "s2", PROMPTS)

        handles = detect_sessions(cwd, None, home=home)
        assert {h.host for h in handles} == set(FAKE_HOSTS)
        messages = extract_user_messages(handles)
        assert Counter(m.content for m in messages) == Counter(dict.fromkeys(PROMPTS, 2))
        assert {m.session_id for m in messages} == {"s1", "s2"}
        assert extract_user_messages(handles, include_agent_sessions=False) == messages

    def test_agent_and_real_host_selection_survive_fake_registration(self, workspace, monkeypatch):
        home, cwd = workspace
        install_fake_read_hosts(monkeypatch)
        write_fake_session(home, cwd, "s1", ["fake prompt"])
        write_fake_session(home, cwd, "agent-s2", ["agent prompt"])
        claude_dir = home / ".claude" / "projects" / encode_project_path(str(cwd))
        claude_dir.mkdir(parents=True)
        (claude_dir / "real.jsonl").write_text(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": "2026-09-24T10:00:00Z",
                    "message": {"content": "real prompt"},
                }
            )
            + "\n"
        )
        handles = detect_sessions(cwd, None, home=home, include_agents=True)
        assert {h.session_id for h in handles} == {"s1", "agent-s2", "real"}
        assert {
            m.content for m in extract_user_messages(handles, include_agent_sessions=False)
        } == {
            "fake prompt",
            "real prompt",
        }
        assert {m.content for m in extract_user_messages(handles)} == {
            "fake prompt",
            "agent prompt",
            "real prompt",
        }

    def test_ll_messages_cli_reads_both_fake_hosts(self, workspace, monkeypatch, capsys):
        from little_loops.cli.messages import main_messages

        home, cwd = workspace
        install_fake_read_hosts(monkeypatch)
        write_fake_session(home, cwd, "s1", PROMPTS)
        write_fake_minimal_session(home, cwd, "s2", PROMPTS)
        monkeypatch.setattr(Path, "home", lambda: home)
        monkeypatch.chdir(cwd)
        monkeypatch.delenv("LL_HOOK_HOST", raising=False)
        with patch.object(sys, "argv", ["ll-messages", "--stdout", "--cwd", str(cwd)]):
            assert main_messages() == 0
        lines = [
            json.loads(line)
            for line in capsys.readouterr().out.splitlines()
            if line.startswith("{")
        ]
        assert Counter(row["content"] for row in lines) == Counter(dict.fromkeys(PROMPTS, 2))

    def test_ll_logs_extract_reads_both_fake_hosts(self, workspace, monkeypatch, capsys):
        from little_loops.cli.logs import main_logs

        home, cwd = workspace
        install_fake_read_hosts(monkeypatch)
        prompts = ["<command-name>/ll:manage-issue", "<command-name>/ll:review-loop"]
        write_fake_session(home, cwd, "s1", prompts)
        write_fake_minimal_session(home, cwd, "s2", prompts)
        monkeypatch.setattr(Path, "home", lambda: home)
        monkeypatch.chdir(cwd)
        monkeypatch.delenv("LL_HOOK_HOST", raising=False)
        with patch.object(sys, "argv", ["ll-logs", "extract", "--project", str(cwd), "--json"]):
            assert main_logs() == 0
        output = capsys.readouterr().out
        doc = json.loads(output)
        assert doc["totals"]["sessions"] == 2
        assert doc["totals"]["records"] == 4
        assert {p.stem for p in (cwd / "logs" / cwd.name).glob("*.jsonl")} == {"s1", "s2"}


class TestIsolation:
    def test_patches_undone_after_test(self):
        assert "fake" not in sessions._PARSERS
        assert "fake" not in sessions._REGISTERED_HOSTS
        assert "fake" not in sessions._LAYOUT_HOSTS
        assert "fake" not in _USER_MESSAGE_READERS

    def test_fake_fixture_does_not_edit_production_registries(self):
        """Regression guard: fixture writes registries only via monkeypatch."""
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
