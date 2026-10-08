"""``ll-next`` recommendation events, explicit acceptance and feedback (FEAT-3711).

Real migrated stores throughout; the CLI is driven through ``main_next`` exactly like
``test_feat3561_phase_e_cli``. Reader request contracts live in
``test_feat3721_history_snapshot.py``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import little_loops.next_arena.recording as recording
import little_loops.next_arena.state as state_module
from little_loops.cli import main_next
from little_loops.next_arena import history as hist
from little_loops.next_arena import render
from little_loops.next_arena.actions import ACTION_VARIANTS
from little_loops.next_arena.recording import (
    canonical_rec_id,
    lookup_feedback,
    project_key_for,
    record_accepted,
    record_shown,
)
from little_loops.session_store import (
    _KINDLESS_TABLES,
    _MIGRATIONS,
    _REBUILD_SEARCH_KINDS,
    _REBUILD_TABLES,
    RECOMMENDATION_EVENTS_MIN_VERSION,
    SCHEMA_VERSION,
    lifecycle,
    rebuild,
)
from little_loops.session_store.backend import BackendConfig, LocalTarget, RemoteTarget
from tests.next_arena_candidates_support import ready_issue
from tests.next_arena_support import AS_OF, make_project, schema_errors, write_issue
from tests.recommendation_support import (
    LATER,
    NOW,
    event_row,
    fetch_rows,
    insert_row,
    loop_offer,
    make_real_store,
    replace_table,
    scan_offer,
    slash_offer,
    sprint_offer,
)

Run = Callable[..., tuple[int, str, str]]


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin ``as_of`` and drop ambient history/analytics overrides."""
    monkeypatch.setattr(state_module, "_normalize_as_of", lambda _as_of: AS_OF)
    monkeypatch.delenv("LL_HISTORY_DB", raising=False)
    monkeypatch.delenv("LL_ANALYTICS_CAPTURE", raising=False)


