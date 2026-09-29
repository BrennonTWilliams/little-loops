"""Callers of ``resolve_history_db`` under a remote history backend (BUG-3652).

``resolve_history_db()`` raises ``HistoryBackendNotLocal`` for a remote store, so a caller
that pre-resolves through it aborts (or silently drops its write) before the target-aware
``schema.connect`` seam is reached. This module pins:

* a caller gate: no ``resolve_history_db()`` call outside ``session_store/`` except the
  reasoned allowlist (reader CLIs owned by ENH-3657, already-remote-aware sites);
* a degrade-handler gate over ``session_store/writers.py``;
* behavior of the converted startup / write / read sites against the Hrana stub.

The caller gate only sees Python ``ast.Call`` nodes under ``scripts/little_loops/``;
``skills/``, ``hooks/scripts/`` and loop-YAML callers are outside its reach.
"""

from __future__ import annotations

import ast
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from little_loops.fsm.continuity import summarize_completed_state
from little_loops.session_store import (
    DEFAULT_DB_PATH,
    SQLiteTransport,
    remote_schema,
    remote_telemetry,
)
from little_loops.session_store import db as db_mod
from little_loops.session_store import writers as writers_mod
from little_loops.session_store.hrana import HranaClient
from tests.hrana_stub import HranaStub

TOKEN = "sentinel-token-DO-NOT-LEAK"

_SRC_ROOT = Path(__file__).resolve().parent.parent / "little_loops"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_remote_config(tmp_path: Path, url: str) -> None:
    (tmp_path / ".ll").mkdir(exist_ok=True)
    (tmp_path / ".ll" / "ll-config.json").write_text(
        json.dumps(
            {
                "history": {
                    "backend": {
                        "provider": "libsql",
                        "url_env": "LL_HISTORY_URL",
                        "project_id": "acme-api",
                    }
                }
            }
        )
    )


@pytest.fixture
def remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[HranaStub]:
    stub = HranaStub(token=TOKEN).start()
    monkeypatch.setenv("LL_HISTORY_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("LL_HISTORY_URL", stub.url)
    monkeypatch.delenv("LL_HISTORY_DB", raising=False)
    monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)
    _write_remote_config(tmp_path, stub.url)
    monkeypatch.chdir(tmp_path)
    remote_schema.clear_verification_cache()
    remote_telemetry.reset_for_tests()
    db_mod.clear_backend_config_cache()
    remote_schema.migrate_remote(HranaClient(stub.url, TOKEN), "acme-api")
    try:
        yield stub
    finally:
        stub.stop()
        remote_schema.clear_verification_cache()
        remote_telemetry.reset_for_tests()
        db_mod.clear_backend_config_cache()


def _count(stub: HranaStub, table: str) -> int:
    return int(stub.db.execute(f"select count(*) from {table}").fetchone()[0])


# ---------------------------------------------------------------------------
# Caller gate
# ---------------------------------------------------------------------------

# (path relative to scripts/little_loops, enclosing function) -> reason.
_CALLER_ALLOWLIST: dict[tuple[str, str], str] = {
    ("cli/doctor.py", "_schema_drift_data"): "already remote-aware (early return on RemoteTarget)",
    (
        "cli/session.py",
        "main_session",
    ): "already refuses via refuse_on_remote before resolving (refresh)",
    ("cli/ctx_stats.py", "main_ctx_stats"): "reader CLI -> ENH-3657",
    ("cli/harness.py", "_read_target_history"): "reader -> ENH-3657",
    ("cli/harness.py", "_retry_gate"): "reader -> ENH-3657",
    ("cli/harness.py", "_resolve_baseline_of"): "reader -> ENH-3657",
    ("cli/harness.py", "read_baseline"): "reader -> ENH-3657",
    ("cli/harness.py", "cmd_dsl"): "reader -> ENH-3657",
    ("cli/history.py", "main_history"): "reader CLI (8 sites) -> ENH-3657",
    ("cli/logs.py", "_cmd_diff"): "reader CLI -> ENH-3657",
    ("cli/logs.py", "_cmd_eval_export"): "reader CLI -> ENH-3657",
    ("decisions.py", "generate_from_completed"): "reader -> ENH-3657",
    ("mcp_server/tools.py", "_tool_history_search"): "reader -> ENH-3657",
    ("user_messages.py", "extract_conversation_turns"): "reader -> ENH-3657",
}


