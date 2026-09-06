"""Tests for runs.py: read_base_sha/read_base_dirty dequeue-time stamp readers (ENH-2775 split from test_history_reader.py)."""

from __future__ import annotations

from pathlib import Path

from little_loops.history_reader import (
    read_base_dirty,
    read_base_sha,
)
from little_loops.session_store import (
    ensure_db,
    record_orchestration_run,
)


class TestReadBaseSha:
    """ENH-2866: the single dequeue-time base-SHA reader, None when unstamped."""

    @staticmethod
    def _stamp(db: Path, **kwargs) -> None:
        base = {"driver": "ll-auto", "status": "running"}
        record_orchestration_run(db, **{**base, **kwargs})

    def test_resolves_stamp_with_run_id(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._stamp(db, run_id="r1", issue_id="ENH-2866", base_sha="abc123")
        assert read_base_sha("ENH-2866", run_id="r1", db=db) == "abc123"

    def test_resolves_stamp_without_run_id(self, tmp_path: Path) -> None:
        """ENH-2853's oracle loop runs out-of-process and has no run_id to supply."""

        db = tmp_path / "history.db"
        self._stamp(db, run_id="r1", issue_id="ENH-2866", base_sha="abc123")
        assert read_base_sha("ENH-2866", db=db) == "abc123"

    def test_most_recent_stamped_row_wins(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._stamp(db, run_id="r1", issue_id="ENH-2866", base_sha="older")
        self._stamp(db, run_id="r2", issue_id="ENH-2866", base_sha="newer")
        assert read_base_sha("ENH-2866", db=db) == "newer"

    def test_unstamped_later_row_does_not_shadow_stamped_earlier_row(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._stamp(db, run_id="r1", issue_id="ENH-2866", base_sha="stamped")
        self._stamp(db, run_id="r2", issue_id="ENH-2866", status="completed")
        assert read_base_sha("ENH-2866", db=db) == "stamped"

    def test_returns_none_when_row_is_unstamped(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._stamp(db, run_id="r1", issue_id="ENH-2866", status="completed")
        assert read_base_sha("ENH-2866", db=db) is None
        assert read_base_sha("ENH-2866", run_id="r1", db=db) is None

    def test_returns_none_when_no_row_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        assert read_base_sha("ENH-9999", db=db) is None

    def test_returns_none_for_missing_db(self, tmp_path: Path) -> None:
        assert read_base_sha("ENH-2866", db=tmp_path / "no" / "history.db") is None

    def test_never_raises_on_malformed_db(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        db.write_text("this is not a sqlite database")
        assert read_base_sha("ENH-2866", db=db) is None

    def test_failed_rev_parse_reads_back_as_none_not_empty_string(self, tmp_path: Path) -> None:
        """A capture site that coerces "" -> None keeps NULL-means-unstamped honest."""

        db = tmp_path / "history.db"
        self._stamp(db, run_id="r1", issue_id="ENH-2866", base_sha="")
        result = read_base_sha("ENH-2866", db=db)
        assert result is None
        assert result != ""

    def test_dirty_flag_is_readable_alongside_the_sha(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_orchestration_runs

        db = tmp_path / "history.db"
        self._stamp(db, run_id="r1", issue_id="ENH-2866", base_sha="abc", base_dirty=True)
        rows = recent_orchestration_runs(issue_id="ENH-2866", db=db)
        assert len(rows) == 1
        assert rows[0].base_sha == "abc"
        assert rows[0].base_dirty == 1


class TestReadBaseDirty:
    """ENH-3142: the additive base_dirty reader, converting int->bool at the boundary."""

    @staticmethod
    def _stamp(db: Path, **kwargs) -> None:
        base = {"driver": "ll-auto", "status": "running"}
        record_orchestration_run(db, **{**base, **kwargs})

    def test_resolves_stamp_with_run_id(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._stamp(db, run_id="r1", issue_id="ENH-3142", base_dirty=True)
        assert read_base_dirty("ENH-3142", run_id="r1", db=db) is True

    def test_resolves_stamp_without_run_id(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._stamp(db, run_id="r1", issue_id="ENH-3142", base_dirty=False)
        assert read_base_dirty("ENH-3142", db=db) is False

    def test_returns_bool_not_int(self, tmp_path: Path) -> None:
        """The stored int is converted to bool at the return boundary."""

        db = tmp_path / "history.db"
        self._stamp(db, run_id="r1", issue_id="ENH-3142", base_dirty=True)
        result = read_base_dirty("ENH-3142", db=db)
        assert result is True
        assert isinstance(result, bool)

    def test_most_recent_stamped_row_wins(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._stamp(db, run_id="r1", issue_id="ENH-3142", base_dirty=False)
        self._stamp(db, run_id="r2", issue_id="ENH-3142", base_dirty=True)
        assert read_base_dirty("ENH-3142", db=db) is True

    def test_unstamped_later_row_does_not_shadow_stamped_earlier_row(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._stamp(db, run_id="r1", issue_id="ENH-3142", base_dirty=True)
        self._stamp(db, run_id="r2", issue_id="ENH-3142", status="completed")
        assert read_base_dirty("ENH-3142", db=db) is True

    def test_returns_none_when_row_is_unstamped(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._stamp(db, run_id="r1", issue_id="ENH-3142", status="completed")
        assert read_base_dirty("ENH-3142", db=db) is None
        assert read_base_dirty("ENH-3142", run_id="r1", db=db) is None

    def test_returns_none_when_no_row_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        assert read_base_dirty("ENH-9999", db=db) is None

    def test_returns_none_for_missing_db(self, tmp_path: Path) -> None:
        assert read_base_dirty("ENH-3142", db=tmp_path / "no" / "history.db") is None

    def test_never_raises_on_malformed_db(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        db.write_text("this is not a sqlite database")
        assert read_base_dirty("ENH-3142", db=db) is None
