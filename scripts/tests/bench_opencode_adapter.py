"""Benchmark: OpenCode adapter cold-start latency for hook intents.

Measures end-to-end latency for Bun.spawn → python interpreter cold start →
handler → exit across 100 sequential invocations of each intent. Reports
min / median / p95 / max in milliseconds.

Decision rule (from hooks/adapters/opencode/README.md):
  - Target: p95 ≤ 200ms
  - If p95 ≥ 400ms: a persistent sidecar must be proposed before hot-path
    intents (tool.execute.before / tool.execute.after) are wired.

Usage:
    python scripts/tests/bench_opencode_adapter.py
    python scripts/tests/bench_opencode_adapter.py --intents session_start pre_compact
    python scripts/tests/bench_opencode_adapter.py --iterations 50

Run from the project root with `bun install` already complete in
hooks/adapters/opencode/. Skipped automatically if Bun is not on PATH.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path


_ADAPTER_DIR = Path(__file__).parent.parent.parent / "hooks" / "adapters" / "opencode"
_DEFAULT_ITERATIONS = 100
_DECISION_TARGET_MS = 200
_DECISION_THRESHOLD_MS = 400


_PAYLOADS: dict[str, dict] = {
    "session_start": {
        "session_id": "bench-session",
        "cwd": str(Path.cwd()),
        "model": "gpt-4o",
        "source": "startup",
    },
    "pre_compact": {
        "session_id": "bench-session",
        "cwd": str(Path.cwd()),
        "transcript_path": "/dev/null",
    },
}


def _run_one(intent: str, payload: dict, cwd: Path) -> float:
    """Invoke one round-trip via Bun and return wall-clock ms."""
    start = time.perf_counter()
    proc = subprocess.run(
        ["bun", str(_ADAPTER_DIR / "index.ts")],
        input=json.dumps({"event": intent, "payload": payload}),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={
            **__import__("os").environ,
            "LL_HOOK_HOST": "opencode",
            "_LL_BENCH_INTENT": intent,
        },
        timeout=10,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    if proc.returncode not in (0, 2):
        # exit 2 is the pre_compact "block + feedback" success path
        print(f"  warn: intent={intent} exit={proc.returncode} stderr={proc.stderr[:200]!r}",
              file=sys.stderr)
    return elapsed_ms


def _percentile(data: list[float], p: float) -> float:
    idx = max(0, min(len(data) - 1, int(len(data) * p / 100 + 0.5) - 1))
    return sorted(data)[idx]


def _bench_intent(intent: str, payload: dict, iterations: int) -> dict[str, float]:
    samples: list[float] = []
    for i in range(iterations):
        print(f"  {intent} [{i + 1}/{iterations}]\r", end="", flush=True)
        try:
            ms = _run_one(intent, payload, Path.cwd())
        except subprocess.TimeoutExpired:
            print(f"\n  error: timeout on iteration {i + 1}", file=sys.stderr)
            continue
        samples.append(ms)
    print()
    if not samples:
        return {}
    return {
        "min": min(samples),
        "median": statistics.median(samples),
        "p95": _percentile(samples, 95),
        "max": max(samples),
        "n": len(samples),
    }


def _print_table(results: dict[str, dict[str, float]]) -> None:
    print(f"\n{'Intent':<24} {'min':>8} {'median':>8} {'p95':>8} {'max':>8} {'n':>6}")
    print("-" * 62)
    for intent, stats in results.items():
        if not stats:
            print(f"  {intent:<22} (no samples)")
            continue
        print(
            f"  {intent:<22}"
            f" {stats['min']:>7.1f}ms"
            f" {stats['median']:>7.1f}ms"
            f" {stats['p95']:>7.1f}ms"
            f" {stats['max']:>7.1f}ms"
            f" {stats['n']:>5}"
        )


def _print_decision(results: dict[str, dict[str, float]]) -> None:
    worst_p95 = max(
        (s["p95"] for s in results.values() if s),
        default=0.0,
    )
    print()
    if worst_p95 == 0:
        print("DECISION: no data collected — cannot evaluate latency gate")
        return
    if worst_p95 <= _DECISION_TARGET_MS:
        print(f"DECISION: p95={worst_p95:.0f}ms ≤ {_DECISION_TARGET_MS}ms target — "
              f"cold-start is acceptable; opt-in-only approach viable for pre_tool_use")
    elif worst_p95 >= _DECISION_THRESHOLD_MS:
        print(f"DECISION: p95={worst_p95:.0f}ms ≥ {_DECISION_THRESHOLD_MS}ms threshold — "
              f"sidecar required before wiring pre_tool_use / post_tool_use (FEAT-1488 rule)")
    else:
        print(f"DECISION: p95={worst_p95:.0f}ms — between target ({_DECISION_TARGET_MS}ms) "
              f"and threshold ({_DECISION_THRESHOLD_MS}ms); opt-in-only viable with "
              f"documented latency cost (~{worst_p95:.0f}ms per tool call)")
    print(f"  Record this p95 in hooks/adapters/opencode/README.md ## Latency Target")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--intents",
        nargs="+",
        default=list(_PAYLOADS),
        choices=list(_PAYLOADS),
        help="Intents to benchmark (default: all)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=_DEFAULT_ITERATIONS,
        help=f"Invocations per intent (default: {_DEFAULT_ITERATIONS})",
    )
    args = parser.parse_args()

    if not shutil.which("bun"):
        print("SKIP: bun not found on PATH", file=sys.stderr)
        return 0

    if not (_ADAPTER_DIR / "node_modules").exists():
        print(
            f"SKIP: bun install not complete in {_ADAPTER_DIR}. "
            "Run `bun install` there first.",
            file=sys.stderr,
        )
        return 0

    print(f"Benchmarking OpenCode adapter — {args.iterations} iterations per intent")
    print(f"Adapter: {_ADAPTER_DIR / 'index.ts'}")
    print()

    results: dict[str, dict[str, float]] = {}
    for intent in args.intents:
        print(f"  Benchmarking {intent}...")
        results[intent] = _bench_intent(intent, _PAYLOADS[intent], args.iterations)

    _print_table(results)
    _print_decision(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
