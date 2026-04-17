"""Unit tests for little_loops.fsm.rate_limit_circuit.RateLimitCircuit."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from little_loops.fsm.rate_limit_circuit import STALE_THRESHOLD_SECONDS, RateLimitCircuit


class TestRateLimitCircuit:
    """Tests for RateLimitCircuit file-backed state + concurrency."""

    @pytest.fixture
    def circuit_path(self, tmp_path: Path) -> Path:
        """Path under tmp_path mirroring the real .loops/tmp layout."""
        return tmp_path / ".loops" / "tmp" / "rate-limit-circuit.json"

    def test_record_creates_file(self, circuit_path: Path) -> None:
        """First record_rate_limit creates parent dirs and writes JSON."""
        circuit = RateLimitCircuit(circuit_path)
        assert not circuit_path.parent.exists()

        circuit.record_rate_limit(60.0)

        assert circuit_path.exists()
        data = json.loads(circuit_path.read_text())
        assert data["attempts"] == 1
        assert "first_seen" in data
        assert "last_seen" in data
        assert "estimated_recovery_at" in data
        assert data["estimated_recovery_at"] >= data["last_seen"] + 59.0

    def test_record_updates_existing(self, circuit_path: Path) -> None:
        """Successive records increment attempts; recovery advances monotonically."""
        circuit = RateLimitCircuit(circuit_path)
        circuit.record_rate_limit(30.0)
        first = json.loads(circuit_path.read_text())

        time.sleep(0.01)
        circuit.record_rate_limit(120.0)
        second = json.loads(circuit_path.read_text())

        assert second["attempts"] == 2
        assert second["first_seen"] == first["first_seen"]
        assert second["last_seen"] >= first["last_seen"]
        assert second["estimated_recovery_at"] >= first["estimated_recovery_at"]

    def test_stale_detection(self, circuit_path: Path) -> None:
        """Entry with last_seen older than STALE_THRESHOLD_SECONDS is stale."""
        circuit = RateLimitCircuit(circuit_path)
        circuit_path.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        stale_last_seen = now - (STALE_THRESHOLD_SECONDS + 60.0)
        circuit_path.write_text(
            json.dumps(
                {
                    "first_seen": stale_last_seen,
                    "last_seen": stale_last_seen,
                    "attempts": 3,
                    "estimated_recovery_at": stale_last_seen + 30.0,
                }
            )
        )

        assert circuit.is_stale() is True

    def test_get_estimated_recovery_stale_returns_none(self, circuit_path: Path) -> None:
        """Stale entry yields None from get_estimated_recovery()."""
        circuit = RateLimitCircuit(circuit_path)
        circuit_path.parent.mkdir(parents=True, exist_ok=True)
        stale = time.time() - (STALE_THRESHOLD_SECONDS + 1.0)
        circuit_path.write_text(
            json.dumps(
                {
                    "first_seen": stale,
                    "last_seen": stale,
                    "attempts": 1,
                    "estimated_recovery_at": stale + 10.0,
                }
            )
        )

        assert circuit.get_estimated_recovery() is None

    def test_get_estimated_recovery_absent_returns_none(self, circuit_path: Path) -> None:
        """Missing file returns None (baseline sanity)."""
        circuit = RateLimitCircuit(circuit_path)
        assert circuit.get_estimated_recovery() is None

    def test_concurrent_access(self, circuit_path: Path) -> None:
        """Two threads writing concurrently produce a valid, non-corrupted file."""
        circuit = RateLimitCircuit(circuit_path)

        start_gate = threading.Event()
        done_a = threading.Event()
        done_b = threading.Event()
        order: list[str] = []

        def worker_a() -> None:
            start_gate.wait(timeout=5)
            for _ in range(20):
                circuit.record_rate_limit(10.0)
            order.append("a_done")
            done_a.set()

        def worker_b() -> None:
            start_gate.wait(timeout=5)
            for _ in range(20):
                circuit.record_rate_limit(15.0)
            order.append("b_done")
            done_b.set()

        t_a = threading.Thread(target=worker_a)
        t_b = threading.Thread(target=worker_b)
        t_a.start()
        t_b.start()
        start_gate.set()

        t_a.join(timeout=10)
        t_b.join(timeout=10)
        assert done_a.is_set() and done_b.is_set()
        assert len(order) == 2

        data = json.loads(circuit_path.read_text())
        assert data["attempts"] == 40
        assert data["last_seen"] >= data["first_seen"]
        assert data["estimated_recovery_at"] >= data["last_seen"]

    def test_atomic_write_crash_safety(self, circuit_path: Path) -> None:
        """File is never partially written — every observable state is valid JSON."""
        circuit = RateLimitCircuit(circuit_path)
        circuit.record_rate_limit(30.0)

        stop = threading.Event()
        errors: list[Exception] = []

        def writer() -> None:
            for _ in range(50):
                if stop.is_set():
                    return
                try:
                    circuit.record_rate_limit(5.0)
                except Exception as e:
                    errors.append(e)
                    return

        def reader() -> None:
            for _ in range(200):
                if stop.is_set():
                    return
                try:
                    raw = circuit_path.read_text()
                except FileNotFoundError:
                    continue
                if not raw:
                    continue
                try:
                    json.loads(raw)
                except json.JSONDecodeError as e:
                    errors.append(e)
                    stop.set()
                    return

        t_w = threading.Thread(target=writer)
        t_r = threading.Thread(target=reader)
        t_w.start()
        t_r.start()
        t_w.join(timeout=10)
        stop.set()
        t_r.join(timeout=10)

        assert errors == [], f"partial-write or error observed: {errors}"

    def test_clear_removes_file(self, circuit_path: Path) -> None:
        """clear() removes the JSON file; recovery then returns None."""
        circuit = RateLimitCircuit(circuit_path)
        circuit.record_rate_limit(30.0)
        assert circuit_path.exists()

        circuit.clear()
        assert not circuit_path.exists()
        assert circuit.get_estimated_recovery() is None

    def test_clear_handles_missing_file(self, circuit_path: Path) -> None:
        """clear() on nonexistent file is a no-op."""
        circuit = RateLimitCircuit(circuit_path)
        circuit.clear()  # must not raise