@pytest.fixture
def proj(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    make_project(root)
    write_issue(root, "features/P2-FEAT-001-impl.md", text=ready_issue())
    write_issue(root, "bugs/P1-BUG-002-fix.md", text=ready_issue())
    monkeypatch.chdir(root)
    return root.resolve()


@pytest.fixture
def db(proj: Path) -> Path:
    return make_real_store(proj / ".ll" / "history.db")


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Run:
    def _run(*argv: str) -> tuple[int, str, str]:
        with patch("sys.argv", ["ll-next", *argv]):
            code = main_next()
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


def target_for(db: Path) -> LocalTarget:
    return LocalTarget(db)


def shown(db: Path, root: Path, offers: list[Any] | None = None, **kw: Any) -> Any:
    return record_shown(
        offers if offers is not None else [slash_offer()],
        target=target_for(db),
        project_key=project_key_for(root),
        invocation_id=kw.pop("invocation_id", str(uuid.uuid4())),
        as_of=kw.pop("as_of", NOW),
        requested_top=kw.pop("requested_top", None),
        requested_types=kw.pop("requested_types", ()),
        now=kw.pop("now", lambda: NOW),
    )


def accept(db: Path, root: Path, rec_id: str, **kw: Any) -> Any:
    return record_accepted(
        rec_id,
        target=target_for(db),
        project_key=project_key_for(root),
        invocation_id=kw.pop("invocation_id", str(uuid.uuid4())),
        now=kw.pop("now", lambda: LATER),
    )


def feedback(db: Path, root: Path, rec_id: str, now: Callable[[], datetime] = lambda: LATER) -> Any:
    snap = hist.read_history_snapshot(
        target_for(db),
        as_of=NOW,
        requests=[hist.RecommendationLookup(project_key_for(root), rec_id)],
        now=now,
    )
    return lookup_feedback(snap, rec_id)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ migration / rebuild


class TestMigration:
    def test_write_floor_is_derived_from_the_owning_migration(self) -> None:
        owning = next(
            i + 1 for i, s in enumerate(_MIGRATIONS) if "CREATE TABLE recommendation_events" in s
        )
        assert RECOMMENDATION_EVENTS_MIN_VERSION == owning <= SCHEMA_VERSION

    def test_classification_keeps_the_table_out_of_rebuild_and_search(self) -> None:
        assert "recommendation_events" in _KINDLESS_TABLES
        assert "recommendation_events" not in _REBUILD_TABLES
        assert not any("recommendation" in kind for kind in _REBUILD_SEARCH_KINDS)

    @pytest.mark.parametrize(
        "bad",
        [
            {"rec_id": None},
            {"kind": "ignored"},
            {"rank": 0},
            {"action_spec": None},
            {"requested_types": None},
            {"project_key": None},
            {"invocation_id": None},
            {"as_of": None},
        ],
    )
    def test_not_null_and_check_constraints_reject_bad_rows(
        self, db: Path, proj: Path, bad: dict[str, Any]
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            insert_row(db, event_row(proj, **bad))
        assert fetch_rows(db) == []

    def test_event_and_identity_uniqueness(self, db: Path, proj: Path) -> None:
        first = event_row(proj)
        insert_row(db, first)
        with pytest.raises(sqlite3.IntegrityError):
            insert_row(db, event_row(proj, event_id=first["event_id"]))
        with pytest.raises(sqlite3.IntegrityError):
            insert_row(db, event_row(proj, rec_id=first["rec_id"]))
        insert_row(db, event_row(proj, rec_id=first["rec_id"], kind="accepted_explicit"))

    def test_rows_survive_rebuild_and_derivation_version_is_unchanged(
        self, db: Path, proj: Path
    ) -> None:
        shown_row = event_row(proj)
        insert_row(db, shown_row)
        insert_row(db, event_row(proj, rec_id=shown_row["rec_id"], kind="accepted_explicit"))
        before = fetch_rows(db)
        version_before = lifecycle.REBUILD_DERIVE_VERSION
        rebuild(db)
        assert fetch_rows(db) == before
        assert lifecycle.REBUILD_DERIVE_VERSION == version_before == "bug3766-v1"


# ----------------------------------------------------------------------------- identity


class TestIdentity:
    def test_canonical_rec_id_normalizes_case_only(self) -> None:
        u = str(uuid.uuid4())
        assert canonical_rec_id(u.upper()) == u
        assert canonical_rec_id(u.title().upper()) == u
        for bad in (f"{{{u}}}", f"urn:uuid:{u}", u.replace("-", ""), u + " ", "", "abc"):
            with pytest.raises(ValueError):
                canonical_rec_id(bad)

    def test_project_key_is_stable_across_spellings_and_distinct_per_root(
        self, tmp_path: Path
    ) -> None:
        a = tmp_path / "a"
        a.mkdir()
        (tmp_path / "b").mkdir()
        assert project_key_for(a) == project_key_for(a / ".." / "a")
        assert project_key_for(a) != project_key_for(tmp_path / "b")
        assert len(project_key_for(a)) == 64


# ---------------------------------------------------------------------------- recording


class TestRecordShown:
    def test_batch_is_atomic_with_shared_invocation_and_ranked_rows(
        self, db: Path, proj: Path
    ) -> None:
        inv = str(uuid.uuid4())
        result = shown(
            db,
            proj,
            [slash_offer("FEAT-001"), loop_offer("daily"), slash_offer("BUG-002")],
            invocation_id=inv,
            requested_top=3,
            requested_types=("run-loop", "implement-issue"),
        )
        assert result.recording.status == "recorded" and result.recording.reason is None
        rows = fetch_rows(db)
        assert [r["rec_id"] for r in rows] == list(result.rec_ids)
        assert len(set(result.rec_ids)) == 3 and all(uuid.UUID(r) for r in result.rec_ids)
        assert [r["rank"] for r in rows] == [1, 2, 3]
        assert {r["invocation_id"] for r in rows} == {inv}
        assert {r["session_id"] for r in rows} == {None}
        assert {r["kind"] for r in rows} == {"shown"}
        assert {r["requested_top"] for r in rows} == {3}
        assert {r["requested_types"] for r in rows} == {'["run-loop", "implement-issue"]'}
        assert {r["ts"] for r in rows} == {"2026-10-08T09:30:00.000000Z"}
        assert {r["project_key"] for r in rows} == {project_key_for(proj)}

    def test_registered_variants_round_trip_losslessly(self, db: Path, proj: Path) -> None:
        offers = [slash_offer(), loop_offer(), sprint_offer(), scan_offer()]
        assert {o.action_spec.variant for o in offers} == set(ACTION_VARIANTS)
        shown(db, proj, offers)
        for offer, row in zip(offers, fetch_rows(db), strict=True):
            assert json.loads(row["action_spec"]) == recording.spec_to_dict(offer.action_spec)
            assert row["action_fingerprint"] == offer.action_fingerprint
            assert row["action_key"] == offer.action_key

    def test_sprint_and_scan_offers_survive_shown_accept_feedback_unchanged(
        self, db: Path, proj: Path
    ) -> None:
        # FEAT-3713: the stored offer, not today's definition/config, backs accept and feedback;
        # sprint members (terminal included) and the scan scope arrays round-trip losslessly.
        offers = [sprint_offer("alpha"), scan_offer()]
        result = shown(db, proj, offers)
        for offer, rec_id in zip(offers, result.rec_ids, strict=True):
            assert accept(db, proj, rec_id).status == "accepted"
            found = feedback(db, proj, rec_id)
            assert found.state == "accepted"
            stored = json.loads(found.offer.action_spec)
            assert stored == recording.spec_to_dict(offer.action_spec)
            document = render.build_feedback_document(rec_id, found)["offer"]
            assert document["display_command"] == render.render_action(offer.action_spec)
        sprint_doc = json.loads(feedback(db, proj, result.rec_ids[0]).offer.action_spec)
        assert sprint_doc["members"] == [
            {"issue_id": "FEAT-001", "status": "open"},
            {"issue_id": "BUG-002", "status": "done"},
        ]
        scan_doc = json.loads(feedback(db, proj, result.rec_ids[1]).offer.action_spec)
        assert scan_doc["focus_dirs"] == ["scripts", "src"]
        assert scan_doc["exclude_patterns"] == ["**/vendor/**"]

    def test_equal_fingerprints_get_distinct_ids(self, db: Path, proj: Path) -> None:
        first = shown(db, proj, [loop_offer("daily")])
        second = shown(db, proj, [loop_offer("daily")])
        assert first.rec_ids != second.rec_ids
        acc = accept(db, proj, first.rec_ids[0])
        assert acc.status == "accepted"
        assert feedback(db, proj, second.rec_ids[0]).state == "unknown"

    def test_empty_offers_probe_nothing(self, tmp_path: Path, proj: Path) -> None:
        missing = tmp_path / "nowhere" / "h.db"
        result = shown(missing, proj, [])
        assert (result.recording.status, result.recording.reason) == (
            "disabled",
            "nothing_to_record",
        )
        assert not missing.parent.exists()

    def test_missing_store_is_schema_not_ready_and_creates_nothing(
        self, tmp_path: Path, proj: Path
    ) -> None:
        missing = tmp_path / "newdir" / "h.db"
        result = shown(missing, proj)
        assert (result.recording.status, result.recording.reason) == (
            "unavailable",
            "schema_not_ready",
        )
        assert result.rec_ids == () and not missing.parent.exists()

    @pytest.mark.parametrize("variant", ["old_stamp", "no_table", "bad_index"])
    def test_unprepared_store_degrades_without_migrating(
        self, db: Path, proj: Path, variant: str
    ) -> None:
        conn = sqlite3.connect(db)
        if variant == "old_stamp":
            conn.execute("UPDATE meta SET value = '62' WHERE key = 'schema_version'")
        elif variant == "no_table":
            conn.execute("DROP TABLE recommendation_events")
        conn.commit()
        conn.close()
        if variant == "bad_index":
            replace_table(
                db,
                ddl_tail="",
                extra=("CREATE UNIQUE INDEX u ON recommendation_events(kind, rec_id)",),
            )
        before = digest(db)
        result = shown(db, proj)
        assert (result.recording.status, result.recording.reason) == (
            "unavailable",
            "schema_not_ready",
        )
        assert result.rec_ids == () and digest(db) == before

    def test_remote_target_is_unsupported_in_v1(self, proj: Path) -> None:
        remote = RemoteTarget(
            BackendConfig(provider="turso", url="https://x.invalid", project_id="p")
        )
        result = record_shown(
            [slash_offer()],
            target=remote,
            project_key=project_key_for(proj),
            invocation_id="i",
            as_of=NOW,
            requested_top=None,
            requested_types=(),
            now=lambda: NOW,
        )
        assert (result.recording.status, result.recording.reason) == (
            "unavailable",
            "remote_unsupported_v1",
        )
        assert accept_remote(proj, remote).reason == "remote_unsupported_v1"

    def test_integrity_conflict_rolls_the_whole_batch_back(
        self, db: Path, proj: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # every minted uuid is identical, so the second row collides on a UNIQUE column
        monkeypatch.setattr(recording.uuid, "uuid4", lambda: uuid.UUID(int=7))
        result = shown(db, proj, [slash_offer("FEAT-001"), slash_offer("BUG-002")])
        assert (result.recording.status, result.recording.reason) == ("unavailable", "write_failed")
        assert result.rec_ids == () and fetch_rows(db) == []

    def test_preflight_write_race_never_recreates_a_removed_store(
        self, db: Path, proj: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(recording, "_preflight_reason", lambda *_a, **_k: None)
        db.unlink()
        result = shown(db, proj)
        assert (result.recording.status, result.recording.reason) == (
            "unavailable",
            "schema_not_ready",
        )
        assert not db.exists()

    def test_preflight_write_race_table_dropped_before_write(
        self, db: Path, proj: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(recording, "_preflight_reason", lambda *_a, **_k: None)
        conn = sqlite3.connect(db)
        conn.execute("DROP TABLE recommendation_events")
        conn.commit()
        conn.close()
        result = shown(db, proj)
        assert result.recording.reason == "schema_not_ready" and result.rec_ids == ()

    def test_uses_the_no_ensure_opener_with_a_250ms_timeout_and_closes(
        self, db: Path, proj: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[Any, float]] = []
        closed: list[bool] = []
        real = recording.connect_existing_writable

        class Spy:
            def __init__(self, conn: sqlite3.Connection) -> None:
                self.conn = conn

            def __getattr__(self, name: str) -> Any:
                return getattr(self.conn, name)

            def close(self) -> None:
                closed.append(True)
                self.conn.close()

        def spy(target: Any, *, timeout: float) -> Any:
            calls.append((target, timeout))
            return Spy(real(target, timeout=timeout))

        monkeypatch.setattr(recording, "connect_existing_writable", spy)
        monkeypatch.setattr(
            "little_loops.session_store.schema.ensure_db",
            lambda *_a, **_k: pytest.fail("recording must never call ensure_db"),
        )
        assert shown(db, proj).recording.status == "recorded"
        assert calls == [(target_for(db), 0.25)] and closed == [True]

    @pytest.mark.parametrize("name", ["a#b", "a?b", "a%20b", "sp ace", "unié"])
    def test_special_character_paths_write_the_intended_file_only(
        self, tmp_path: Path, proj: Path, name: str
    ) -> None:
        intended = make_real_store(tmp_path / name / "h.db")
        decoy_dir = tmp_path / name.split("#")[0].split("?")[0].replace("%20", " ")
        decoy = make_real_store(tmp_path / "decoy" / "h.db") if not decoy_dir.exists() else None
        before = digest(decoy) if decoy else None
        assert shown(intended, proj).recording.status == "recorded"
        assert len(fetch_rows(intended)) == 1
        if decoy is not None:
            assert digest(decoy) == before
        missing = tmp_path / f"{name}-missing" / "h.db"
        assert shown(missing, proj).recording.status == "unavailable"
        assert not missing.parent.exists()


def accept_remote(proj: Path, remote: RemoteTarget) -> Any:
    return record_accepted(
        str(uuid.uuid4()),
        target=remote,
        project_key=project_key_for(proj),
        invocation_id="i",
        now=lambda: LATER,
    )


# ------------------------------------------------------------------------------- accept


class TestAccept:
    def test_accept_appends_one_copied_acknowledgement(self, db: Path, proj: Path) -> None:
        rec = shown(db, proj, [loop_offer()]).rec_ids[0]
        inv = str(uuid.uuid4())
        result = accept(db, proj, rec, invocation_id=inv)
        assert (result.status, result.reason) == ("accepted", None)
        assert result.accepted_at == "2026-10-08T09:31:00.123456Z"
        first, second = fetch_rows(db)
        assert (first["kind"], second["kind"]) == ("shown", "accepted_explicit")
        for column in recording._COPIED_COLUMNS:
            assert first[column] == second[column]
        assert second["invocation_id"] == inv and second["event_id"] != first["event_id"]
        assert second["session_id"] is None

    def test_replay_is_idempotent_and_returns_the_original_time(self, db: Path, proj: Path) -> None:
        rec = shown(db, proj).rec_ids[0]
        first = accept(db, proj, rec, now=lambda: LATER)
        replay = accept(db, proj, rec, now=lambda: datetime(2030, 1, 1, tzinfo=UTC))
        assert (first.status, replay.status) == ("accepted", "already_accepted")
        assert replay.accepted_at == first.accepted_at
        assert len(fetch_rows(db)) == 2

    def test_unknown_and_foreign_project_ids_are_unknown(
        self, db: Path, proj: Path, tmp_path: Path
    ) -> None:
        other = tmp_path / "other"
        other.mkdir()
        rec = shown(db, proj).rec_ids[0]
        assert accept(db, other, rec).status == "unknown"
        assert accept(db, proj, str(uuid.uuid4())).status == "unknown"
        assert [r["kind"] for r in fetch_rows(db)] == ["shown"]

    def test_concurrent_accepts_write_exactly_one_acknowledgement(
        self, db: Path, proj: Path
    ) -> None:
        rec = shown(db, proj).rec_ids[0]
        results: list[Any] = []
        barrier = threading.Barrier(4)

        def worker() -> None:
            barrier.wait()
            results.append(accept(db, proj, rec))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(r.status for r in results).count("accepted") == 1
        assert {r.status for r in results} <= {"accepted", "already_accepted"}
        assert len({r.accepted_at for r in results}) == 1
        assert len(fetch_rows(db)) == 2

    def test_unrelated_unique_conflict_raises_and_rolls_back(
        self, db: Path, proj: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rec = shown(db, proj).rec_ids[0]
        existing = fetch_rows(db)[0]["event_id"]
        # the acknowledgement's fresh event_id collides with the shown row's event_id
        monkeypatch.setattr(recording.uuid, "uuid4", lambda: uuid.UUID(existing))
        result = accept(db, proj, rec)
        assert (result.status, result.reason) == ("unavailable", "write_failed")
        assert [r["kind"] for r in fetch_rows(db)] == ["shown"]

    def test_binary_conflict_target_does_not_swallow_a_nocase_constraint(
        self, db: Path, proj: Path
    ) -> None:
        rec = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        replace_table(
            db,
            ddl_tail="UNIQUE (rec_id, kind)",
            rec="TEXT COLLATE NOCASE",
            kind="TEXT COLLATE NOCASE",
            pk="TEXT COLLATE NOCASE",
            extra=(
                "CREATE UNIQUE INDEX uq_bin ON recommendation_events"
                "(rec_id COLLATE BINARY, kind COLLATE BINARY)",
            ),
        )
        insert_row(db, event_row(proj, rec_id=rec))
        # differs only by case: BINARY-distinct, but NOCASE-conflicting with the new acknowledgement
        insert_row(db, event_row(proj, rec_id=rec.upper(), kind="accepted_explicit"))
        result = accept(db, proj, rec)
        assert (result.status, result.reason) == ("unavailable", "write_failed")
        assert len(fetch_rows(db)) == 2

    def test_nocase_declared_columns_stay_project_exact_and_idempotent(
        self, db: Path, proj: Path, tmp_path: Path
    ) -> None:
        replace_table(
            db,
            ddl_tail="UNIQUE (rec_id, kind)",
            rec="TEXT COLLATE NOCASE",
            kind="TEXT COLLATE NOCASE",
            pk="TEXT COLLATE NOCASE",
            extra=(
                "CREATE UNIQUE INDEX uq_bin ON recommendation_events"
                "(rec_id COLLATE BINARY, kind COLLATE BINARY)",
                "CREATE UNIQUE INDEX uq_nocase ON recommendation_events(event_id COLLATE NOCASE)",
            ),
        )
        row = event_row(proj)
        insert_row(db, row)
        mixed_case_project = project_key_for(proj).upper()
        assert hist.RecommendationLookup(mixed_case_project, row["rec_id"])  # distinct value
        assert accept(db, proj, row["rec_id"]).status == "accepted"
        assert accept(db, proj, row["rec_id"]).status == "already_accepted"
        assert accept(db, tmp_path, row["rec_id"]).status == "unknown"

    def test_unsupported_variant_is_unavailable_never_unknown_or_accepted(
        self, db: Path, proj: Path
    ) -> None:
        spec = json.dumps({"variant": "teleport", "target": "x"})
        row = event_row(proj, action_spec=spec)
        insert_row(db, row)
        result = accept(db, proj, row["rec_id"])
        assert (result.status, result.reason) == ("unavailable", "unsupported_action_spec")
        assert feedback(db, proj, row["rec_id"]).reason == "unsupported_action_spec"
        # only that identity is affected
        ok = shown(db, proj).rec_ids[0]
        assert accept(db, proj, ok).status == "accepted"

    def test_malformed_recognized_payload_is_a_storage_failure(self, db: Path, proj: Path) -> None:
        row = event_row(proj, action_spec=json.dumps({"variant": "slash", "command": 7}))
        insert_row(db, row)
        assert accept(db, proj, row["rec_id"]).reason == "malformed_offer"
        assert feedback(db, proj, row["rec_id"]).reason == "malformed_offer"
        broken = event_row(proj, action_spec="{not json")
        insert_row(db, broken)
        assert feedback(db, proj, broken["rec_id"]).reason == "malformed_offer"

    def test_changed_acknowledgement_payload_fails_accept_and_feedback(
        self, db: Path, proj: Path
    ) -> None:
        rec = shown(db, proj).rec_ids[0]
        assert accept(db, proj, rec).status == "accepted"
        conn = sqlite3.connect(db)
        conn.execute(
            "UPDATE recommendation_events SET action_fingerprint = 'sha256:' || hex(zeroblob(32)) "
            "WHERE kind = 'accepted_explicit'"
        )
        conn.commit()
        conn.close()
        assert accept(db, proj, rec).reason == "inconsistent_acknowledgement"
        assert feedback(db, proj, rec).reason == "inconsistent_acknowledgement"

    def test_acknowledgement_without_an_offer_is_inconsistent(self, db: Path, proj: Path) -> None:
        orphan = event_row(proj, kind="accepted_explicit")
        insert_row(db, orphan)
        assert accept(db, proj, orphan["rec_id"]).reason == "inconsistent_acknowledgement"
        assert feedback(db, proj, orphan["rec_id"]).reason == "inconsistent_acknowledgement"

    def test_unprepared_store_reports_schema_not_ready(self, tmp_path: Path, proj: Path) -> None:
        missing = tmp_path / "x" / "h.db"
        result = accept(missing, proj, str(uuid.uuid4()))
        assert (result.status, result.reason) == ("unavailable", "schema_not_ready")
        assert not missing.parent.exists()

    def test_uses_the_frozen_target_not_the_cwd(
        self, db: Path, proj: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rec = shown(db, proj).rec_ids[0]
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        assert accept(db, proj, rec).status == "accepted"
        assert list(elsewhere.iterdir()) == []


# ------------------------------------------------------------------------------ feedback


class TestFeedback:
    def test_states_and_timestamps(self, db: Path, proj: Path) -> None:
        rec = shown(db, proj, now=lambda: NOW).rec_ids[0]
        pending = feedback(db, proj, rec)
        assert (pending.found, pending.state, pending.accepted_at) == (True, "unknown", None)
        assert pending.offer is not None and pending.offer.as_of == "2026-10-08T09:30:00.000000Z"
        accept(db, proj, rec, now=lambda: LATER)
        done = feedback(db, proj, rec, now=lambda: LATER)
        assert (done.state, done.accepted_at) == ("accepted", "2026-10-08T09:31:00.123456Z")
        assert done.read_observed_at == LATER

    def test_absent_and_foreign_ids_produce_identical_documents(
        self, db: Path, proj: Path, tmp_path: Path
    ) -> None:
        other = tmp_path / "other"
        other.mkdir()
        foreign = shown(db, other).rec_ids[0]
        absent = str(uuid.uuid4())
        # same requested ID, same clock: swap which store row exists
        a = render.build_feedback_document(foreign, feedback(db, proj, foreign))
        b_db = make_real_store(tmp_path / "empty" / "h.db")
        b = render.build_feedback_document(foreign, feedback(b_db, proj, foreign))
        assert a == b
        assert (a["found"], a["state"], a["reason"]) == (False, None, "rec_id_not_found")
        assert render.build_feedback_document(absent, feedback(db, proj, absent))["found"] is False

    def test_an_accept_committed_after_as_of_is_visible(self, db: Path, proj: Path) -> None:
        rec = shown(db, proj).rec_ids[0]
        snap_as_of = datetime(2000, 1, 1, tzinfo=UTC)  # long before either write
        accept(db, proj, rec)
        snap = hist.read_history_snapshot(
            target_for(db),
            as_of=snap_as_of,
            requests=[hist.RecommendationLookup(project_key_for(proj), rec)],
            now=lambda: LATER,
        )
        result = lookup_feedback(snap, rec)
        assert result.state == "accepted"  # type: ignore[union-attr]

    def test_old_ids_stay_exact_beyond_the_cli_history_budget(self, db: Path, proj: Path) -> None:
        old = shown(db, proj).rec_ids[0]
        conn = sqlite3.connect(db)
        conn.executemany(
            "INSERT INTO cli_events(ts, binary, args) VALUES(?, 'll-sprint', '[\"run\",\"a\"]')",
            [("2026-10-01T00:00:00Z",)] * 3000,
        )
        conn.commit()
        conn.close()
        assert feedback(db, proj, old).found is True

    def test_lookup_is_read_only(self, db: Path, proj: Path) -> None:
        rec = shown(db, proj).rec_ids[0]
        before = digest(db)
        for _ in range(2):
            feedback(db, proj, rec)
        assert digest(db) == before and len(fetch_rows(db)) == 1


# ----------------------------------------------------------------------------------- CLI


def semantic(envelope: dict[str, Any]) -> dict[str, Any]:
    """The envelope minus the observational ``recording`` object and ``rec_id`` fields."""
    stripped = {k: v for k, v in envelope.items() if k != "recording"}
    stripped["recommendations"] = [
        {k: v for k, v in r.items() if k != "rec_id"} for r in envelope["recommendations"]
    ]
    return stripped


def run_json(run: Run, *argv: str) -> tuple[int, dict[str, Any]]:
    code, out, err = run("--json", *argv)
    assert err == ""
    envelope = json.loads(out)
    schema = render.load_output_schema()
    assert schema_errors(envelope, schema, schema) == []
    return code, envelope


class TestCliRecording:
    def test_default_records_and_exposes_only_saved_ids(
        self, proj: Path, db: Path, run: Run
    ) -> None:
        code, envelope = run_json(run, "--top", "2")
        assert code == 0 and envelope["recording"] == {"status": "recorded", "reason": None}
        ids = [r["rec_id"] for r in envelope["recommendations"]]
        assert ids == [r["rec_id"] for r in fetch_rows(db)] and all(ids)
        rows = fetch_rows(db)
        assert [r["rank"] for r in rows] == [1, 2]
        assert len({r["invocation_id"] for r in rows}) == 1 and {r["session_id"] for r in rows} == {
            None
        }
        assert {r["requested_top"] for r in rows} == {2}
        assert json.loads(rows[0]["requested_types"]) == []

    def test_text_output_prints_rec_ids(self, proj: Path, db: Path, run: Run) -> None:
        code, out, err = run()
        assert (code, err) == (0, "")
        rec = fetch_rows(db)[0]["rec_id"]
        assert f"rec_id: {rec}" in out and "Recording: recorded" in out

    def test_requested_type_filter_is_stored_in_order(self, proj: Path, db: Path, run: Run) -> None:
        run("--type", "refine-issue", "--type", "implement-issue", "--top", "1")
        assert json.loads(fetch_rows(db)[0]["requested_types"]) == [
            "refine-issue",
            "implement-issue",
        ]

    def test_no_record_and_explain_write_nothing(self, proj: Path, db: Path, run: Run) -> None:
        before = digest(db)
        code, env = run_json(run, "--no-record")
        assert env["recording"] == {"status": "disabled", "reason": "no_record"}
        assert all(r["rec_id"] is None for r in env["recommendations"])
        code, env = run_json(run, "--explain", "implement-issue", "FEAT-001")
        assert env["recording"] == {"status": "disabled", "reason": "explain"}
        run("--explain", "implement-issue", "FEAT-001", "--no-record")
        assert digest(db) == before and fetch_rows(db) == []

    def test_empty_result_records_nothing(self, proj: Path, db: Path, run: Run) -> None:
        for path in (proj / ".issues").rglob("*.md"):
            path.unlink()
        code, env = run_json(run, "--type", "implement-issue")
        assert code == 1 and env["recommendations"] == []
        assert env["recording"] == {"status": "disabled", "reason": "nothing_to_record"}

    def test_semantic_content_is_identical_across_recording_outcomes(
        self, proj: Path, db: Path, run: Run
    ) -> None:
        code_a, recorded = run_json(run)
        _, disabled = run_json(run, "--no-record")
        db.unlink()
        code_c, unavailable = run_json(run)
        assert unavailable["recording"] == {"status": "unavailable", "reason": "schema_not_ready"}
        assert all(r["rec_id"] is None for r in unavailable["recommendations"])
        assert semantic(recorded) == semantic(disabled) == semantic(unavailable)
        assert code_a == code_c == 0

    def test_unprepared_store_text_hint_and_nothing_created(self, proj: Path, run: Run) -> None:
        code, out, err = run()
        assert code == 0 and err == ""
        assert "Recording: unavailable (schema_not_ready)" in out and "ll-session migrate" in out
        assert not list(proj.rglob("history.db*"))

    def test_write_failure_keeps_recommendations_and_exit(
        self, proj: Path, db: Path, run: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, baseline = run_json(run, "--no-record")
        monkeypatch.setattr(recording.uuid, "uuid4", lambda: uuid.UUID(int=3))
        code, env = run_json(run)
        assert code == 0 and env["recording"]["reason"] == "write_failed"
        assert semantic(env) == semantic(baseline)

    @pytest.mark.parametrize(
        ("config", "env", "reason"),
        [
            ({"next": {"recording": {"enabled": False}}}, None, "config_disabled"),
            ({"analytics": {"enabled": False}}, None, "analytics_disabled"),
            (
                {"analytics": {"capture": {"cli_commands": ["ll-loop"]}}},
                None,
                "command_not_captured",
            ),
            ({}, "off", "env_kill_switch"),
            ({}, "0", "env_kill_switch"),
        ],
    )
    def test_capture_gates_disable_before_any_target_resolution(
        self,
        proj: Path,
        db: Path,
        run: Run,
        monkeypatch: pytest.MonkeyPatch,
        config: dict[str, Any],
        env: str | None,
        reason: str,
    ) -> None:
        (proj / ".ll" / "ll-config.json").write_text(json.dumps(config), encoding="utf-8")
        if env is not None:
            monkeypatch.setenv("LL_ANALYTICS_CAPTURE", env)
        monkeypatch.setenv("LL_HISTORY_DB", str(proj / "never-consulted.db"))
        monkeypatch.setattr(
            recording,
            "freeze_history_target",
            lambda *_a, **_k: pytest.fail("target resolved although recording is disabled"),
        )
        _, envelope = run_json(run)
        assert envelope["recording"] == {"status": "disabled", "reason": reason}
        assert fetch_rows(db) == []

    def test_allowlisted_command_records(self, proj: Path, db: Path, run: Run) -> None:
        (proj / ".ll" / "ll-config.json").write_text(
            json.dumps({"analytics": {"enabled": True, "capture": {"cli_commands": ["ll-next"]}}}),
            encoding="utf-8",
        )
        assert run_json(run)[1]["recording"]["status"] == "recorded"

    def test_malformed_recording_config_is_a_usage_error_only_where_consumed(
        self, proj: Path, db: Path, run: Run
    ) -> None:
        (proj / ".ll" / "ll-config.json").write_text(
            json.dumps({"next": {"recording": {"enabled": "yes"}}}), encoding="utf-8"
        )
        code, out, err = run("--json")
        assert (code, out) == (2, "") and "next.recording.enabled" in err
        assert run("--no-record")[0] == 0
        assert run("--explain", "implement-issue", "FEAT-001")[0] == 0
        rec = str(uuid.uuid4())
        assert run("feedback", rec)[0] == 1  # historical lookups ignore the toggle
        assert run("accept", rec)[0] == 1

    def test_relative_env_override_is_cwd_relative_and_absolute_shares(
        self, proj: Path, run: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sub = proj / "pkg"
        sub.mkdir()
        root_store = make_real_store(proj / "rel.db")
        sub_store = make_real_store(sub / "rel.db")
        monkeypatch.setenv("LL_HISTORY_DB", "rel.db")
        run("--no-record")  # untouched
        run()
        monkeypatch.chdir(sub)
        run()
        assert len(fetch_rows(root_store)) == 2 and len(fetch_rows(sub_store)) == 2
        assert {r["project_key"] for r in fetch_rows(root_store) + fetch_rows(sub_store)} == {
            project_key_for(proj)
        }
        monkeypatch.setenv("LL_HISTORY_DB", str(root_store))
        run()
        monkeypatch.chdir(proj)
        rec = fetch_rows(root_store)[-1]["rec_id"]
        assert run("feedback", rec)[0] == 0

    def test_shared_store_between_projects_scopes_ids(
        self, proj: Path, db: Path, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run()
        rec = fetch_rows(db)[0]["rec_id"]
        other = tmp_path / "other"
        make_project(other)
        write_issue(other, "features/P2-FEAT-009-x.md", text=ready_issue())
        monkeypatch.setenv("LL_HISTORY_DB", str(db))
        monkeypatch.chdir(other)
        assert run("feedback", rec)[0] == 1
        assert run("accept", rec)[0] == 1
        assert {r["kind"] for r in fetch_rows(db)} == {"shown"}  # nothing acknowledged
        run()  # the other project records its own offer into the shared file
        assert {r["project_key"] for r in fetch_rows(db)} == {
            project_key_for(proj),
            project_key_for(other),
        }

    def test_subdirectory_shares_the_project_scope_and_relocation_forgets_ids(
        self, proj: Path, db: Path, run: Run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        run()
        rec = fetch_rows(db)[0]["rec_id"]
        sub = proj / "a" / "b"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        assert run("feedback", rec)[0] == 0
        moved = tmp_path / "moved"
        proj.rename(moved)
        monkeypatch.chdir(moved)
        code, out, _ = run("feedback", "--json", rec)
        assert code == 1 and json.loads(out)["found"] is False


class TestCliSubcommands:
    def test_accept_prints_one_human_line_and_is_idempotent(
        self, proj: Path, db: Path, run: Run
    ) -> None:
        run()
        rec = fetch_rows(db)[0]["rec_id"]
        code, out, err = run("accept", rec.upper())  # case-insensitive input
        assert (code, err) == (0, "") and out.count("\n") == 1
        assert out.startswith(f"ll-next: accepted {rec}") and "FEAT-001" in out or "BUG-002" in out
        code, again, _ = run("accept", rec)
        assert code == 0 and again.startswith(f"ll-next: already accepted {rec}")
        rows = fetch_rows(db)
        acknowledged = [r for r in rows if r["kind"] == "accepted_explicit"]
        assert len(acknowledged) == 1 and acknowledged[0]["rec_id"] == rec
        offer = next(r for r in rows if r["rec_id"] == rec and r["kind"] == "shown")
        assert acknowledged[0]["invocation_id"] != offer["invocation_id"]

    def test_accept_ignores_automatic_capture_gates(self, proj: Path, db: Path, run: Run) -> None:
        run()
        rec = fetch_rows(db)[0]["rec_id"]
        (proj / ".ll" / "ll-config.json").write_text(
            json.dumps(
                {"next": {"recording": {"enabled": False}}, "analytics": {"enabled": False}}
            ),
            encoding="utf-8",
        )
        assert run("accept", rec)[0] == 0

    @pytest.mark.parametrize("subcommand", ["accept", "feedback"])
    def test_malformed_ids_are_usage_errors_before_any_storage(
        self, proj: Path, run: Run, subcommand: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            recording, "freeze_history_target", lambda *_a: pytest.fail("storage touched")
        )
        u = str(uuid.uuid4())
        for bad in ("abc", f"{{{u}}}", f"urn:uuid:{u}", u.replace("-", "")):
            code, out, err = run(subcommand, bad)
            assert (code, out) == (2, "") and err
        assert run(subcommand)[0] == 2  # missing REC_ID

    def test_flags_belong_after_the_subcommand(self, proj: Path, run: Run) -> None:
        rec = str(uuid.uuid4())
        code, out, err = run("--json", "feedback", rec)
        assert (code, out) == (2, "") and err
        assert run("accept", "--json", rec)[0] == 2  # accept has no --json in v1

    @pytest.mark.parametrize("subcommand", ["accept", "feedback"])
    def test_help_does_no_history_work(
        self, proj: Path, run: Run, subcommand: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            recording, "freeze_history_target", lambda *_a: pytest.fail("storage touched")
        )
        code, out, _ = run(subcommand, "--help")
        assert code == 0 and "REC_ID" in out

    def test_unknown_ids_exit_1_and_unprepared_store_exits_2(
        self, proj: Path, db: Path, run: Run
    ) -> None:
        rec = str(uuid.uuid4())
        assert run("accept", rec)[0] == 1
        assert run("feedback", rec)[0] == 1
        db.unlink()
        code, out, err = run("accept", rec)
        assert (code, out) == (2, "") and "ll-session migrate" in err
        code, out, err = run("feedback", rec)
        assert (code, out) == (2, "") and "schema_not_ready" in err
        assert not db.exists()  # never recreated (SQLite may leave stale WAL sidecars behind)

    def test_historical_commands_bypass_arena_collection_and_config_validation(
        self, proj: Path, db: Path, run: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run()
        rec = fetch_rows(db)[0]["rec_id"]
        for victim in proj.glob(".issues/*/*.md"):  # the offered targets are gone
            victim.unlink()
        poisoned = [
            {"next": {"verbs": {"implement-issue": {"cap": "x"}}}},
            {"next": {"loop_history": {"weights": "bad"}}},
            {"next": {"recording": [1]}},
        ]
        monkeypatch.setattr(
            state_module,
            "collect_project_state",
            lambda *_a, **_k: pytest.fail("collected project state"),
        )
        import little_loops.next_arena.candidates as candidates

        monkeypatch.setattr(
            candidates, "assess_candidates", lambda *_a, **_k: pytest.fail("generators ran")
        )
        for config in poisoned:
            (proj / ".ll" / "ll-config.json").write_text(json.dumps(config), encoding="utf-8")
            code, out, _ = run("feedback", "--json", rec)
            assert code == 0 and json.loads(out)["found"] is True
        assert run("accept", rec)[0] == 0
        (proj / ".ll" / "ll-config.json").write_text("{not json", encoding="utf-8")
        assert run("feedback", rec)[0] == 2

    def test_feedback_documents_validate_for_exits_0_1_and_2(
        self, proj: Path, db: Path, run: Run
    ) -> None:
        run()
        rec = fetch_rows(db)[0]["rec_id"]
        schema = render.load_feedback_schema()

        def doc(*argv: str) -> tuple[int, dict[str, Any]]:
            code, out, err = run(*argv)
            assert err == ""
            parsed = json.loads(out)
            assert schema_errors(parsed, schema, schema) == []
            return code, parsed

        code, found = doc("feedback", "--json", rec)
        assert (code, found["state"], found["accepted_at"], found["found"]) == (
            0,
            "unknown",
            None,
            True,
        )
        run("accept", rec)
        code, accepted = doc("feedback", "--json", rec)
        assert (code, accepted["state"]) == (0, "accepted") and accepted["accepted_at"]
        assert accepted["offer"]["action_spec"]["variant"] == "slash"
        assert accepted["offer"]["display_command"].startswith("/ll:")
        code, absent = doc("feedback", "--json", str(uuid.uuid4()))
        assert (code, absent["found"], absent["state"], absent["reason"]) == (
            1,
            False,
            None,
            "rec_id_not_found",
        )
        db.unlink()
        code, unavailable = doc("feedback", "--json", rec)
        assert code == 2 and unavailable["availability"] == "unavailable"
        assert (unavailable["found"], unavailable["state"]) == (False, None)
        assert unavailable["reason"] == "schema_not_ready"

    def test_feedback_is_read_only(self, proj: Path, db: Path, run: Run) -> None:
        run()
        rec = fetch_rows(db)[0]["rec_id"]
        before = digest(db)
        run("feedback", rec)
        run("feedback", "--json", rec)
        assert digest(db) == before and {r["kind"] for r in fetch_rows(db)} == {"shown"}
        assert not (proj / ".ll" / "history.db-journal").exists()

    def test_feedback_reports_provenance_and_remote_is_unsupported(
        self, proj: Path, db: Path, run: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run()
        rec = fetch_rows(db)[0]["rec_id"]
        _, out, _ = run("feedback", "--json", rec)
        assert json.loads(out)["provenance"] == {"store": str(db), "source": "default"}
        remote = RemoteTarget(
            BackendConfig(provider="turso", url="https://x.invalid", project_id="p")
        )
        monkeypatch.setattr(
            recording,
            "freeze_history_target",
            lambda _root: (remote, {"store": "remote:turso", "source": "history.backend"}),
        )
        code, out, _ = run("feedback", "--json", rec)
        doc = json.loads(out)
        assert (code, doc["availability"], doc["reason"]) == (
            2,
            "unavailable",
            "remote_unsupported_v1",
        )
        assert run("accept", rec)[0] == 2

    def test_help_documents_recording_and_subcommands(self, run: Run) -> None:
        code, out, _ = run("--help")
        assert code == 0
        for text in ("--no-record", "accept REC_ID", "feedback REC_ID", "history"):
            assert text in out
        import little_loops.cli.next as cli_next

        assert "no ``history.db``" not in (cli_next.__doc__ or "")


# ----------------------------------------------------------------- time / rendering contract


def test_instant_formatter_is_microsecond_precise_and_the_public_one_is_not() -> None:
    whole = datetime(2026, 10, 8, 1, 2, 3, tzinfo=UTC)
    frac = datetime(2026, 10, 8, 1, 2, 3, 45, tzinfo=UTC)
    assert render.format_instant(whole) == "2026-10-08T01:02:03.000000Z"
    assert render.format_instant(frac) == "2026-10-08T01:02:03.000045Z"
    assert render.format_as_of(frac) == "2026-10-08T01:02:03Z"


def test_whole_second_times_round_trip_through_storage_and_feedback(
    tmp_path: Path, proj: Path
) -> None:
    db = make_real_store(tmp_path / "t.db")
    whole = datetime(2026, 10, 8, 9, 30, 0, tzinfo=UTC)
    rec = shown(db, proj, as_of=whole, now=lambda: whole).rec_ids[0]
    accept(db, proj, rec, now=lambda: whole)
    result = feedback(db, proj, rec, now=lambda: whole)
    assert (
        result.offer.as_of == result.offer.ts == result.accepted_at == "2026-10-08T09:30:00.000000Z"
    )
    document = render.build_feedback_document(rec, result)
    assert document["read_observed_at"] == "2026-10-08T09:30:00.000000Z"


def test_rollback_in_wall_clock_does_not_invalidate_acknowledgement(
    tmp_path: Path, proj: Path
) -> None:
    db = make_real_store(tmp_path / "t.db")
    rec = shown(db, proj, now=lambda: LATER).rec_ids[0]
    earlier = datetime(2020, 1, 1, tzinfo=UTC)
    assert accept(db, proj, rec, now=lambda: earlier).status == "accepted"
    assert feedback(db, proj, rec).state == "accepted"


def test_generated_schemas_match_checked_in_files_and_package_data() -> None:
    assert json.loads(render.feedback_schema_text()) == render.load_feedback_schema()
    assert render.feedback_schema_text() == (
        Path(render.__file__).with_name(render.FEEDBACK_SCHEMA_FILENAME).read_text("utf-8")
    )
    from little_loops.package_data import PACKAGE_DATA_ASSETS

    assert render.FEEDBACK_SCHEMA_ASSET in PACKAGE_DATA_ASSETS


def test_v4_envelope_requires_recording_and_nullable_rec_id() -> None:
    schema = render.load_output_schema()
    assert schema["properties"]["schema_version"] == {"const": 4}
    assert "recording" in schema["required"]
    recommendation = schema["$defs"]["recommendation"]
    assert "rec_id" in recommendation["required"]
    reasons = {
        r
        for branch in schema["$defs"]["recording"]["oneOf"]
        for r in branch["properties"]["reason"].get("enum", [])
    }
    assert reasons == set(render.RECORDING_DISABLED_REASONS) | set(
        render.RECORDING_UNAVAILABLE_REASONS
    )
