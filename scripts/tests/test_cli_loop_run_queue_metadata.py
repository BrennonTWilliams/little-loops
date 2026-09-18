"""Tests for cli/loop/run.py's `_write_queue_start_metadata` (FEAT-3498).

The full `cmd_run()` path (instance-id/run_dir resolution, worktree chdir,
argparse wiring of --queue-entry-id/--queue-metadata-out) is exercised
end-to-end by test_cli_queue_run.py's stubbed-subprocess dispatch tests; this
file unit-tests the atomic-write primitive itself in isolation.
"""

from __future__ import annotations

import json
from pathlib import Path

from little_loops.cli.loop.run import _write_queue_start_metadata


class TestWriteQueueStartMetadata:
    def test_writes_expected_payload(self, tmp_path: Path) -> None:
        dest = tmp_path / "metadata" / "entry-1.json"
        _write_queue_start_metadata(
            dest, queue_id="entry-1", instance_id="inst-abc", run_dir="/proj/.loops/runs/inst-abc"
        )
        payload = json.loads(dest.read_text())
        assert payload == {
            "queueId": "entry-1",
            "instanceId": "inst-abc",
            "runDir": "/proj/.loops/runs/inst-abc",
        }

    def test_no_leftover_temp_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "entry-1.json"
        _write_queue_start_metadata(dest, queue_id="x", instance_id="y", run_dir="/z")
        names = {p.name for p in tmp_path.glob("*")}
        assert names == {"entry-1.json"}

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        dest = tmp_path / "nested" / "dir" / "entry-1.json"
        _write_queue_start_metadata(dest, queue_id="x", instance_id="y", run_dir="/z")
        assert dest.exists()
