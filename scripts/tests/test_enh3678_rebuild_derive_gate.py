"""ENH-3678: gate the auto-spawned history rebuild on REBUILD_DERIVE_VERSION."""

from __future__ import annotations

import json
import sqlite3
import textwrap
from pathlib import Path

import pytest

from little_loops.hooks.session_start import handle
from little_loops.hooks.types import LLHookEvent
from little_loops.session_store import (
    REBUILD_DERIVE_VERSION,
    SCHEMA_VERSION,
    RebuildState,
    ensure_db,
    lifecycle,
    rebuild,
    rebuild_needed,
)
from little_loops.session_store.backend import HistoryUnavailable, connect_readonly
from tests.rebuild_fingerprint import (
    SNAPSHOT_REL,
    compute_fingerprint,
    resolve_function_set,
    sources_at,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _set_meta(db: Path, **values: str | None) -> None:
    conn = sqlite3.connect(str(db))
    try:
        for key, value in values.items():
            conn.execute("DELETE FROM meta WHERE key = ?", (key,))
            conn.execute("INSERT INTO meta(key, value) VALUES(?, ?)", (key, value))
        conn.commit()
    finally:
        conn.close()


def _drop_meta(db: Path, key: str) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("DELETE FROM meta WHERE key = ?", (key,))
        conn.commit()
    finally:
        conn.close()


def _meta(db: Path, key: str) -> str | None:
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "history.db"
    ensure_db(path)
    return path


class TestRebuildNeeded:
    def test_returns_frozen_dataclass(self, db: Path) -> None:
        state = rebuild_needed(db)
        assert isinstance(state, RebuildState)
        with pytest.raises(AttributeError):
            state.status = "current"  # type: ignore[misc]

    def test_fresh_db_has_no_stamp(self, db: Path) -> None:
        assert rebuild_needed(db) == RebuildState("stale", "no_stamp")

    def test_db_missing_is_stale(self, tmp_path: Path) -> None:
        assert rebuild_needed(tmp_path / "nope.db") == RebuildState("stale", "db_missing")

    def test_missing_db_is_not_created(self, tmp_path: Path) -> None:
        path = tmp_path / "nope.db"
        rebuild_needed(path)
        assert not path.exists()

    def test_after_rebuild_is_current(self, db: Path) -> None:
        rebuild(db)
        assert rebuild_needed(db) == RebuildState("current", "derive_match")

    def test_schema_version_bump_alone_does_not_make_stale(
        self, db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rebuild(db)
        monkeypatch.setattr(lifecycle, "SCHEMA_VERSION", SCHEMA_VERSION + 1)
        assert rebuild_needed(db).status == "current"

    def test_derive_version_bump_makes_stale(
        self, db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rebuild(db)
        monkeypatch.setattr(lifecycle, "REBUILD_DERIVE_VERSION", "bumped")
        assert rebuild_needed(db) == RebuildState("stale", "derive_mismatch")

    def test_stamp_behind_current_is_stale(self, db: Path) -> None:
        _set_meta(db, rebuild_derive_version="older-tag")
        assert rebuild_needed(db) == RebuildState("stale", "derive_mismatch")

    @pytest.mark.parametrize("last", ["58", "59", "60"])
    def test_unmarked_legacy_store_at_or_above_floor_is_current(
        self, db: Path, last: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Only while the current derive version still equals the frozen legacy one;
        # BUG-3761's bump moved it, so the frozen-baseline path is exercised by patching.
        monkeypatch.setattr(
            lifecycle, "REBUILD_DERIVE_VERSION", lifecycle._FROZEN_LEGACY_DERIVE_VERSION
        )
        _set_meta(db, last_rebuild_version=last)
        assert rebuild_needed(db) == RebuildState("current", "legacy_floor")
        assert _meta(db, "rebuild_derive_version") is None  # no hook-side write

    @pytest.mark.parametrize("last", ["58", "59", "60"])
    def test_unmarked_legacy_store_is_stale_after_derivation_bump(
        self, db: Path, last: str
    ) -> None:
        assert REBUILD_DERIVE_VERSION != lifecycle._FROZEN_LEGACY_DERIVE_VERSION
        _set_meta(db, last_rebuild_version=last)
        assert rebuild_needed(db) == RebuildState("stale", "derive_mismatch")

    @pytest.mark.parametrize("last", ["57", "0"])
    def test_unmarked_store_below_floor_rebuilds(self, db: Path, last: str) -> None:
        _set_meta(db, last_rebuild_version=last)
        assert rebuild_needed(db) == RebuildState("stale", "legacy_below_floor")

    def test_null_and_absent_last_rebuild_version_are_identical(self, db: Path) -> None:
        _set_meta(db, last_rebuild_version=None)
        null_state = rebuild_needed(db)
        _drop_meta(db, "last_rebuild_version")
        assert rebuild_needed(db) == null_state == RebuildState("stale", "no_stamp")

    def test_null_stamp_is_treated_as_absent(
        self, db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            lifecycle, "REBUILD_DERIVE_VERSION", lifecycle._FROZEN_LEGACY_DERIVE_VERSION
        )
        _set_meta(db, rebuild_derive_version=None, last_rebuild_version="58")
        assert rebuild_needed(db) == RebuildState("current", "legacy_floor")

    def test_non_integer_last_rebuild_version_is_stale_not_unknown(self, db: Path) -> None:
        _set_meta(db, last_rebuild_version="not-a-number")
        assert rebuild_needed(db) == RebuildState("stale", "legacy_below_floor")

    def test_future_bump_makes_unmarked_legacy_store_stale(
        self, db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_meta(db, last_rebuild_version="58")
        monkeypatch.setattr(lifecycle, "REBUILD_DERIVE_VERSION", "enh9999-v2")
        assert rebuild_needed(db) == RebuildState("stale", "derive_mismatch")

    def test_unreadable_store_is_unknown(self, tmp_path: Path) -> None:
        path = tmp_path / "garbage.db"
        path.write_bytes(b"this is not a sqlite database" * 100)
        assert rebuild_needed(path) == RebuildState("unknown", "read_error")

    def test_store_without_meta_table_is_unknown(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.db"
        sqlite3.connect(str(path)).close()
        assert rebuild_needed(path) == RebuildState("unknown", "read_error")

    def test_locked_store_maps_to_unknown_within_short_timeout(self, db: Path) -> None:
        import time

        _set_meta(db, last_rebuild_version="58")
        holder = sqlite3.connect(str(db), isolation_level=None)
        try:
            holder.execute("PRAGMA journal_mode=DELETE")
            holder.execute("BEGIN EXCLUSIVE")
            start = time.monotonic()
            state = rebuild_needed(db)
            elapsed = time.monotonic() - start
        finally:
            holder.execute("ROLLBACK")
            holder.close()
        assert state == RebuildState("unknown", "read_error")
        assert elapsed < 3.0

    def test_remote_target_is_unknown(self, db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from little_loops.session_store.targets import RemoteTarget

        class _Remote(RemoteTarget):
            def __init__(self) -> None:  # noqa: D107
                pass

        monkeypatch.setattr(lifecycle, "resolve_history_target", lambda _db: _Remote())
        assert rebuild_needed(db) == RebuildState("unknown", "remote")

    def test_read_leaves_store_byte_identical(self, db: Path) -> None:
        rebuild(db)
        before = db.read_bytes()
        rebuild_needed(db)
        assert db.read_bytes() == before


class TestRebuildStamp:
    def test_rebuild_stamps_derive_version_beside_last_rebuild_version(self, db: Path) -> None:
        rebuild(db)
        assert _meta(db, "rebuild_derive_version") == REBUILD_DERIVE_VERSION
        assert int(_meta(db, "last_rebuild_version") or 0) == SCHEMA_VERSION

    def test_key_is_unseeded_and_outside_usage_namespace(self, db: Path) -> None:
        assert _meta(db, "rebuild_derive_version") is None
        assert not "rebuild_derive_version".startswith("usage_derive_")

    def test_failed_rebuild_leaves_stamp_unwritten(
        self, db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*_a, **_k):
            raise RuntimeError("boom")

        monkeypatch.setattr(lifecycle, "_backfill_sessions", _boom)
        with pytest.raises(RuntimeError):
            rebuild(db)
        assert _meta(db, "rebuild_derive_version") is None
        assert rebuild_needed(db).status == "stale"


class TestConnectReadonlyTimeout:
    def test_default_timeout_unchanged_and_override_accepted(self, db: Path) -> None:
        conn = connect_readonly(db)
        conn.close()
        conn = connect_readonly(db, timeout=0.25)
        conn.close()

    def test_missing_file_still_raises_unavailable(self, tmp_path: Path) -> None:
        with pytest.raises(HistoryUnavailable):
            connect_readonly(tmp_path / "nope.db", timeout=0.1)


def _event() -> LLHookEvent:
    return LLHookEvent(host="claude-code", intent="session_start", payload={})


class TestSessionStartGate:
    def _setup(self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[list[list], Path]:
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))
        calls: list[list] = []

        class _FakePopen:
            def __init__(self_inner, args, **kw):  # noqa: N805
                calls.append(list(args))

        monkeypatch.setattr("little_loops.hooks.session_start.subprocess.Popen", _FakePopen)
        import little_loops.user_messages as um

        monkeypatch.setattr(um, "get_project_folder", lambda *a, **kw: in_tmp)
        monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)
        return calls, in_tmp / ".ll" / "history.db"

    @pytest.fixture
    def in_tmp(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        return tmp_path

    def test_stale_adds_rebuild(self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        calls, _ = self._setup(in_tmp, monkeypatch)
        handle(_event())
        assert len(calls) == 1 and "--auto-rebuild" in calls[0]
        assert "--rebuild" not in calls[0]

    def test_schema_bump_without_derive_bump_does_not_rebuild(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rebuild(in_tmp / ".ll" / "history.db")
        calls, _ = self._setup(in_tmp, monkeypatch)
        monkeypatch.setattr(lifecycle, "SCHEMA_VERSION", SCHEMA_VERSION + 5)
        handle(_event())
        assert len(calls) == 1 and "--rebuild" not in calls[0]

    def test_derive_bump_adds_rebuild(self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rebuild(in_tmp / ".ll" / "history.db")
        calls, _ = self._setup(in_tmp, monkeypatch)
        monkeypatch.setattr(lifecycle, "REBUILD_DERIVE_VERSION", "bumped")
        handle(_event())
        assert "--auto-rebuild" in calls[0]

    def test_unknown_spawns_incremental_worker_without_rebuild(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls, _ = self._setup(in_tmp, monkeypatch)
        monkeypatch.setattr(
            "little_loops.session_store.lifecycle.rebuild_needed",
            lambda _db: RebuildState("unknown", "read_error"),
        )
        handle(_event())
        assert len(calls) == 1
        assert "backfill_worker" in " ".join(calls[0])
        assert "--rebuild" not in calls[0]

    def test_exception_in_rebuild_needed_does_not_block_popen(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls, _ = self._setup(in_tmp, monkeypatch)

        def _boom(_db):
            raise RuntimeError("bug in rebuild_needed")

        monkeypatch.setattr("little_loops.session_store.lifecycle.rebuild_needed", _boom)
        handle(_event())
        assert len(calls) == 1
        assert "--rebuild" not in calls[0] and "--auto-rebuild" not in calls[0]

    # -- ENH-3698: size gate ------------------------------------------------

    @staticmethod
    def _over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(lifecycle, "REBUILD_AUTO_MAX_BYTES", 1)

    def test_over_limit_spawns_ingestion_without_replay_flag(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls, _ = self._setup(in_tmp, monkeypatch)
        self._over_limit(monkeypatch)
        result = handle(_event())
        assert len(calls) == 1 and "backfill_worker" in " ".join(calls[0])
        assert "--rebuild" not in calls[0] and "--auto-rebuild" not in calls[0]
        assert "History rebuild deferred" in (result.feedback or "")
        assert "History rebuild deferred" not in (result.stdout or "")

    def test_pending_notice_wording_and_compaction_from_raw_config(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls, _ = self._setup(in_tmp, monkeypatch)
        self._over_limit(monkeypatch)
        # Raw project JSON has compaction off; only the local override turns it on, and the
        # manual command never merges .ll/ll.local.md, so the notice must say "disabled".
        (in_tmp / ".ll" / "ll.local.md").write_text(
            "---\nhistory:\n  compaction:\n    enabled: true\n---\n"
        )
        text = handle(_event()).feedback or ""
        assert "tables may be incomplete" in text and "ll-session rebuild" in text
        assert "history.compaction is disabled" in text
        assert "retention" not in text

    def test_pending_notice_names_enabled_compaction(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._setup(in_tmp, monkeypatch)
        (in_tmp / ".ll" / "ll-config.json").write_text(
            json.dumps({"history": {"compaction": {"enabled": True}}})
        )
        self._over_limit(monkeypatch)
        text = handle(_event()).feedback or ""
        assert "LLM summarization inside the same transaction" in text

    def test_derive_mismatch_notice_says_mixed(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rebuild(in_tmp / ".ll" / "history.db")
        self._setup(in_tmp, monkeypatch)
        monkeypatch.setattr(lifecycle, "REBUILD_DERIVE_VERSION", "bumped")
        self._over_limit(monkeypatch)
        assert "mixed" in (handle(_event()).feedback or "")

    def test_pending_notice_survives_popen_failure(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._setup(in_tmp, monkeypatch)
        self._over_limit(monkeypatch)

        def _boom(*_a, **_kw):  # type: ignore[no-untyped-def]
            raise OSError("spawn failed")

        monkeypatch.setattr("little_loops.hooks.session_start.subprocess.Popen", _boom)
        assert "History rebuild deferred" in (handle(_event()).feedback or "")

    def test_no_notice_when_small_current_or_unknown(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._setup(in_tmp, monkeypatch)
        assert "deferred" not in (handle(_event()).feedback or "")
        monkeypatch.setattr(
            lifecycle, "rebuild_needed", lambda _t: RebuildState("unknown", "read_error")
        )
        self._over_limit(monkeypatch)
        assert "deferred" not in (handle(_event()).feedback or "")

    def test_unknown_size_adds_no_flag_and_no_notice(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls, _ = self._setup(in_tmp, monkeypatch)
        monkeypatch.setattr(lifecycle, "_store_bytes", lambda _p: None)
        result = handle(_event())
        assert len(calls) == 1
        assert "--rebuild" not in calls[0] and "--auto-rebuild" not in calls[0]
        assert "deferred" not in (result.feedback or "")

    def test_non_interactive_and_no_source_suppress_notice(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls, _ = self._setup(in_tmp, monkeypatch)
        self._over_limit(monkeypatch)
        monkeypatch.setenv("LL_NON_INTERACTIVE", "1")
        assert "deferred" not in (handle(_event()).feedback or "")
        assert calls == []
        monkeypatch.delenv("LL_NON_INTERACTIVE")
        import little_loops.user_messages as um

        monkeypatch.setattr(um, "get_project_folder", lambda *a, **kw: None)
        assert "deferred" not in (handle(_event()).feedback or "")
        assert calls == []

    def test_remote_store_gets_neither_flag_nor_notice(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls, _ = self._setup(in_tmp, monkeypatch)
        self._over_limit(monkeypatch)
        from little_loops.session_store.targets import BackendConfig, RemoteTarget

        remote = RemoteTarget(BackendConfig(provider="libsql", url="https://h.example"))
        monkeypatch.setattr(
            "little_loops.session_store.db.resolve_history_store", lambda *a, **kw: remote
        )
        result = handle(_event())
        assert all("--rebuild" not in c and "--auto-rebuild" not in c for c in calls)
        assert "deferred" not in (result.feedback or "")

    def test_hook_writes_no_stamp(self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _calls, db = self._setup(in_tmp, monkeypatch)
        handle(_event())
        assert _meta(db, "rebuild_derive_version") is None


class TestDeriveFingerprint:
    """ENH-3678 bump-rule guard: a derivation change needs a REBUILD_DERIVE_VERSION bump.

    ``rebuild_fingerprint.json`` pins a digest of what a non-usage ``rebuild()``
    derives: ``_REBUILD_TABLES`` minus ``usage_events``, ``_REBUILD_SEARCH_KINDS`` minus
    ``"usage"``, the DDL of the non-usage rebuild tables, and the source of every
    module-level function in ``writers.py``/``lifecycle.py`` reachable from ``rebuild()``
    (edges into ``_backfill_usage_events``/``_set_usage_derive_checkpoint`` are pruned;
    ``_call_llm_for_summary`` is listed but not hashed; usage/remote-guard/stamp
    statements are blanked from ``rebuild``'s body). ``backfill()``-only functions are
    out of the set: ``rebuild()`` cannot apply them.

    Regenerate (from the repo root) after a deliberate change, in the same commit that
    bumps ``REBUILD_DERIVE_VERSION``::

        python -c "import sys; sys.path.insert(0, 'scripts'); from pathlib import Path; \\
        from tests.rebuild_fingerprint import regenerate; regenerate(Path('.'))"

    ``frozen_legacy_digest`` is never regenerated. A derivation change needs a bump; the
    SessionStart size gate defers the resulting replay on a large store.

    Expected noise: about one trip a week over recent history, roughly half of them false
    positives (e.g. a ruff reflow adding a trailing comma). Regenerating by reflex defeats
    the guard; it is a discipline aid, not a guarantee.

    Known residual gap: ``rebuild`` replays already-normalized ``raw_events`` and cannot
    apply parser changes in ``sessions.py``/``gemini.py``/``omp.py``/``CodexNormalizer``
    (correctly outside the set). The one replay-time gap is the function-local
    ``from little_loops.session_store.qwen import is_raw_qwen_record,
    normalize_qwen_record`` in the replay shim: edits to those two functions are not hashed.
    """

    @staticmethod
    def _snapshot() -> dict:
        return json.loads((REPO_ROOT / SNAPSHOT_REL).read_text(encoding="utf-8"))

    def test_resolved_function_set_matches_snapshot(self) -> None:
        sources, _manifest = sources_at(REPO_ROOT, None)
        resolved = [f"{m}.{n}" for m, n in resolve_function_set(sources)]
        assert len(resolved) == 28
        assert resolved == self._snapshot()["function_set"], (
            "the set of functions reachable from rebuild() changed; regenerate "
            "rebuild_fingerprint.json (see this class's docstring) and consider a bump"
        )

    def test_digest_matches_snapshot(self) -> None:
        snap = self._snapshot()
        current = compute_fingerprint(*sources_at(REPO_ROOT, None))["digest"]
        if current == snap["current_digest"]:
            return
        # Two-assert convention (TestAllowlistVersionLockstep): which half is stale?
        assert REBUILD_DERIVE_VERSION != lifecycle._FROZEN_LEGACY_DERIVE_VERSION, (
            "rebuild() derivation changed but REBUILD_DERIVE_VERSION was not bumped. "
            "Bump it in the same change that regenerates rebuild_fingerprint.json (see this "
            "class's docstring); the size gate defers the replay on a large store."
        )
        pytest.fail(
            "REBUILD_DERIVE_VERSION was bumped but rebuild_fingerprint.json is stale; "
            "regenerate it (see TestDeriveFingerprint's docstring)."
        )

    def test_frozen_legacy_digest_is_never_regenerated(self) -> None:
        sources, manifest = sources_at(REPO_ROOT, "9cb4467d6")
        legacy = compute_fingerprint(sources, manifest)["digest"]
        assert self._snapshot()["frozen_legacy_digest"] == legacy


class TestNormalizerStability:
    """The hashed representation must ignore comments, docstrings and whitespace."""

    _BASE = textwrap.dedent(
        '''
        def rebuild():
            """doc"""
            x = 1  # trailing
            return x
        def _backfill_sessions(): return 0
        '''
    )

    def _digest(
        self, lifecycle_src: str, predicates: str = "_REBUILD_TABLE_PREDICATES = {}\n"
    ) -> str:
        sources = {"lifecycle": lifecycle_src, "writers": "def _noop():\n    return 1\n"}
        manifest: dict = {"objects": {}}
        # constants are required by compute_fingerprint
        sources["lifecycle"] += (
            '\n_REBUILD_TABLES = ("a",)\n_REBUILD_SEARCH_KINDS = ("tool",)\n' + predicates
        )
        return compute_fingerprint(sources, manifest)["digest"]

    def test_stable_under_comment_docstring_whitespace_edits(self) -> None:
        edited = textwrap.dedent(
            '''
            def rebuild():
                """a much longer
                docstring"""
                # a new comment
                x   =   1
                return   x
            def _backfill_sessions(): return 0
            '''
        )
        assert self._digest(self._BASE) == self._digest(edited)

    def test_changes_on_code_edit(self) -> None:
        edited = self._BASE.replace("x = 1", "x = 2")
        assert self._digest(self._BASE) != self._digest(edited)

    def test_non_usage_predicate_changes_digest(self) -> None:
        """BUG-3715: a deletion-predicate change is a selection change."""
        usage = "_REBUILD_TABLE_PREDICATES = {'usage_events': \"channel IS NOT 'live'\"}\n"
        retention = "'summary_nodes': \"kind IS NOT 'retention'\""
        added = f"_REBUILD_TABLE_PREDICATES = {{'usage_events': \"channel IS NOT 'live'\", {retention}}}\n"
        changed = added.replace("'retention'", "'other'")
        base = self._digest(self._BASE, usage)
        assert self._digest(self._BASE, added) != base
        assert self._digest(self._BASE, changed) != self._digest(self._BASE, added)

    def test_usage_only_predicate_does_not_change_digest(self) -> None:
        empty = self._digest(self._BASE)
        usage = "_REBUILD_TABLE_PREDICATES = {'usage_events': \"channel IS NOT 'live'\"}\n"
        other = "_REBUILD_TABLE_PREDICATES = {'usage_events': 'channel = 1'}\n"
        assert self._digest(self._BASE, usage) == empty
        assert self._digest(self._BASE, other) == empty

    def test_annotated_predicate_literal_is_supported(self) -> None:
        plain = "_REBUILD_TABLE_PREDICATES = {'summary_nodes': 'kind IS NOT 1'}\n"
        annotated = (
            "_REBUILD_TABLE_PREDICATES: dict[str, str] = {'summary_nodes': 'kind IS NOT 1'}\n"
        )
        assert self._digest(self._BASE, plain) == self._digest(self._BASE, annotated)

    def test_missing_predicate_constant_fails_clearly(self) -> None:
        with pytest.raises(KeyError, match="_REBUILD_TABLE_PREDICATES"):
            self._digest(self._BASE, "")

    def test_walk_prunes_usage_edges(self) -> None:
        src = textwrap.dedent(
            """
            def rebuild():
                _backfill_usage_events()
                _helper()
            def _backfill_usage_events():
                _usage_only()
            def _usage_only(): return 1
            def _helper(): return 2
            _REBUILD_TABLES = ("a",)
            _REBUILD_SEARCH_KINDS = ("tool",)
            _REBUILD_TABLE_PREDICATES = {}
            """
        )
        names = [n for _m, n in resolve_function_set({"lifecycle": src, "writers": ""})]
        assert names == ["_helper", "rebuild"]


class TestFrozenLegacyPins:
    def test_frozen_legacy_derive_version_literal(self) -> None:
        """Permanent: bumping both constants would mark every legacy store current."""
        assert lifecycle._FROZEN_LEGACY_DERIVE_VERSION == "enh3678-v1"

    def test_package_exports(self) -> None:
        import little_loops.session_store as pkg

        for name in ("REBUILD_DERIVE_VERSION", "RebuildState", "rebuild_needed"):
            assert name in pkg.__all__ and hasattr(pkg, name)
