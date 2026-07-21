"""AC tests for the ENH-2712 live per-invocation usage_events writer spike.

Retires the outcome-confidence risk factor: "No existing live per-invocation
writer exists yet ... unproven internal mechanism with no test coverage."
"""

from __future__ import annotations

import ast
import multiprocessing
import sqlite3
from pathlib import Path

import pytest

from .writer import derive_run_id, init_schema, simulate_run


def _rows(db_path: str) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT run_id, input_tokens, output_tokens FROM usage_events ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


class TestUsageEventsRunIdWriter:
    def test_single_run_stamps_correct_run_id(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "history.db")
        init_schema(db_path)

        run_id = simulate_run(db_path, "rn-refine", "2026-07-21T12:00:00.000Z", 5)

        rows = _rows(db_path)
        assert len(rows) == 5
        assert all(row[0] == run_id for row in rows)

    def test_concurrent_runs_do_not_cross_attribute(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "history.db")
        init_schema(db_path)

        loop_names = ["rn-refine", "rn-implement", "autodev", "spike-gate"]
        args = [
            (db_path, name, f"2026-07-21T12:0{i}:00.000Z", 25)
            for i, name in enumerate(loop_names)
        ]
        with multiprocessing.Pool(processes=len(args)) as pool:
            run_ids = pool.starmap(simulate_run, args)

        assert len(set(run_ids)) == len(run_ids)  # every run got a distinct run_id

        rows = _rows(db_path)
        assert len(rows) == 25 * len(args)
        by_run: dict[str, int] = {}
        for run_id, _input, _output in rows:
            by_run[run_id] = by_run.get(run_id, 0) + 1

        assert set(by_run) == set(run_ids)
        for run_id in run_ids:
            assert by_run[run_id] == 25

    def test_concurrent_runs_lose_no_writes(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "history.db")
        init_schema(db_path)

        n_runs = 8
        n_per_run = 40
        args = [
            (db_path, f"loop-{i}", f"2026-07-21T13:{i:02d}:00.000Z", n_per_run)
            for i in range(n_runs)
        ]
        with multiprocessing.Pool(processes=n_runs) as pool:
            pool.starmap(simulate_run, args)

        rows = _rows(db_path)
        assert len(rows) == n_runs * n_per_run

    def test_run_id_derivation_matches_executor_format(self) -> None:
        # Port of fsm/executor.py:2601,2604's inline derivation, reproduced
        # here (not imported) to assert byte-identical output.
        started_at = "2026-07-21T17:29:51.123456+00:00"
        loop_name = "rn-refine"
        expected = started_at.replace(":", "").replace(".", "").replace("+", "")[:17]
        expected = f"{expected}-{loop_name}"

        assert derive_run_id(started_at, loop_name) == expected

    def test_spike_does_not_import_production_modules(self) -> None:
        writer_path = Path(__file__).parent / "writer.py"
        tree = ast.parse(writer_path.read_text())

        forbidden_prefixes = ("little_loops",)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            for name in names:
                assert not any(
                    name.startswith(prefix) for prefix in forbidden_prefixes
                ), f"writer.py must not import production module {name!r}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
