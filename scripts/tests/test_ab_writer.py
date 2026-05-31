"""Unit tests for ab_writer module — A/B baseline results aggregation and I/O."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from little_loops.ab_writer import (
    ABResults,
    ab_results_to_dict,
    calculate_ab_summary,
    get_ab_schema,
    read_ab_json,
    write_ab_json,
)


def _make_item(
    index: int,
    harness_pass: bool = True,
    baseline_pass: bool = False,
    harness_tokens: int = 1000,
    baseline_tokens: int = 500,
    harness_duration_ms: int = 2000,
    baseline_duration_ms: int = 1000,
    **kwargs: Any,
) -> dict[str, Any]:
    return {
        "index": index,
        "harness_pass": harness_pass,
        "baseline_pass": baseline_pass,
        "harness_tokens": harness_tokens,
        "baseline_tokens": baseline_tokens,
        "harness_duration_ms": harness_duration_ms,
        "baseline_duration_ms": baseline_duration_ms,
        "confidence": kwargs.get("confidence", 0.9),
        "reason": kwargs.get("reason", "test"),
    }


class TestABResults:
    """Tests for ABResults dataclass and serialization."""

    def test_empty_results(self) -> None:
        """Empty per_item list produces zero rates."""
        results = calculate_ab_summary([])
        assert results.harness_pass_rate == 0.0
        assert results.baseline_pass_rate == 0.0
        assert results.delta == 0.0
        assert results.median_tokens_harness == 0
        assert results.median_tokens_baseline == 0
        assert results.median_duration_harness == 0.0
        assert results.median_duration_baseline == 0.0
        assert results.per_item == []

    def test_all_pass(self) -> None:
        """All items pass both arms."""
        items = [
            _make_item(0, harness_pass=True, baseline_pass=True),
            _make_item(1, harness_pass=True, baseline_pass=True),
        ]
        results = calculate_ab_summary(items)
        assert results.harness_pass_rate == 1.0
        assert results.baseline_pass_rate == 1.0
        assert results.delta == 0.0

    def test_all_fail(self) -> None:
        """All items fail both arms."""
        items = [
            _make_item(0, harness_pass=False, baseline_pass=False),
            _make_item(1, harness_pass=False, baseline_pass=False),
        ]
        results = calculate_ab_summary(items)
        assert results.harness_pass_rate == 0.0
        assert results.baseline_pass_rate == 0.0
        assert results.delta == 0.0

    def test_harness_only_pass(self) -> None:
        """Harness arm passes, baseline arm fails on all items."""
        items = [
            _make_item(0, harness_pass=True, baseline_pass=False),
            _make_item(1, harness_pass=True, baseline_pass=False),
        ]
        results = calculate_ab_summary(items)
        assert results.harness_pass_rate == 1.0
        assert results.baseline_pass_rate == 0.0
        assert results.delta == 1.0

    def test_baseline_only_pass(self) -> None:
        """Baseline arm passes, harness arm fails on all items."""
        items = [
            _make_item(0, harness_pass=False, baseline_pass=True),
            _make_item(1, harness_pass=False, baseline_pass=True),
        ]
        results = calculate_ab_summary(items)
        assert results.harness_pass_rate == 0.0
        assert results.baseline_pass_rate == 1.0
        assert results.delta == -1.0

    def test_mixed_results(self) -> None:
        """Mixed results: 3/4 harness pass, 2/4 baseline pass."""
        items = [
            _make_item(0, harness_pass=True, baseline_pass=True),
            _make_item(1, harness_pass=True, baseline_pass=False),
            _make_item(2, harness_pass=True, baseline_pass=True),
            _make_item(3, harness_pass=False, baseline_pass=False),
        ]
        results = calculate_ab_summary(items)
        assert results.harness_pass_rate == 0.75
        assert results.baseline_pass_rate == 0.5
        assert results.delta == 0.25

    def test_single_item(self) -> None:
        """Single item aggregation."""
        items = [_make_item(0, harness_pass=True, baseline_pass=False)]
        results = calculate_ab_summary(items)
        assert results.harness_pass_rate == 1.0
        assert results.baseline_pass_rate == 0.0
        assert results.delta == 1.0

    def test_median_tokens_odd(self) -> None:
        """Median of odd number of token values."""
        items = [
            _make_item(0, harness_tokens=100, baseline_tokens=50),
            _make_item(1, harness_tokens=200, baseline_tokens=150),
            _make_item(2, harness_tokens=300, baseline_tokens=250),
        ]
        results = calculate_ab_summary(items)
        assert results.median_tokens_harness == 200
        assert results.median_tokens_baseline == 150

    def test_median_tokens_even(self) -> None:
        """Median of even number of token values."""
        items = [
            _make_item(0, harness_tokens=100, baseline_tokens=50),
            _make_item(1, harness_tokens=200, baseline_tokens=150),
            _make_item(2, harness_tokens=300, baseline_tokens=250),
            _make_item(3, harness_tokens=400, baseline_tokens=350),
        ]
        results = calculate_ab_summary(items)
        assert results.median_tokens_harness == 250
        assert results.median_tokens_baseline == 200

    def test_median_durations(self) -> None:
        """Median of duration values."""
        items = [
            _make_item(0, harness_duration_ms=1000, baseline_duration_ms=500),
            _make_item(1, harness_duration_ms=3000, baseline_duration_ms=1500),
            _make_item(2, harness_duration_ms=2000, baseline_duration_ms=1000),
        ]
        results = calculate_ab_summary(items)
        assert results.median_duration_harness == 2000.0
        assert results.median_duration_baseline == 1000.0


class TestABJsonIO:
    """Tests for ab.json serialization and deserialization."""

    def test_write_and_read_roundtrip(self) -> None:
        """Write ab.json and read it back — roundtrip should match."""
        items = [
            _make_item(0, harness_pass=True, baseline_pass=False),
            _make_item(1, harness_pass=True, baseline_pass=True),
        ]
        results = calculate_ab_summary(items)
        with tempfile.TemporaryDirectory() as tmpdir:
            write_ab_json(results, tmpdir)
            ab_path = Path(tmpdir) / "ab.json"
            assert ab_path.exists()

            loaded = read_ab_json(tmpdir)
            assert loaded is not None
            assert loaded.harness_pass_rate == results.harness_pass_rate
            assert loaded.baseline_pass_rate == results.baseline_pass_rate
            assert loaded.delta == results.delta
            assert loaded.median_tokens_harness == results.median_tokens_harness
            assert loaded.median_tokens_baseline == results.median_tokens_baseline
            assert loaded.median_duration_harness == results.median_duration_harness
            assert loaded.median_duration_baseline == results.median_duration_baseline
            assert len(loaded.per_item) == 2

    def test_write_creates_directory(self) -> None:
        """write_ab_json creates the run directory if it doesn't exist."""
        items = [_make_item(0)]
        results = calculate_ab_summary(items)
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "nested" / "dir"
            write_ab_json(results, str(nested))
            assert nested.exists()
            assert (nested / "ab.json").exists()

    def test_read_missing_file(self) -> None:
        """read_ab_json returns None for missing file."""
        result = read_ab_json("/nonexistent/path")
        assert result is None

    def test_read_invalid_json(self) -> None:
        """read_ab_json returns None for invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ab.json"
            path.write_text("not json")
            result = read_ab_json(tmpdir)
            assert result is None

    def test_read_partial_data(self) -> None:
        """read_ab_json handles missing summary fields gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ab.json"
            path.write_text(json.dumps({"summary": {}, "items": []}))
            result = read_ab_json(tmpdir)
            assert result is not None
            assert result.harness_pass_rate == 0.0
            assert result.per_item == []

    def test_ab_results_to_dict(self) -> None:
        """ab_results_to_dict produces the ab.json wire format."""
        items = [_make_item(0)]
        results = calculate_ab_summary(items)
        d = ab_results_to_dict(results)
        assert "summary" in d
        assert "items" in d
        assert d["summary"]["harness_pass_rate"] == 1.0
        assert len(d["items"]) == 1


class TestABSchema:
    """Tests for JSON schema generation."""

    def test_schema_is_draft07(self) -> None:
        """Schema uses JSON Schema draft-07."""
        schema = get_ab_schema()
        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"

    def test_schema_validates_against_empty_results(self) -> None:
        """Schema validates the output of ab_results_to_dict for empty results."""
        schema = get_ab_schema()
        results = calculate_ab_summary([])
        output = ab_results_to_dict(results)
        # Structural check: output should match schema's required fields
        for key in schema["required"]:
            assert key in output

    def test_schema_validates_against_real_results(self) -> None:
        """Schema validates the output of ab_results_to_dict for populated results."""
        schema = get_ab_schema()
        items = [
            _make_item(0, harness_pass=True, baseline_pass=False),
            _make_item(1, harness_pass=True, baseline_pass=True),
        ]
        results = calculate_ab_summary(items)
        output = ab_results_to_dict(results)
        for key in schema["required"]:
            assert key in output
        assert len(output["items"]) == 2
