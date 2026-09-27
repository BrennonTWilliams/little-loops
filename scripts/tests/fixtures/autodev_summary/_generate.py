"""Regenerate the autodev ``finalize_done`` golden fixtures.

These fixtures pin the behaviour of the shell action that autodev's
``finalize_done`` state ran before it was extracted into
``little_loops.autodev_summary`` (ENH: autodev_summary extraction). The legacy
action is kept verbatim in ``_legacy_finalize_done.sh`` next to this script so
the oracle survives the YAML change; ``test_autodev_summary.py`` replays every
scenario against the Python module and asserts byte-identical output.

Each scenario directory holds:

* ``scenario.json`` -- description, ``quality_gate`` value, and the raw
  frontmatter ``status`` of every issue file the scenario's project contains;
* ``inputs/`` -- the run-dir files present before finalization;
* ``expected_summary.json`` -- the exact bytes of the written summary.json;
* ``expected_stdout.txt`` -- the operator report printed to stdout;
* ``expected_exit`` -- the action's exit code;
* ``expected_ledgers.json`` -- post-run ``autodev-passed.txt`` /
  ``autodev-unverified.txt`` contents (``null`` when the file does not exist).

The legacy action resolves statuses with ``ll-issues show <ID> --json``; the
generator runs it against a throwaway project whose issue files carry the
scenario's statuses, with ``ll-issues`` shimmed to this checkout's
``little_loops.cli.issues`` so the fixture reflects the source tree rather than
whatever is installed. ``LC_ALL=C`` pins ``sort`` to byte order (the module
sorts by code point; the shell's order was locale-dependent).

Usage (from the repository root)::

    PYTHONPATH=scripts python scripts/tests/fixtures/autodev_summary/_generate.py

Existing scenario directories are overwritten; unknown ones are left alone.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCRIPTS_DIR = HERE.parents[2]
LEGACY_ACTION = HERE / "_legacy_finalize_done.sh"
QUALITY_GATE_REF = "${context.quality_gate:shell:default=true}"
LEDGERS = ("autodev-passed.txt", "autodev-unverified.txt")

_CATEGORY_DIRS = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements", "EPIC": "epics"}


def _evidence(verdict: Any, head: Any = "deadbeefcafe", dirty: Any = False) -> str:
    return json.dumps({"verdict": verdict, "head_sha": head, "dirty": dirty})


#: name -> (description, quality_gate, {ID: raw frontmatter status}, {run-dir path: content})
SCENARIOS: dict[str, tuple[str, str, dict[str, str], dict[str, str]]] = {
    # --- test_builtin_loops.py TestAutodevLoop finalize_done scenarios -------------
    "blocked_by_unmet_bucket": (
        "ENH-2909: blocked_by_unmet skips get their own bucket",
        "false",
        {},
        {
            "autodev-skipped.txt": (
                "ENH-1001  refine_failed\nBUG-2865  already_completed\n"
                "FEAT-2001  blocked_by_unmet\n"
            )
        },
    ),
    "already_resolved_bucket": (
        "ENH-2868: pre-flight already_* skips get their own bucket; infra split out",
        "false",
        {},
        {
            "autodev-skipped.txt": (
                "ENH-1001  refine_failed\nENH-1002  refine_failed_infra\n"
                "BUG-2865  already_completed\nFEAT-1003  already_deferred\n"
            )
        },
    ),
    "phantom_staged_not_closed": (
        "BUG-2908: staged but still open -> unverified, phantom, exit 1",
        "false",
        {"FEAT-108": "open"},
        {"autodev-staged.txt": "FEAT-108\n"},
    ),
    "promotes_verified_closure": (
        "BUG-2908: staged and done -> promoted, success",
        "false",
        {"FEAT-200": "done"},
        {"autodev-staged.txt": "FEAT-200\n"},
    ),
    "splits_cancelled_from_implemented": (
        "ENH-3613: mixed implemented/cancelled closure; duplicate staged line",
        "false",
        {"FEAT-1": "done", "FEAT-2": "cancelled", "BUG-1": "completed"},
        {"autodev-staged.txt": "FEAT-1\nFEAT-2\nFEAT-2\nBUG-1\n"},
    ),
    "all_implemented_no_suffix": (
        "ENH-3613: no cancelled suffix on the Passed line",
        "false",
        {"FEAT-1": "Done"},
        {"autodev-staged.txt": "FEAT-1\n"},
    ),
    "all_cancelled_no_op": (
        "ENH-3613: an all-cancelled run is no-op",
        "false",
        {"FEAT-1": "cancelled", "FEAT-2": "Cancelled"},
        {"autodev-staged.txt": "FEAT-1\nFEAT-2\n"},
    ),
    "all_cancelled_with_not_started": (
        "ENH-3613: all-cancelled plus a not-started ID -> not_started",
        "false",
        {"FEAT-1": "cancelled"},
        {"autodev-staged.txt": "FEAT-1\n", "autodev-not-started.txt": "FEAT-9  notstarted_x\n"},
    ),
    "cancelled_plus_unverified_phantom": (
        "ENH-3613: cancelled + unverified -> phantom",
        "false",
        {"FEAT-1": "cancelled", "FEAT-2": "open"},
        {"autodev-staged.txt": "FEAT-1\nFEAT-2\n"},
    ),
    "no_op_empty_gate_off": (
        "empty run dir -> no-op, completed, pending 0",
        "false",
        {},
        {},
    ),
    "rate_limited_with_pending": (
        "rate-limit stop -> rate_limited, pending listed, inflight abandoned",
        "false",
        {},
        {
            "autodev-stop-reason": "rate_limit",
            "autodev-queue.txt": "FEAT-301\nFEAT-302\n",
            "autodev-inflight": "FEAT-300",
        },
    ),
    "not_started_verdict": (
        "ENH-2989: not-started only -> not_started, excluded from Skipped",
        "false",
        {},
        {
            "autodev-not-started.txt": "FEAT-1  not_ready\n",
            "autodev-skipped.txt": "FEAT-1  notstarted_not_ready\n",
        },
    ),
    "proof_gate_infra_count": (
        "BUG-3603: proof-gate infra ledger surfaces as its own bucket",
        "false",
        {},
        {"autodev-proof-gate-infra.txt": "FEAT-701\nFEAT-702\n"},
    ),
    "mixed_run_success": (
        "success still wins over a not-started entry",
        "false",
        {"FEAT-200": "done"},
        {"autodev-staged.txt": "FEAT-200\n", "autodev-not-started.txt": "FEAT-1  not_ready\n"},
    ),
    "reasoned_unverified_not_double_counted": (
        "BUG-3390: a reasoned unverified line is not duplicated by a bare ID",
        "true",
        {"FEAT-1": "open"},
        {
            "autodev-staged.txt": "FEAT-1\n",
            "autodev-unverified.txt": "FEAT-1  impl_exit0_not_closed\n",
        },
    ),
    # --- test_feat3573_quality_gate.py TestFinalizeDonePromotion scenarios --------
    "quality_evidence_gate_pass": (
        "FEAT-3573: GATE_PASS evidence promotes a done issue",
        "true",
        {"FEAT-1": "done"},
        {"autodev-staged.txt": "FEAT-1\n", "quality/FEAT-1.json": _evidence("GATE_PASS")},
    ),
    "quality_evidence_gate_skip": (
        "FEAT-3573: GATE_SKIP evidence promotes a done issue",
        "true",
        {"FEAT-1": "done"},
        {"autodev-staged.txt": "FEAT-1\n", "quality/FEAT-1.json": _evidence("GATE_SKIP")},
    ),
    "quality_failed_not_promoted": (
        "FEAT-3573: GATE_FAILED is not promoted and is listed with sha/dirty",
        "true",
        {"FEAT-1": "done", "FEAT-2": "done"},
        {
            "autodev-staged.txt": "FEAT-1\nFEAT-2\n",
            "autodev-unverified.txt": "FEAT-2  quality_gate_failed\n",
            "quality/FEAT-1.json": _evidence("GATE_PASS"),
            "quality/FEAT-2.json": _evidence("GATE_FAILED", "0123456789ab", True),
        },
    ),
    "quality_infra_reported": (
        "FEAT-3573: GATE_INFRA reported separately; phantom",
        "true",
        {"FEAT-1": "done"},
        {
            "autodev-staged.txt": "FEAT-1\n",
            "autodev-unverified.txt": "FEAT-1  quality_gate_infra\n",
            "quality/FEAT-1.json": _evidence("GATE_INFRA"),
        },
    ),
    "quality_all_gated_failed_hint": (
        "FEAT-3573: every gated issue failed -> quality_gate=false hint",
        "true",
        {"FEAT-1": "done"},
        {
            "autodev-staged.txt": "FEAT-1\n",
            "autodev-unverified.txt": "FEAT-1  quality_gate_failed\n",
            "quality/FEAT-1.json": _evidence("GATE_FAILED"),
        },
    ),
    "quality_evidence_missing": (
        "FEAT-3573: done without evidence -> quality_evidence_missing",
        "true",
        {"FEAT-1": "done"},
        {"autodev-staged.txt": "FEAT-1\n"},
    ),
    "quality_cancelled_without_evidence": (
        "FEAT-3573: cancelled closure promoted on status alone",
        "true",
        {"FEAT-1": "cancelled"},
        {"autodev-staged.txt": "FEAT-1\n"},
    ),
    "quality_gate_off_status_only": (
        "FEAT-3573: gate off restores status-only credit",
        "false",
        {"FEAT-1": "done"},
        {"autodev-staged.txt": "FEAT-1\n"},
    ),
    "no_op_empty_gate_on": (
        "empty run dir with the gate on (summary key shape)",
        "true",
        {},
        {},
    ),
    # --- additional coverage ---------------------------------------------------
    "abandoned_inflight_phantom": (
        "BUG-2908 step 4: residual inflight sentinel -> inflight_at_finalize, phantom",
        "true",
        {},
        {"autodev-inflight": "FEAT-5\n"},
    ),
    "inflight_already_passed": (
        "inflight ID promoted this finalize -> not abandoned",
        "true",
        {"FEAT-5": "done"},
        {
            "autodev-staged.txt": "FEAT-5\n",
            "autodev-inflight": " FEAT-5 \n",
            "quality/FEAT-5.json": _evidence("GATE_PASS"),
        },
    ),
    "inflight_already_unverified": (
        "BUG-2981 D2: inflight already recorded -> abandoned but not re-appended",
        "false",
        {},
        {
            "autodev-inflight": "FEAT-5",
            "autodev-unverified.txt": "FEAT-5  impl_exit0_not_closed\n",
        },
    ),
    "kitchen_sink": (
        "every bucket populated at once, with duplicates, blank lines and a manual stop",
        "true",
        {
            "FEAT-10": "done",
            "FEAT-11": "done",
            "FEAT-12": "cancelled",
            "BUG-20": "open",
            "ENH-30": "in_progress",
        },
        {
            "autodev-staged.txt": "FEAT-10\nFEAT-11\n\nFEAT-12\nBUG-20\nENH-30\nFEAT-10\n",
            "autodev-unverified.txt": "FEAT-11  quality_gate_failed\n",
            "autodev-skipped.txt": (
                "ENH-1  refine_failed\nENH-2  refine_failed_infra\nENH-2  refine_failed_infra\n"
                "BUG-3  already_done\nBUG-4  blocked_by_unmet\nBUG-5  notstarted_x\n"
                "BUG-6  refine_failed  already_x\n\n   \nENH-1  refine_failed\n"
            ),
            "autodev-gate-blocked.txt": "FEAT-40\nFEAT-40\n\nFEAT-41\n",
            "autodev-decision-unresolved.txt": "ENH-50\n",
            "autodev-not-started.txt": "BUG-5  x\n",
            "autodev-proof-gate-infra.txt": "FEAT-60\nFEAT-60\n",
            "autodev-spike-inconclusive.txt": "ENH-70\nENH-71\nENH-70\n",
            "autodev-proposal-unsound.txt": "ENH-80\n",
            "autodev-stop-reason": "manual\n",
            "autodev-queue.txt": "FEAT-90\n\nFEAT-91\nFEAT-90\n",
            "autodev-inflight": "FEAT-99",
            "quality/FEAT-10.json": _evidence("GATE_PASS"),
            "quality/FEAT-11.json": _evidence("GATE_FAILED", "abcdef0123456789"),
        },
    ),
    "rate_limit_overrides_success": (
        "rate_limit stop reason overrides a success verdict; empty queue prints none",
        "false",
        {"FEAT-1": "done"},
        {"autodev-staged.txt": "FEAT-1\n", "autodev-stop-reason": "rate_limit\n"},
    ),
    "staged_issue_not_found": (
        "a staged ID with no issue file resolves to an empty status -> unverified",
        "false",
        {},
        {"autodev-staged.txt": "FEAT-404\n"},
    ),
    "quality_gate_uppercase_off": (
        "quality_gate value is case-folded: OFF disables the gate",
        "OFF",
        {"FEAT-1": "done"},
        {"autodev-staged.txt": "FEAT-1\n"},
    ),
    "quality_gate_empty_value": (
        "an empty quality_gate value leaves the gate on",
        "",
        {"FEAT-1": "done"},
        {"autodev-staged.txt": "FEAT-1\n"},
    ),
    "quality_evidence_malformed": (
        "malformed / odd evidence records tolerated exactly like the shell",
        "true",
        {"FEAT-6": "done", "FEAT-7": "done"},
        {
            "autodev-staged.txt": "FEAT-6\nFEAT-7\n",
            "autodev-unverified.txt": (
                "FEAT-3  quality_gate_failed\nFEAT-4  quality_gate_infra\n"
                "FEAT-5  quality_gate_failed\nFEAT-8  quality_gate_failed\n"
            ),
            "quality/FEAT-3.json": "not json",
            "quality/FEAT-4.json": "[1]",
            "quality/FEAT-5.json": _evidence("GATE_FAILED", "", False),
            "quality/FEAT-6.json": _evidence("GATE_BOGUS"),
            "quality/FEAT-7.json": "[]",
        },
    ),
    "quality_partial_gated_no_hint": (
        "one of two gated issues failed -> no all-failed hint",
        "true",
        {"FEAT-1": "done", "FEAT-2": "done"},
        {
            "autodev-staged.txt": "FEAT-1\nFEAT-2\n",
            "autodev-unverified.txt": "FEAT-2  quality_gate_failed\n",
            "quality/FEAT-1.json": _evidence("GATE_PASS"),
            "quality/FEAT-2.json": _evidence("GATE_FAILED"),
        },
    ),
    "not_started_edge_lines": (
        "not-started ledger lines with blanks, one field, and three fields",
        "false",
        {},
        {"autodev-not-started.txt": "FEAT-1  a  extra\n\nFEAT-2\nFEAT-1  a\n"},
    ),
    "pending_completed_no_stopped_line": (
        "a non-empty queue with no stop reason counts pending but prints no Stopped line",
        "false",
        {},
        {"autodev-queue.txt": "FEAT-1\nFEAT-2\n"},
    ),
    "staged_whitespace_quirks": (
        "staged lines are word-split after sort -u (trailing space / two IDs per line)",
        "false",
        {"FEAT-1": "done", "BUG-9": "cancelled"},
        {"autodev-staged.txt": "FEAT-1\nFEAT-1 \n  \nBUG-9 BUG-9\n"},
    ),
    "unverified_no_trailing_newline": (
        "appending to an unverified ledger that lacks a trailing newline",
        "false",
        {"FEAT-2": "open"},
        {
            "autodev-staged.txt": "FEAT-2\n",
            "autodev-unverified.txt": "FEAT-1  impl_exit0_not_closed",
        },
    ),
}


def make_project(root: Path, statuses: dict[str, str]) -> Path:
    """Create a minimal little-loops project whose issue files carry *statuses*."""
    project = root / "project"
    (project / ".ll").mkdir(parents=True)
    (project / ".ll" / "ll-config.json").write_text(json.dumps({"issues": {"base_dir": ".issues"}}))
    for issue_id, status in statuses.items():
        kind = issue_id.split("-", 1)[0]
        cat = project / ".issues" / _CATEGORY_DIRS[kind]
        cat.mkdir(parents=True, exist_ok=True)
        (cat / f"P3-{issue_id}-fixture.md").write_text(
            f"---\nid: {issue_id}\ntype: {kind}\ntitle: t\nstatus: {status}\n"
            f"priority: P3\n---\n\n# {issue_id}: t\n"
        )
    return project


def write_inputs(run_dir: Path, files: dict[str, str]) -> None:
    """Materialise a scenario's run-dir files under *run_dir*."""
    run_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def _ll_issues_shim(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "ll-issues"
    shim.write_text(
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -c "
        "'import sys; from little_loops.cli.issues import main_issues; "
        'sys.argv[0] = "ll-issues"; sys.exit(main_issues())\' "$@"\n'
    )
    shim.chmod(0o755)


def run_legacy(project: Path, run_dir: Path, quality_gate: str, bin_dir: Path) -> tuple[int, str]:
    """Run the verbatim legacy action; return (exit code, stdout)."""
    script = (
        LEGACY_ACTION.read_text()
        .replace("${context.run_dir}", str(run_dir))
        .replace(QUALITY_GATE_REF, shlex.quote(quality_gate))
        .replace("$${", "${")
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(SCRIPTS_DIR),
        "LC_ALL": "C",
    }
    result = subprocess.run(
        ["bash", "-c", script], cwd=project, capture_output=True, text=True, env=env
    )
    return result.returncode, result.stdout


def generate(name: str) -> None:
    """Record one scenario's fixture directory from the legacy shell action."""
    description, gate, statuses, files = SCENARIOS[name]
    out = HERE / name
    if out.exists():
        shutil.rmtree(out)
    write_inputs(out / "inputs", files)
    (out / "scenario.json").write_text(
        json.dumps(
            {"description": description, "quality_gate": gate, "statuses": statuses},
            indent=2,
        )
        + "\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project = make_project(root, statuses)
        run_dir = project / "run"
        write_inputs(run_dir, files)
        _ll_issues_shim(root / "bin")
        code, stdout = run_legacy(project, run_dir, gate, root / "bin")
        summary = run_dir / "summary.json"
        (out / "expected_summary.json").write_bytes(summary.read_bytes())
        (out / "expected_stdout.txt").write_text(stdout)
        (out / "expected_exit").write_text(f"{code}\n")
        ledgers = {
            n: (run_dir / n).read_text() if (run_dir / n).exists() else None for n in LEDGERS
        }
        (out / "expected_ledgers.json").write_text(json.dumps(ledgers, indent=2) + "\n")
    print(f"{name}: exit={code}")


def main() -> int:
    """Regenerate every scenario, or only those named on the command line."""
    names = sys.argv[1:] or list(SCENARIOS)
    for name in names:
        generate(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
