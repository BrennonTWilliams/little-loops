"""ll-loop run-completion summary printing: usage table, A/B, cross-host.

Relocated from ``cli/loop/_helpers.py`` (ENH-2776).
"""

from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path
from typing import Any


def _print_usage_summary(usage_path: Path, cost_output_json: Path | None = None) -> None:
    """Print per-state token usage summary from usage.jsonl.

    Args:
        usage_path: Path to usage.jsonl written by PersistentExecutor
        cost_output_json: Optional path to also write the stable-JSON
            report (ENH-2477). Write failures are non-fatal: a missing
            parent dir or unwritable path must not block the run's
            normal exit path.
    """
    from little_loops.fsm.cost_graph import CostReport

    if not usage_path.exists():
        return
    report = CostReport.from_usage_jsonl(usage_path)
    if not report.states:
        return

    print()
    print(report.table())

    if cost_output_json is not None:
        try:
            report.write_json(cost_output_json)
        except OSError:
            pass  # Non-fatal: a failed write shouldn't block the run


def _print_ab_summary(ab_path: Path) -> None:
    """Print A/B comparison summary from ab.json.

    Args:
        ab_path: Path to ab.json file written by the executor
    """
    from little_loops.ab_writer import read_ab_json
    from little_loops.stats import paired_direction, wilson_ci

    results = read_ab_json(str(ab_path.parent))
    if results is None or not results.per_item:
        return

    n = len(results.per_item)
    harness_pct = results.harness_pass_rate * 100
    baseline_pct = results.baseline_pass_rate * 100
    delta_pct = results.delta * 100

    k_harness = sum(1 for item in results.per_item if item.get("harness_pass", False))
    k_baseline = sum(1 for item in results.per_item if item.get("baseline_pass", False))
    h_lo, h_hi = wilson_ci(k_harness, n)
    b_lo, b_hi = wilson_ci(k_baseline, n)

    tokens_ratio = (
        results.median_tokens_harness / results.median_tokens_baseline
        if results.median_tokens_baseline > 0
        else 0
    )
    dur_ratio = (
        results.median_duration_harness / results.median_duration_baseline
        if results.median_duration_baseline > 0
        else 0
    )

    def _fmt_dur(ms: float) -> str:
        if ms < 1000:
            return f"{ms:.0f}ms"
        elif ms < 60000:
            return f"{ms / 1000:.1f}s"
        else:
            return f"{ms / 60000:.1f}m"

    tokens_dir = "+" if tokens_ratio > 1 else "-"
    dur_dir = "+" if dur_ratio > 1 else "-"

    print()
    print(f"A/B Summary (n={n})")
    print(f"  Harness pass-rate:  {harness_pct:.0f}%  [{h_lo:.2f}, {h_hi:.2f}]")
    print(f"  Baseline pass-rate: {baseline_pct:.0f}%  [{b_lo:.2f}, {b_hi:.2f}]")
    print(f"  Delta:              {delta_pct:+.0f}%")
    print()
    print(
        f"  Median tokens:      harness={results.median_tokens_harness}  "
        f"baseline={results.median_tokens_baseline}  "
        f"({tokens_dir}{abs(tokens_ratio - 1) * 100:.0f}%)"
    )
    print(
        f"  Median duration:    harness={_fmt_dur(results.median_duration_harness)}  "
        f"baseline={_fmt_dur(results.median_duration_baseline)}  "
        f"({dur_dir}{abs(dur_ratio - 1) * 100:.0f}%)"
    )

    # Verdict line — paired sign test on discordant items (ENH-3298); the raw
    # delta sign asserts a winner even when the two Wilson CIs overlap almost
    # entirely, so the direction must instead be established by the CI on
    # the discordant split itself.
    direction, b, c = paired_direction(results.per_item)
    discordant = b + c
    if direction == "inconclusive":
        quality_verdict = f"inconclusive at n={n} ({discordant} discordant pairs)"
    else:
        favor = b if direction == "harness" else c
        quality_verdict = (
            f"{direction} wins on quality ({favor}/{discordant} discordant pairs favor {direction})"
        )
    cost_verdict = (
        f"costs ~{abs(tokens_ratio - 1) * 100:.0f}% more tokens"
        if tokens_ratio > 1
        else (
            f"costs ~{abs(tokens_ratio - 1) * 100:.0f}% fewer tokens"
            if tokens_ratio < 1
            else "same token cost"
        )
    )
    print(f"  Verdict:            {quality_verdict}, {cost_verdict}")
    print()
    print(f"Per-item: {ab_path}")