def _enclosing_functions(tree: ast.AST) -> dict[int, str]:
    owner: dict[int, str] = {}

    def visit(node: ast.AST, current: str) -> None:
        for child in ast.iter_child_nodes(node):
            nxt = current
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nxt = child.name
            owner[id(child)] = nxt
            visit(child, nxt)

    visit(tree, "<module>")
    return owner


def _resolve_history_db_calls(source: str) -> list[tuple[str, int]]:
    """(enclosing function, lineno) for each real ``resolve_history_db(...)`` call."""
    tree = ast.parse(source)
    owner = _enclosing_functions(tree)
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = (
            fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
        )
        if name == "resolve_history_db":
            hits.append((owner[id(node)], node.lineno))
    return hits


def _all_caller_keys() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(_SRC_ROOT).as_posix()
        if rel.startswith("session_store/"):
            continue
        for func, _line in _resolve_history_db_calls(path.read_text(encoding="utf-8")):
            keys.add((rel, func))
    return keys


class TestResolveHistoryDbCallerGate:
    def test_no_unlisted_caller_outside_session_store(self) -> None:
        stray = sorted(_all_caller_keys() - set(_CALLER_ALLOWLIST))
        assert not stray, (
            "resolve_history_db() raises HistoryBackendNotLocal under a remote backend; pass "
            "DEFAULT_DB_PATH to the writer (or use resolve_history_store) instead. Add a "
            f"reasoned allowlist entry only for a reader/refusing site: {stray}"
        )

    def test_allowlist_has_no_stale_entries(self) -> None:
        stale = sorted(set(_CALLER_ALLOWLIST) - _all_caller_keys())
        assert not stale, f"remove these fully-migrated allowlist entries: {stale}"

    def test_detector_rejects_a_stray_pre_resolve(self) -> None:
        src = (
            "from little_loops.session_store import SQLiteTransport, resolve_history_db\n"
            "def wire(bus):\n"
            "    bus.add_transport(SQLiteTransport(resolve_history_db()))\n"
            "def attr(db):\n"
            "    return db.resolve_history_db()\n"
        )
        assert _resolve_history_db_calls(src) == [("attr", 5), ("wire", 3)]

    def test_detector_ignores_docstring_mentions(self) -> None:
        src = 'def f():\n    """never ``resolve_history_db()`` here"""\n    return 1\n'
        assert _resolve_history_db_calls(src) == []


# ---------------------------------------------------------------------------
# writers.py degrade-handler gate
# ---------------------------------------------------------------------------


def _degrade_gate_violations(source: str) -> list[int]:
    """Line numbers of ``except sqlite3.Error`` handlers that swallow without HistoryError."""
    tree = ast.parse(source)
    bad: list[int] = []

    def names_sqlite_error(expr: ast.expr | None) -> bool:
        if expr is None:
            return False
        exprs = list(expr.elts) if isinstance(expr, ast.Tuple) else [expr]
        for e in exprs:
            if (
                isinstance(e, ast.Attribute)
                and e.attr == "Error"
                and isinstance(e.value, ast.Name)
                and e.value.id == "sqlite3"
            ):
                return True
            if isinstance(e, ast.Name) and e.id == "Error":  # ``from sqlite3 import Error``
                return True
        return False

    def names_history_error(expr: ast.expr | None) -> bool:
        if expr is None:
            return False
        exprs = list(expr.elts) if isinstance(expr, ast.Tuple) else [expr]
        return any(
            isinstance(e, ast.Name) and e.id in ("HistoryError", "_DEGRADE_ERRORS") for e in exprs
        )

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not names_sqlite_error(node.type) or names_history_error(node.type):
            continue
        if any(isinstance(n, ast.Raise) for n in ast.walk(node)):
            continue
        if all(isinstance(stmt, ast.Pass) for stmt in node.body):
            continue  # the ``conn.close()`` ``pass`` handlers are not degrade handlers
        bad.append(node.lineno)
    return bad


