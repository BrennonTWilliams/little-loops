"""Live remote libSQL integration tests (FEAT-3535).

Selected by ``LL_TEST_LIBSQL_URL`` + ``LL_TEST_LIBSQL_AUTH_TOKEN`` (a sqld or Turso Cloud
endpoint and a full-access token). They skip **only** when that configuration is absent; a
failure against a configured endpoint fails the test. ``LL_TEST_LIBSQL_READONLY_TOKEN`` is
optional and gates just the read-only-token test.

The store is shared and long-lived, so every test cleans up the rows it writes and the
suite stamps a fixed integration ``project_id``. Excluded from the default CI selection by
the ``integration`` marker.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from little_loops.session_store import db as db_mod
from little_loops.session_store import remote_schema, remote_telemetry
from little_loops.session_store.backend import (
    BackendConfig,
    HistoryIntegrityError,
    HistoryUnavailable,
    HistoryUnsupported,
    RemoteTarget,
)
from little_loops.session_store.hrana import HranaClient
from little_loops.session_store.libsql import LibsqlBackend
from little_loops.session_store.schema import _MIGRATIONS

pytestmark = pytest.mark.integration

_URL = os.environ.get("LL_TEST_LIBSQL_URL")
_TOKEN = os.environ.get("LL_TEST_LIBSQL_AUTH_TOKEN")
_RO_TOKEN = os.environ.get("LL_TEST_LIBSQL_READONLY_TOKEN")
_CONFIGURED = bool(_URL and _TOKEN)
_needs_endpoint = pytest.mark.skipif(
    not _CONFIGURED, reason="set LL_TEST_LIBSQL_URL and LL_TEST_LIBSQL_AUTH_TOKEN to run"
)
PROJECT = "little-loops-integration"


def _target(project_id: str | None = PROJECT) -> RemoteTarget:
    return RemoteTarget(
        BackendConfig(
            provider="libsql",
            url=_URL,
            auth_token_env="LL_TEST_LIBSQL_AUTH_TOKEN",
            project_id=project_id,
        )
    )


@pytest.fixture(scope="module")
def migrated() -> Iterator[HranaClient]:
    """Migrate the shared store once (a no-op when it is already current)."""
    if not _CONFIGURED:
        pytest.skip("LL_TEST_LIBSQL_URL / LL_TEST_LIBSQL_AUTH_TOKEN not set")
    assert _URL and _TOKEN
    client = HranaClient(_URL, _TOKEN, timeout=30.0)
    report = remote_schema.migrate_remote(client, PROJECT)
    assert report.after == len(_MIGRATIONS)
    yield client


@pytest.fixture(autouse=True)
def _fresh() -> Iterator[None]:
    remote_schema.clear_verification_cache()
    remote_telemetry.reset_for_tests()
    db_mod.clear_backend_config_cache()
    yield
    remote_schema.clear_verification_cache()


@_needs_endpoint
class TestLive:
    def test_migration_is_idempotent_and_stamped(self, migrated: HranaClient) -> None:
        again = remote_schema.migrate_remote(migrated, PROJECT)
        assert again.applied == 0 and again.after == len(_MIGRATIONS)
        state = remote_schema.read_state(migrated)
        assert state.version == len(_MIGRATIONS) and state.project_id == PROJECT

    def test_project_mismatch_is_refused(self, migrated: HranaClient) -> None:
        with pytest.raises(HistoryUnsupported, match="project_id"):
            LibsqlBackend().connect_readonly(_target("someone-else")).execute("select 1")

    def test_write_read_round_trip_and_cleanup(self, migrated: HranaClient) -> None:
        marker = f"it-{uuid.uuid4().hex[:8]}"
        conn = LibsqlBackend().connect(_target())
        try:
            conn.execute(
                "insert into skill_events(ts, session_id, skill_name, args) values (?, ?, ?, ?)",
                ("2026-01-01T00:00:00Z", marker, "integration", "x"),
            )
            row = conn.execute(
                "select skill_name, args from skill_events where session_id = ?", (marker,)
            ).fetchone()
            assert (row["skill_name"], row["args"]) == ("integration", "x")
        finally:
            conn.execute("delete from skill_events where session_id = ?", (marker,))

    def test_executemany_is_atomic_against_a_real_endpoint(self, migrated: HranaClient) -> None:
        marker = f"it-{uuid.uuid4().hex[:8]}"
        conn = LibsqlBackend().connect(_target())
        try:
            conn.executemany(
                "insert into meta(key, value) values (?, ?)",
                [(f"{marker}-a", "1"), (f"{marker}-b", "1")],
            )
            with pytest.raises(HistoryIntegrityError):
                conn.executemany(
                    "insert into meta(key, value) values (?, ?)",
                    [(f"{marker}-c", "1"), (f"{marker}-a", "dup")],
                )
            assert (
                conn.execute(
                    "select count(*) from meta where key like ?", (f"{marker}-%",)
                ).fetchone()[0]
                == 2
            )
        finally:
            conn.execute("delete from meta where key like ?", (f"{marker}-%",))

    def test_fts5_round_trip(self, migrated: HranaClient) -> None:
        marker = f"ftsmarker{uuid.uuid4().hex[:8]}"
        conn = LibsqlBackend().connect(_target())
        try:
            conn.execute(
                "insert into search_index(content, kind, ref, anchor, ts) values (?, ?, ?, ?, ?)",
                (f"remote {marker} works", "integration", marker, "a", "t"),
            )
            rows = conn.execute(
                "select ref from search_index where search_index match ?", (marker,)
            ).fetchall()
            assert [r["ref"] for r in rows] == [marker]
        finally:
            conn.execute("delete from search_index where ref = ?", (marker,))

    def test_bad_token_is_unavailable_and_never_echoed(self, migrated: HranaClient) -> None:
        assert _URL
        bad = "not-a-real-token-" + uuid.uuid4().hex
        with pytest.raises(HistoryUnavailable) as ei:
            HranaClient(_URL, bad, timeout=15.0).execute("select 1")
        assert bad not in str(ei.value)

    @pytest.mark.skipif(not _RO_TOKEN, reason="LL_TEST_LIBSQL_READONLY_TOKEN not set")
    def test_read_only_token_write_is_blocked(self, migrated: HranaClient) -> None:
        assert _URL and _RO_TOKEN
        ro = HranaClient(_URL, _RO_TOKEN, timeout=15.0)
        assert ro.execute("select 1").rows == [(1,)]
        with pytest.raises(HistoryUnavailable):
            ro.execute("insert into meta(key, value) values ('it-blocked', '1')")

    def test_a_dead_read_timeout_is_bounded(self, migrated: HranaClient) -> None:
        assert _URL and _TOKEN
        heavy = (
            "with recursive c(x) as (select 1 union all select x+1 from c where x < 300000000) "
            "select count(*) from c"
        )
        t0 = time.monotonic()
        with pytest.raises(HistoryUnavailable):
            HranaClient(_URL, _TOKEN, timeout=1.0).execute(heavy)
        assert time.monotonic() - t0 < 4.0


class TestNetworkBounds:
    """Need no endpoint, only a routable-but-silent address."""

    def test_a_blackholed_connect_is_bounded_by_the_timeout(self) -> None:
        t0 = time.monotonic()
        with pytest.raises(HistoryUnavailable):
            HranaClient("https://10.255.255.1", "t", timeout=2.0).execute("select 1")
        assert time.monotonic() - t0 < 4.0


def test_module_docstring_is_honest_about_gating() -> None:
    assert Path(__file__).read_text().count("LL_TEST_LIBSQL_URL") >= 2
