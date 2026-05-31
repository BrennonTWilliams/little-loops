"""A/B baseline results aggregation and ab.json writer.

Provides the ABResults dataclass, summary calculation, and JSON schema
generation for the A/B baseline comparison feature (FEAT-1790).
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# JSON Schema for ab.json (draft-07)
# ---------------------------------------------------------------------------

_AB_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "little-loops://ab-results.json",
    "title": "A/B Baseline Comparison Results",
    "description": "Per-item and summary results from blind A/B baseline comparison.",
    "type": "object",
    "required": ["summary", "items"],
    "properties": {
        "summary": {
            "type": "object",
            "required": [
                "harness_pass_rate",
                "baseline_pass_rate",
                "delta",
                "median_tokens_harness",
                "median_tokens_baseline",
                "median_duration_harness",
                "median_duration_baseline",
            ],
            "properties": {
                "harness_pass_rate": {
                    "type": "number",
                    "description": "Harness arm pass rate (0-1)",
                },
                "baseline_pass_rate": {
                    "type": "number",
                    "description": "Baseline arm pass rate (0-1)",
                },
                "delta": {
                    "type": "number",
                    "description": "Pass-rate delta (harness - baseline)",
                },
                "median_tokens_harness": {
                    "type": "integer",
                    "description": "Median token count for harness arm",
                },
                "median_tokens_baseline": {
                    "type": "integer",
                    "description": "Median token count for baseline arm",
                },
                "median_duration_harness": {
                    "type": "number",
                    "description": "Median duration (ms) for harness arm",
                },
                "median_duration_baseline": {
                    "type": "number",
                    "description": "Median duration (ms) for baseline arm",
                },
            },
            "additionalProperties": False,
        },
        "items": {
            "type": "array",
            "description": "Per-item blind comparison records",
            "items": {
                "type": "object",
                "required": [
                    "index",
                    "harness_pass",
                    "baseline_pass",
                    "harness_tokens",
                    "baseline_tokens",
                    "harness_duration_ms",
                    "baseline_duration_ms",
                ],
                "properties": {
                    "index": {"type": "integer", "description": "Zero-based item index"},
                    "harness_pass": {
                        "type": "boolean",
                        "description": "Whether harness arm passed evaluation",
                    },
                    "baseline_pass": {
                        "type": "boolean",
                        "description": "Whether baseline arm passed evaluation",
                    },
                    "harness_tokens": {
                        "type": "integer",
                        "description": "Token count for harness arm",
                    },
                    "baseline_tokens": {
                        "type": "integer",
                        "description": "Token count for baseline arm",
                    },
                    "harness_duration_ms": {
                        "type": "integer",
                        "description": "Duration (ms) for harness arm",
                    },
                    "baseline_duration_ms": {
                        "type": "integer",
                        "description": "Duration (ms) for baseline arm",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Judge confidence (0-1)",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Judge reasoning for verdicts",
                    },
                },
                "additionalProperties": True,
            },
        },
    },
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ABResults:
    """Aggregated A/B comparison results.

    Attributes:
        harness_pass_rate: Fraction of items where harness arm passed (0-1)
        baseline_pass_rate: Fraction of items where baseline arm passed (0-1)
        delta: Pass-rate difference (harness - baseline)
        median_tokens_harness: Median token count for harness arm
        median_tokens_baseline: Median token count for baseline arm
        median_duration_harness: Median duration (ms) for harness arm
        median_duration_baseline: Median duration (ms) for baseline arm
        per_item: List of per-item comparison records
    """

    harness_pass_rate: float
    baseline_pass_rate: float
    delta: float
    median_tokens_harness: int
    median_tokens_baseline: int
    median_duration_harness: float
    median_duration_baseline: float
    per_item: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def calculate_ab_summary(per_item_results: list[dict[str, Any]]) -> ABResults:
    """Aggregate per-item verdicts into summary statistics.

    Args:
        per_item_results: List of per-item dicts, each with keys:
            harness_pass, baseline_pass, harness_tokens, baseline_tokens,
            harness_duration_ms, baseline_duration_ms

    Returns:
        ABResults with computed aggregate statistics
    """
    if not per_item_results:
        return ABResults(
            harness_pass_rate=0.0,
            baseline_pass_rate=0.0,
            delta=0.0,
            median_tokens_harness=0,
            median_tokens_baseline=0,
            median_duration_harness=0.0,
            median_duration_baseline=0.0,
            per_item=[],
        )

    n = len(per_item_results)
    harness_passes = sum(1 for item in per_item_results if item.get("harness_pass", False))
    baseline_passes = sum(1 for item in per_item_results if item.get("baseline_pass", False))

    harness_tokens = [item.get("harness_tokens", 0) for item in per_item_results]
    baseline_tokens = [item.get("baseline_tokens", 0) for item in per_item_results]
    harness_durations = [item.get("harness_duration_ms", 0) for item in per_item_results]
    baseline_durations = [item.get("baseline_duration_ms", 0) for item in per_item_results]

    return ABResults(
        harness_pass_rate=harness_passes / n,
        baseline_pass_rate=baseline_passes / n,
        delta=(harness_passes - baseline_passes) / n,
        median_tokens_harness=int(statistics.median(harness_tokens)),
        median_tokens_baseline=int(statistics.median(baseline_tokens)),
        median_duration_harness=float(statistics.median(harness_durations)),
        median_duration_baseline=float(statistics.median(baseline_durations)),
        per_item=per_item_results,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def ab_results_to_dict(results: ABResults) -> dict[str, Any]:
    """Serialize ABResults to the ab.json wire format.

    Args:
        results: Aggregated A/B results

    Returns:
        Dict matching the ab.json schema
    """
    return {
        "summary": {
            "harness_pass_rate": results.harness_pass_rate,
            "baseline_pass_rate": results.baseline_pass_rate,
            "delta": results.delta,
            "median_tokens_harness": results.median_tokens_harness,
            "median_tokens_baseline": results.median_tokens_baseline,
            "median_duration_harness": results.median_duration_harness,
            "median_duration_baseline": results.median_duration_baseline,
        },
        "items": results.per_item,
    }


def write_ab_json(results: ABResults, run_dir: str) -> None:
    """Write ab.json to the run directory.

    Args:
        results: Aggregated A/B results to serialize
        run_dir: Target directory (created if missing)
    """
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    path = Path(run_dir) / "ab.json"
    path.write_text(json.dumps(ab_results_to_dict(results), indent=2))


def read_ab_json(run_dir: str) -> ABResults | None:
    """Read ab.json from a run directory.

    Args:
        run_dir: Directory containing ab.json

    Returns:
        ABResults if file exists and is valid, None otherwise
    """
    path = Path(run_dir) / "ab.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    summary = data.get("summary", {})
    items = data.get("items", [])
    return ABResults(
        harness_pass_rate=summary.get("harness_pass_rate", 0.0),
        baseline_pass_rate=summary.get("baseline_pass_rate", 0.0),
        delta=summary.get("delta", 0.0),
        median_tokens_harness=summary.get("median_tokens_harness", 0),
        median_tokens_baseline=summary.get("median_tokens_baseline", 0),
        median_duration_harness=summary.get("median_duration_harness", 0.0),
        median_duration_baseline=summary.get("median_duration_baseline", 0.0),
        per_item=items,
    )


def get_ab_schema() -> dict[str, Any]:
    """Return the ab.json JSON Schema (draft-07)."""
    return _AB_SCHEMA