class TestWritersDegradeGate:
    def test_every_sqlite_error_degrade_handler_also_catches_history_errors(self) -> None:
        source = (_SRC_ROOT / "session_store" / "writers.py").read_text(encoding="utf-8")
        assert _degrade_gate_violations(source) == []

    def test_detector_rejects_a_planted_bare_sqlite_error_handler(self) -> None:
        src = (
            "import sqlite3\n"
            "def w():\n"
            "    try:\n"
            "        pass\n"
            "    except sqlite3.Error:\n"
            "        return False\n"
        )
        assert _degrade_gate_violations(src) == [5]

    def test_detector_rejects_an_aliased_error_import(self) -> None:
        src = (
            "from sqlite3 import Error\n"
            "def w():\n"
            "    try:\n"
            "        pass\n"
            "    except (Error, OSError):\n"
            "        return 0\n"
        )
        assert _degrade_gate_violations(src) == [5]

    def test_detector_exempts_close_pass_handlers(self) -> None:
        src = (
            "import sqlite3\n"
            "def w(c):\n"
            "    try:\n"
            "        c.close()\n"
            "    except sqlite3.Error:\n"
            "        pass\n"
        )
        assert _degrade_gate_violations(src) == []


# ---------------------------------------------------------------------------
# Startup / write sites under a live remote store
# ---------------------------------------------------------------------------


class TestStartupUnderRemote:
    def test_wire_transports_sqlite_branch_does_not_raise_and_writes_remotely(
        self, remote: HranaStub
    ) -> None:
        from little_loops.config.features import EventsConfig
        from little_loops.events import EventBus
        from little_loops.transport import wire_transports

        bus = EventBus()
        cfg = EventsConfig.from_dict({"transports": ["sqlite"]})
        wire_transports(bus, cfg)
        bus.emit({"event": "loop_start", "loop_name": "demo", "ts": "2026-09-29T00:00:00Z"})
        assert _count(remote, "loop_events") >= 1

    def test_default_sqlite_transport_reaches_the_remote_store(self, remote: HranaStub) -> None:
        transport = SQLiteTransport()
        transport.send({"event": "loop_start", "loop_name": "demo", "ts": "2026-09-29T00:00:00Z"})
        assert _count(remote, "loop_events") == 1
        assert not Path(".ll/history.db").exists()

    def test_transport_construction_sends_no_request(self, remote: HranaStub) -> None:
        before = len(remote.requests)
        SQLiteTransport()
        assert len(remote.requests) == before

    def test_dead_endpoint_transport_is_silent_and_traceback_free(
        self, remote: HranaStub, caplog: pytest.LogCaptureFixture
    ) -> None:
        remote.stop()
        with caplog.at_level(logging.DEBUG):
            transport = SQLiteTransport()
            for _ in range(3):
                transport.send({"event": "loop_start", "loop_name": "demo"})
        assert all(r.exc_info is None for r in caplog.records)
        assert not any(TOKEN in r.getMessage() for r in caplog.records)
        assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) <= 1

    def test_local_provider_twin_is_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ll").mkdir()
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        db_mod.clear_backend_config_cache()
        transport = SQLiteTransport()
        assert transport._path == db_mod.resolve_history_db()

    def test_local_default_resolves_identically_from_a_subdirectory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "pkg" / "deep"
        sub.mkdir(parents=True)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        db_mod.clear_backend_config_cache()
        monkeypatch.chdir(tmp_path)
        from_root = db_mod.resolve_history_db()
        monkeypatch.chdir(sub)
        assert db_mod.resolve_history_db() == from_root
        assert db_mod.resolve_history_store(DEFAULT_DB_PATH) == from_root


