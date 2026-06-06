"""Snapshot tests for shared CLI output primitives.

Golden files live in scripts/tests/__snapshots__/ and are version-controlled.
To regenerate after an intentional formatting change:

    pytest --snapshot-update scripts/tests/test_snapshot_output_primitives.py
"""

from __future__ import annotations

import pytest
from syrupy.assertion import SnapshotAssertion


@pytest.mark.usefixtures("stable_snapshot_env")
class TestTableSnapshot:
    """Snapshot tests for table()."""

    def test_two_col_table(self, snapshot: SnapshotAssertion) -> None:
        from little_loops.cli.output import table

        result = table(["Name", "Status"], [["foo", "open"], ["bar", "done"]])
        assert snapshot == result

    def test_single_col_table(self, snapshot: SnapshotAssertion) -> None:
        from little_loops.cli.output import table

        result = table(["Item"], [["alpha"], ["beta"], ["gamma"]])
        assert snapshot == result

    def test_table_with_truncation(self, snapshot: SnapshotAssertion) -> None:
        from little_loops.cli.output import table

        result = table(["Key", "Value"], [["short", "a" * 50]], max_col_width=20)
        assert snapshot == result

    def test_three_col_issue_table(self, snapshot: SnapshotAssertion) -> None:
        from little_loops.cli.output import table

        result = table(
            ["ID", "Priority", "Title"],
            [
                ["ENH-1965", "P3", "Add Snapshot Testing"],
                ["BUG-001", "P0", "Critical crash"],
                ["FEAT-042", "P2", "Dark mode support"],
            ],
        )
        assert snapshot == result


@pytest.mark.usefixtures("stable_snapshot_env")
class TestStatusBlockSnapshot:
    """Snapshot tests for status_block()."""

    def test_two_key_status_block(self, snapshot: SnapshotAssertion) -> None:
        from little_loops.cli.output import status_block

        result = status_block({"Status": "open", "Priority": "P3"})
        assert snapshot == result

    def test_aligned_status_block(self, snapshot: SnapshotAssertion) -> None:
        from little_loops.cli.output import status_block

        result = status_block(
            {
                "ID": "ENH-1965",
                "Title": "Add snapshot testing",
                "Status": "in_progress",
                "Priority": "P3",
                "Type": "ENH",
            }
        )
        assert snapshot == result


@pytest.mark.usefixtures("stable_snapshot_env")
class TestProgressSnapshot:
    """Snapshot tests for progress()."""

    def test_half_filled_bar(self, snapshot: SnapshotAssertion) -> None:
        from little_loops.cli.output import progress

        result = progress(50, 100, 20)
        assert snapshot == result

    def test_full_bar(self, snapshot: SnapshotAssertion) -> None:
        from little_loops.cli.output import progress

        result = progress(100, 100, 20)
        assert snapshot == result

    def test_empty_bar(self, snapshot: SnapshotAssertion) -> None:
        from little_loops.cli.output import progress

        result = progress(0, 100, 20)
        assert snapshot == result


@pytest.mark.usefixtures("stable_snapshot_env")
class TestSparklineSnapshot:
    """Snapshot tests for sparkline()."""

    def test_half_filled(self, snapshot: SnapshotAssertion) -> None:
        from little_loops.cli.output import sparkline

        result = sparkline(5, 10, 10)
        assert snapshot == result

    def test_full(self, snapshot: SnapshotAssertion) -> None:
        from little_loops.cli.output import sparkline

        result = sparkline(10, 10, 10)
        assert snapshot == result

    def test_empty(self, snapshot: SnapshotAssertion) -> None:
        from little_loops.cli.output import sparkline

        result = sparkline(0, 10, 10)
        assert snapshot == result