def _run_cross_host_validation(
    args: argparse.Namespace,
    loop_path: Path | None,
    primary_run_dir: Path,
    primary_ab_path: Path,
    loop_name: str,
) -> None:
    """Re-run the loop on a second available host and print a cross-host comparison.

    Identifies a second host via _PROBE_ORDER, runs the same baseline trial with
    LL_HOST_CLI overridden, then calls _print_cross_host_table if both ab.json
    files are available.
    """
    import shutil

    from little_loops.host_runner import (
        _PROBE_ORDER,
        HostNotConfigured,
        project_child_env,
        resolve_host,
    )

    # Identify the current (primary) host
    try:
        primary_host = resolve_host().name
    except HostNotConfigured:
        primary_host = None

    # Find a second available host different from the primary
    second_host: str | None = None
    for host_name, binary in _PROBE_ORDER:
        if host_name == primary_host:
            continue
        if shutil.which(binary) is not None:
            second_host = host_name
            break

    if second_host is None:
        print("\nCross-host: only one host available — skipping cross-host validation.")
        return

    print(f"\nCross-host: running {loop_name!r} on {second_host}...")

    # Build the second-host command
    cmd = ["ll-loop", "run", "--baseline"]
    baseline_skill = getattr(args, "baseline_skill", None)
    if baseline_skill is not None:
        cmd.extend(["--baseline-skill", baseline_skill])
    items = getattr(args, "items", None)
    if items is not None:
        cmd.extend(["--items", str(items)])
    cmd.append(loop_name)

    env = project_child_env(extra={"LL_HOST_CLI": second_host})

    before = time.time()
    result = subprocess.run(cmd, env=env)

    if result.returncode != 0:
        print(
            f"\nCross-host: second-host run ({second_host}) failed "
            f"(exit {result.returncode}) — no comparison available."
        )
        return

    # Find the second run's ab.json: newest file under the same runs directory
    # that appeared after the second run started and differs from the primary.
    runs_dir = primary_run_dir.parent
    candidates = sorted(
        runs_dir.glob("*/ab.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    second_ab_path = next(
        (p for p in candidates if p != primary_ab_path and p.stat().st_mtime >= before),
        None,
    )

    if second_ab_path is None:
        print(
            "\nCross-host: second-host run completed but no ab.json found — "
            "no comparison available."
        )
        return

    from little_loops.ab_writer import read_ab_json

    primary_results = read_ab_json(str(primary_run_dir))
    second_results = read_ab_json(str(second_ab_path.parent))

    if primary_results is None or second_results is None:
        return

    _print_cross_host_table(primary_host or "primary", primary_results, second_host, second_results)


def _print_cross_host_table(
    host1: str,
    results1: Any,
    host2: str,
    results2: Any,
) -> None:
    """Print a cross-host pass-rate comparison table with Wilson 95% CIs."""
    from little_loops.stats import paired_direction, wilson_ci

    def _host_stats(results: Any) -> tuple[int, int, float, float, float]:
        n = len(results.per_item)
        k = sum(1 for item in results.per_item if item.get("harness_pass", False))
        rate = results.harness_pass_rate * 100
        lo, hi = wilson_ci(k, n) if n > 0 else (0.0, 0.0)
        return n, k, rate, lo, hi

    n1, _k1, rate1, lo1, hi1 = _host_stats(results1)
    n2, _k2, rate2, lo2, hi2 = _host_stats(results2)

    print()
    print("Cross-host Comparison")
    print(f"  {'Host':<20}  {'Pass rate':>10}  {'95% CI':>18}  {'n':>5}")
    print(f"  {'-' * 20}  {'-' * 10}  {'-' * 18}  {'-' * 5}")
    print(f"  {host1:<20}  {rate1:>9.0f}%  [{lo1:.2f}, {hi1:.2f}]  {n1:>5}")
    print(f"  {host2:<20}  {rate2:>9.0f}%  [{lo2:.2f}, {hi2:.2f}]  {n2:>5}")

    # Warn on ordering reversal only when both runs independently establish a
    # direction (ENH-3298) — otherwise a noisy disagreement between two
    # inconclusive runs prints identically to a genuine host-specific effect.
    direction1, _b1, _c1 = paired_direction(results1.per_item)
    direction2, _b2, _c2 = paired_direction(results2.per_item)
    print()
    if direction1 != "inconclusive" and direction2 != "inconclusive" and direction1 != direction2:
        print(
            f"  ⚠ Ordering reversal: {host1} shows {direction1} ahead, "
            f"{host2} shows {direction2} ahead. "
            "Improvement may be host-specific."
        )
    elif direction1 != direction2:
        print(
            f"  Note: ordering differs between hosts, but neither run separates from "
            f"chance (n={n1}, n={n2}) — not evidence of a host-specific effect."
        )
    print()