class TestSetStatusUnderRemote:
    def _issue(self, tmp_path: Path) -> Path:
        d = tmp_path / ".issues" / "bugs"
        d.mkdir(parents=True)
        path = d / "P3-BUG-901-example.md"
        path.write_text(
            "---\nid: BUG-901\ntype: BUG\nstatus: open\npriority: P3\n---\n\n# BUG-901\n"
        )
        return path

    def test_status_file_changes_and_history_rows_reach_the_remote_store(
        self, remote: HranaStub, tmp_path: Path
    ) -> None:
        from little_loops.cli.issues.set_status import apply_status_transition
        from little_loops.config import BRConfig

        path = self._issue(tmp_path)
        apply_status_transition(BRConfig(tmp_path), path, "BUG-901", "in_progress")
        assert "status: in_progress" in path.read_text()
        assert _count(remote, "issue_events") == 1
        assert _count(remote, "issue_snapshots") == 1

    def test_dead_endpoint_still_changes_the_status_file(
        self, remote: HranaStub, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        from little_loops.cli.issues.set_status import apply_status_transition
        from little_loops.config import BRConfig

        path = self._issue(tmp_path)
        remote.stop()
        with caplog.at_level(logging.DEBUG):
            apply_status_transition(BRConfig(tmp_path), path, "BUG-901", "in_progress")
        assert "status: in_progress" in path.read_text()
        assert all(r.exc_info is None for r in caplog.records)


# ---------------------------------------------------------------------------
# Writer-level fail-soft against a dead endpoint
# ---------------------------------------------------------------------------

_DEGRADE_WRITERS: list[tuple[str, dict[str, Any], Any]] = [
    (
        "record_session_lifecycle_event",
        {"session_id": "s1", "event": "worktree_create"},
        False,
    ),
    (
        "record_context_pressure_event",
        {"session_id": "s1", "used_pct": 90.0, "used_tokens_est": 1},
        False,
    ),
    (
        "write_advisor_consult",
        {
            "session_id": "s1",
            "task_key": "t",
            "signal": "x",
            "advisor_host": "h",
            "advisor_model": "m",
            "main_model": "mm",
            "outcome": "ok",
        },
        False,
    ),
    (
        "write_research_triage",
        {
            "issue_id": "BUG-1",
            "refined_at": None,
            "session_id": None,
            "axes": [("locator", True, "stale", "e")],
        },
        False,
    ),
    (
        "write_credential_scope",
        {"run_id": "r", "state": "s", "scopes": frozenset({"x"}), "var_names": ["V"]},
        False,
    ),
    (
        "record_subagent_run_start",
        {"parent_session_id": None, "agent_id": "a1", "agent_type": "t"},
        False,
    ),
    (
        "record_subagent_run_stop",
        {"parent_session_id": None, "agent_id": "a1", "status": "done"},
        False,
    ),
]


class TestDegradeWritersAgainstDeadEndpoint:
    @pytest.mark.parametrize(("name", "kwargs", "expected"), _DEGRADE_WRITERS)
    def test_returns_failure_value_without_raising(
        self,
        remote: HranaStub,
        caplog: pytest.LogCaptureFixture,
        name: str,
        kwargs: dict[str, Any],
        expected: Any,
    ) -> None:
        remote.stop()
        writer = getattr(writers_mod, name)
        with caplog.at_level(logging.DEBUG):
            assert writer(DEFAULT_DB_PATH, **kwargs) == expected
        assert all(r.exc_info is None for r in caplog.records)
        assert not any(TOKEN in r.getMessage() for r in caplog.records)

    def test_reconcile_stale_subagent_runs_returns_zero(
        self, remote: HranaStub, caplog: pytest.LogCaptureFixture
    ) -> None:
        remote.stop()
        with caplog.at_level(logging.DEBUG):
            assert (
                writers_mod.reconcile_stale_subagent_runs(DEFAULT_DB_PATH, current_session_id=None)
                == 0
            )
        assert all(r.exc_info is None for r in caplog.records)


# ---------------------------------------------------------------------------
# Prepatch readers, continuity
# ---------------------------------------------------------------------------


class TestPrepatchReadersUnderRemote:
    def _stamp(self, issue_id: str, sha: str) -> None:
        from little_loops.session_store import record_orchestration_run

        record_orchestration_run(
            DEFAULT_DB_PATH,
            run_id="run-1",
            driver="ll-parallel",
            issue_id=issue_id,
            status="running",
            base_sha=sha,
            base_dirty=False,
        )

    def test_reads_the_stamped_sha_from_the_remote_store(self, remote: HranaStub) -> None:
        from little_loops.history_reader import read_base_dirty, read_base_sha

        self._stamp("BUG-5", "cafebabe")
        assert read_base_sha("BUG-5") == "cafebabe"
        assert read_base_dirty("BUG-5") is False

    def test_refused_connection_returns_none_without_a_traceback(
        self, remote: HranaStub, caplog: pytest.LogCaptureFixture
    ) -> None:
        from little_loops.history_reader import read_base_dirty, read_base_sha

        remote.stop()
        with caplog.at_level(logging.DEBUG):
            assert read_base_sha("BUG-5") is None
            assert read_base_dirty("BUG-5") is None
        assert all(r.exc_info is None for r in caplog.records)

    def test_mid_query_failure_returns_none(
        self, remote: HranaStub, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The connection opens (schema/check_access succeed) but the query itself fails."""
        from little_loops.history_reader import _base as base_mod
        from little_loops.history_reader import read_base_dirty, read_base_sha
        from little_loops.session_store.backend import HistoryUnavailable

        real = base_mod._connect_readonly

        class _Boom:
            def __init__(self, conn: Any) -> None:
                self._conn = conn
                self.row_factory = None

            def execute(self, *a: Any, **k: Any) -> Any:
                raise HistoryUnavailable("stub: query failed")

            def close(self) -> None:
                self._conn.close()

        def _open(db_path: Path) -> Any:
            conn = real(db_path)
            return _Boom(conn) if conn is not None else None

        monkeypatch.setattr("little_loops.history_reader.runs._connect_readonly", _open)
        with caplog.at_level(logging.DEBUG):
            assert read_base_sha("BUG-5") is None
            assert read_base_dirty("BUG-5") is None
        assert all(r.exc_info is None for r in caplog.records)


class TestContinuityUnderRemote:
    def test_summarize_completed_state_returns_none_on_a_remote_store(
        self, remote: HranaStub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import little_loops.fsm.continuity as cont

        folder = tmp_path / "sessions"
        folder.mkdir()
        (folder / "sess-1.jsonl").write_text("{}\n")
        monkeypatch.setattr(cont, "get_sessions_folder", lambda *_a, **_k: folder)
        before = len(remote.requests)
        assert summarize_completed_state("sess-1") is None
        assert len(remote.requests) == before


# ---------------------------------------------------------------------------
# research-triage
# ---------------------------------------------------------------------------


class TestResearchTriageUnderRemote:
    def test_write_reaches_the_remote_store_and_a_dead_endpoint_degrades(
        self, remote: HranaStub
    ) -> None:
        from little_loops.session_store import write_research_triage

        args = {"issue_id": "BUG-1", "refined_at": None, "session_id": None}
        axes = [("locator", True, "stale", "e")]
        assert write_research_triage(DEFAULT_DB_PATH, axes=axes, **args) is True
        assert _count(remote, "research_triage_events") >= 1
        remote.stop()
        assert write_research_triage(DEFAULT_DB_PATH, axes=axes, **args) is False
