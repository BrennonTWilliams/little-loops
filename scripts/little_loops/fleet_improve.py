"""Helpers for the ``fleet-loop-improve`` built-in meta-loop.

The loop (``loops/fleet-loop-improve.yaml``) automates the cycle documented in
``docs/runbooks/FLEET_LOOP_REVIEW.md``::

    harvest -> measure-externally -> select -> diagnose -> propose -> apply -> gate -> commit

Every state that needs logic calls ``python3 -m little_loops.fleet_improve
<subcommand>`` so the YAML stays thin, the logic is unit-testable, and no
untrusted value ever has to be interpolated into a shell body: states hand
values to each other through ``<run-dir>/target.json``.

RE-MEASURE cannot happen inside one run — the fleet's success rate only
moves after other projects accumulate fresh runs on a fix. So each run first
``measure``s the fixes recorded by earlier runs, then performs one new cycle
and records it as ``pending`` in a durable ledger
(``.loops/diagnostics/fleet-loop-improve-ledger.jsonl``) for the *next* run
to measure. ``.loops/diagnostics/`` is the runbook's own home for
``fleet-review-<stamp>.json`` sidecars and the ``loop-specialist`` agent's
diagnosis artifacts, so the ledger lives beside them.

Exit-code contract (mirrors the loop's routes): ``0`` = yes, ``1`` = the
documented "no" verdict (nothing to select, gate failed), ``2`` = malformed
input or a tool failure, which the loop routes via ``on_error``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from little_loops.cli.logs import _builtin_loop_paths, is_flagged
from little_loops.fsm.loop_paths import get_builtin_loops_dir

DEFAULT_LEDGER = Path(".loops/diagnostics/fleet-loop-improve-ledger.jsonl")
DIAGNOSTICS_DIR = Path(".loops/diagnostics")

#: Required headings of a ``loop-specialist`` diagnosis artifact
#: (``agents/loop-specialist.md`` § Diagnosis artifact).
ARTIFACT_SECTIONS: tuple[str, ...] = (
    "## Failure modes observed",
    "## Evidence",
    "## Intended contract",
    "## Proposed change",
    "## Verification",
    "## Open questions",
)

#: ``Verdict:`` values the ``propose`` state may end its artifact with, and
#: the single token ``check-proposal`` prints for each. The loop routes on
#: these tokens with ``output_contains``.
VERDICT_TOKENS: dict[str, str] = {
    "fix": "VERDICT_FIX",
    "not-a-loop-bug": "VERDICT_NOT_A_LOOP_BUG",
    "needs-human": "VERDICT_NEEDS_HUMAN",
}
_VERDICT_RE = re.compile(r"^Verdict:\s*(fix|not-a-loop-bug|needs-human)\s*$", re.MULTILINE)

#: Ledger statuses that make a loop ineligible for re-selection until
#: ``--dismiss-ttl-days`` have elapsed. ``rejected`` is included so a fix that
#: failed the gate is not re-attempted in the very same run.
SKIP_TTL_STATUSES: frozenset[str] = frozenset({"dismissed", "needs-human", "rejected"})

#: Subcommand exit codes.
EXIT_YES = 0
EXIT_NO = 1
EXIT_ERROR = 2

_SIDECAR_STAMP_RE = re.compile(r"fleet-review-(\d{8}T\d{6}Z)\.json$")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class FleetImproveError(Exception):
    """Malformed input or a failed tool invocation (exit ``2``)."""


# --------------------------------------------------------------------------- #
# Small shared helpers
# --------------------------------------------------------------------------- #


def utc_now() -> datetime:
    """Current UTC time (patched in tests)."""
    return datetime.now(UTC)


def utc_stamp(now: datetime | None = None) -> str:
    """``YYYYMMDDTHHMMSSZ`` — the stamp format shared with ``fleet-review`` sidecars."""
    return (now or utc_now()).strftime("%Y%m%dT%H%M%SZ")


def _run(
    cmd: list[str], *, cwd: Path | None = None, timeout: int = 300
) -> subprocess.CompletedProcess[str]:
    """Run ``cmd`` capturing text output; never raises on a non-zero exit."""
    env = dict(os.environ)
    # LL_AUTOMATION inherits into every descendant of a loop run and makes a
    # handful of tests behave differently; the gate's pytest must see the
    # same environment a developer's shell would.
    env.pop("LL_AUTOMATION", None)
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except FileNotFoundError as e:
        raise FleetImproveError(f"command not found: {cmd[0]} ({e})") from e
    except subprocess.TimeoutExpired as e:
        raise FleetImproveError(f"timed out after {timeout}s: {' '.join(cmd)}") from e


def _parse_json_or_none(text: str) -> Any | None:
    """Parse ``text`` as JSON, returning ``None`` when it is not JSON."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def load_sidecar(path: Path) -> dict[str, Any]:
    """Load a ``fleet-review`` JSON sidecar, validating its top-level shape."""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise FleetImproveError(f"cannot read sidecar {path}: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("loops"), dict):
        raise FleetImproveError(f"sidecar {path} has no 'loops' mapping")
    return data


def sidecar_stamp(path: Path, sidecar: dict[str, Any]) -> str:
    """Harvest stamp: from the sidecar filename, else its ``generated`` field."""
    m = _SIDECAR_STAMP_RE.search(path.name)
    if m:
        return m.group(1)
    generated = sidecar.get("generated")
    if isinstance(generated, str):
        try:
            return utc_stamp(datetime.fromisoformat(generated))
        except ValueError:
            pass
    return "unknown"


def load_target(run_dir: Path) -> dict[str, Any]:
    """Load ``<run-dir>/target.json`` written by ``select``."""
    path = run_dir / "target.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise FleetImproveError(f"cannot read {path}: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("loop"), str):
        raise FleetImproveError(f"{path} is not a target record")
    return data


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #


def read_ledger(path: Path) -> list[dict[str, Any]]:
    """Read every entry of the JSONL ledger (missing file = empty ledger)."""
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            raise FleetImproveError(f"{path}:{lineno}: malformed ledger line: {e}") from e
        if not isinstance(entry, dict) or not isinstance(entry.get("loop"), str):
            raise FleetImproveError(f"{path}:{lineno}: ledger line has no 'loop'")
        entries.append(entry)
    return entries


def latest_by_loop(entries: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Latest ledger line per loop wins (file order is chronological)."""
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        latest[entry["loop"]] = entry
    return latest


def append_ledger(path: Path, entry: dict[str, Any]) -> None:
    """Append one entry to the ledger, creating the directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def _parse_recorded_at(entry: dict[str, Any]) -> datetime | None:
    value = entry.get("recorded_at")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


# --------------------------------------------------------------------------- #
# select
# --------------------------------------------------------------------------- #


def flagged_loops(
    sidecar: dict[str, Any], *, threshold: int, min_runs: int
) -> list[tuple[str, dict[str, Any]]]:
    """``(name, record)`` pairs from ``sidecar['loops']`` that fail the flagging rule.

    The sidecar's ``loops`` mapping is builtin-attribution only (shadowed and
    custom runs never enter it), so ``is_flagged`` needs no attribution check.
    """
    out: list[tuple[str, dict[str, Any]]] = []
    for name, rec in sidecar["loops"].items():
        if not isinstance(rec, dict):
            continue
        try:
            hit = is_flagged(
                int(rec["runs"]),
                int(rec["success_pct"]),
                str(rec["top_outcome"]),
                threshold=threshold,
                min_runs=min_runs,
            )
        except (KeyError, TypeError, ValueError) as e:
            raise FleetImproveError(f"sidecar loop {name!r} is malformed: {e}") from e
        if hit:
            out.append((name, rec))
    return out


def skip_reason(
    latest: dict[str, dict[str, Any]], loop: str, *, now: datetime, ttl_days: int
) -> str | None:
    """Why ``loop`` must not be selected now, or ``None`` if it is eligible."""
    entry = latest.get(loop)
    if entry is None:
        return None
    status = entry.get("status")
    if status == "pending":
        return "pending re-measure"
    if status in SKIP_TTL_STATUSES:
        recorded = _parse_recorded_at(entry)
        if recorded is not None and now - recorded < timedelta(days=ttl_days):
            return f"{status} on {recorded.date().isoformat()} (ttl {ttl_days}d)"
    return None


def read_fixes_count(run_dir: Path) -> int:
    """Number of ``pending`` fixes recorded during this run."""
    path = run_dir / "fixes.count"
    try:
        return int(path.read_text().strip() or "0")
    except (OSError, ValueError):
        return 0


def yaml_is_dirty(path: Path, runner: Runner = _run) -> bool:
    """True when ``git status --porcelain -- <path>`` reports any change (staged or not)."""
    proc = runner(["git", "status", "--porcelain", "--", str(path)], cwd=Path.cwd(), timeout=30)
    return bool(proc.stdout.strip())


def select_target(
    sidecar: dict[str, Any],
    sidecar_path: Path,
    ledger_entries: list[dict[str, Any]],
    *,
    threshold: int,
    min_runs: int,
    dismiss_ttl_days: int,
    now: datetime,
    builtin_paths: dict[str, Path],
    log: Callable[[str], None] = lambda _msg: None,
    is_dirty: Callable[[Path], bool] | None = None,
) -> dict[str, Any] | None:
    """Pick the flagged loop with the most fleet evidence that is eligible for a cycle.

    A candidate whose built-in YAML has uncommitted changes is skipped rather
    than aborting the run: ``gate`` (``git diff --quiet``), ``revert``
    (``git restore``) and ``commit`` (``git add``) all operate on that one file
    and need it clean. This per-target check replaces the loop's former
    dir-wide ``preflight`` guard, which blocked every run while any other
    loop in the package was being authored.
    """
    if is_dirty is None:
        is_dirty = yaml_is_dirty
    latest = latest_by_loop(ledger_entries)
    candidates = flagged_loops(sidecar, threshold=threshold, min_runs=min_runs)
    candidates.sort(key=lambda item: (-int(item[1]["runs"]), item[0]))
    for name, rec in candidates:
        reason = skip_reason(latest, name, now=now, ttl_days=dismiss_ttl_days)
        if reason:
            log(f"skip {name}: {reason}")
            continue
        yaml_path = builtin_paths.get(name)
        if yaml_path is None:
            log(f"skip {name}: no built-in YAML found for this stem")
            continue
        if is_dirty(yaml_path):
            log(f"skip {name}: built-in YAML has uncommitted changes ({yaml_path})")
            continue
        stamp = utc_stamp(now)
        return {
            "loop": name,
            "projects": list(rec.get("projects", [])),
            "runs": int(rec["runs"]),
            "converged": int(rec.get("converged", 0)),
            "success_pct": int(rec["success_pct"]),
            "top_outcome": str(rec["top_outcome"]),
            "outcomes": dict(rec.get("outcomes", {})),
            "yaml_path": str(yaml_path),
            "tests_dir": str(get_builtin_loops_dir().parent.parent / "tests"),
            "artifact": str(DIAGNOSTICS_DIR / f"{name}-{stamp}.md"),
            "stamp": stamp,
            "harvest_stamp": sidecar_stamp(sidecar_path, sidecar),
            "sidecar": str(sidecar_path),
            "baseline": {
                "runs": int(rec["runs"]),
                "converged": int(rec.get("converged", 0)),
                "success_pct": int(rec["success_pct"]),
                "top_outcome": str(rec["top_outcome"]),
                "window_days": sidecar.get("window_days"),
                "excluded_projects": sorted(sidecar.get("excluded_projects", [])),
            },
        }
    return None


def cmd_select(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    fixes_done = read_fixes_count(run_dir)
    if fixes_done >= args.max_fixes:
        print(f"max fixes per run reached ({fixes_done}/{args.max_fixes})")
        return EXIT_NO
    sidecar = load_sidecar(args.sidecar)
    target = select_target(
        sidecar,
        args.sidecar,
        read_ledger(args.ledger),
        threshold=args.threshold,
        min_runs=args.min_runs,
        dismiss_ttl_days=args.dismiss_ttl_days,
        now=utc_now(),
        builtin_paths=_builtin_loop_paths(),
        log=lambda msg: print(msg, file=sys.stderr),
    )
    if target is None:
        print("no eligible flagged loop")
        return EXIT_NO
    (run_dir / "target.json").write_text(json.dumps(target, indent=2, sort_keys=True) + "\n")
    print(json.dumps(target, sort_keys=True))
    return EXIT_YES


# --------------------------------------------------------------------------- #
# diagnose
# --------------------------------------------------------------------------- #


def _tool_report(cmd: list[str], project: Path, runner: Runner) -> str:
    """Run one read-only ``ll-loop`` subcommand inside ``project`` and render its output."""
    proc = runner(cmd, cwd=project, timeout=120)
    parsed = _parse_json_or_none(proc.stdout)
    header = f"`{' '.join(cmd)}` (exit {proc.returncode})"
    if parsed is not None:
        return f"{header}\n\n```json\n{json.dumps(parsed, indent=2, sort_keys=True)}\n```\n"
    # Plain text means "No history" / "Insufficient history" — evidence, not an error.
    body = (proc.stdout.strip() or proc.stderr.strip()) or "(no output)"
    return f"{header}\n\n```\n{body}\n```\n"


def validate_loop(yaml_path: Path, runner: Runner) -> tuple[dict[str, Any], str]:
    """``ll-loop validate <yaml_path> --json`` → (parsed report, raw stdout)."""
    proc = runner(["ll-loop", "validate", str(yaml_path), "--json"], cwd=Path.cwd(), timeout=120)
    parsed = _parse_json_or_none(proc.stdout)
    if not isinstance(parsed, dict) or "violations" not in parsed:
        raise FleetImproveError(
            f"ll-loop validate did not return JSON (exit {proc.returncode}): "
            f"{proc.stdout.strip() or proc.stderr.strip()}"
        )
    return parsed, proc.stdout


def warning_count(report: dict[str, Any]) -> int:
    """Number of ``warning``-severity violations in a ``validate --json`` report."""
    return sum(
        1
        for v in report.get("violations", [])
        if isinstance(v, dict) and v.get("severity") == "warning"
    )


def git_head(runner: Runner) -> str:
    proc = runner(["git", "rev-parse", "HEAD"], cwd=Path.cwd(), timeout=30)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def diagnose(target: dict[str, Any], run_dir: Path, runner: Runner = _run) -> Path:
    """Build the per-loop dossier and the gate baseline for ``target``.

    ``diagnose-evaluators``/``calibrate-budget`` only read the *current*
    project's ``.loops/.history`` and have no ``--project`` flag (FEAT-2379
    Decisions #5), so each is run with ``cwd=<project>``. ``--min-runs 2``
    is required: the default of 10 prints plain "Insufficient history" text
    for almost every single project, which is still recorded as evidence.
    """
    loop = target["loop"]
    yaml_path = Path(target["yaml_path"])
    lines = [
        f"# Diagnosis dossier: {loop}",
        "",
        f"Harvest: `{target.get('sidecar', '')}` (stamp {target.get('harvest_stamp', '')})",
        "",
        "## Fleet aggregate",
        "",
        f"- runs: {target['runs']}",
        f"- converged: {target['converged']}",
        f"- success_pct: {target['success_pct']}",
        f"- top_outcome: {target['top_outcome']}",
        f"- outcomes: {json.dumps(target.get('outcomes', {}), sort_keys=True)}",
        f"- built-in YAML: `{yaml_path}`",
        "",
        "## Per-project evaluator variance",
        "",
    ]
    for project_str in target.get("projects", []):
        project = Path(project_str)
        lines.append(f"### {project}")
        lines.append("")
        if not project.is_dir():
            lines.append("_project directory missing — history unavailable_")
            lines.append("")
            continue
        for sub in ("diagnose-evaluators", "calibrate-budget"):
            cmd = ["ll-loop", sub, loop, "--json", "--min-runs", "2"]
            lines.append(_tool_report(cmd, project, runner))
    report, raw = validate_loop(yaml_path, runner)
    warnings = warning_count(report)
    lines += [
        "## Validation (pre-fix)",
        "",
        f"valid: {report.get('valid')}  warnings: {warnings}",
        "",
        "```json",
        raw.strip(),
        "```",
        "",
    ]
    diag_dir = run_dir / "diagnose"
    diag_dir.mkdir(parents=True, exist_ok=True)
    dossier = diag_dir / f"{loop}.md"
    dossier.write_text("\n".join(lines))
    baseline = {"head": git_head(runner), "warnings": warnings, "valid": report.get("valid")}
    (run_dir / "gate-baseline.json").write_text(json.dumps(baseline, indent=2) + "\n")
    return dossier


def cmd_diagnose(args: argparse.Namespace) -> int:
    target = load_target(args.run_dir)
    dossier = diagnose(target, args.run_dir)
    print(str(dossier))
    return EXIT_YES


# --------------------------------------------------------------------------- #
# measure (the "measure-externally" arrow, closed one run late)
# --------------------------------------------------------------------------- #


def comparable(baseline: dict[str, Any], sidecar: dict[str, Any]) -> bool:
    """Runbook comparability: same window and same excluded-project set.

    ``since``/``until`` are absolute timestamps that differ on every
    ``--window-days`` run, and ``projects_scanned`` legitimately grows as new
    projects appear, so neither is compared.
    """
    return baseline.get("window_days") == sidecar.get("window_days") and sorted(
        baseline.get("excluded_projects", [])
    ) == sorted(sidecar.get("excluded_projects", []))


def measure_entry(
    entry: dict[str, Any],
    sidecar: dict[str, Any],
    *,
    stamp: str,
    min_new_runs: int,
    now: datetime,
) -> tuple[dict[str, Any] | None, str]:
    """Measure one ``pending`` entry against ``sidecar``.

    Returns ``(new_entry, note)``: ``new_entry`` is the ledger line to append
    (``None`` when the entry stays pending) and ``note`` is the human-readable
    reason.
    """
    loop = entry["loop"]
    baseline = entry.get("baseline") or {}
    rec = sidecar["loops"].get(loop)
    if not isinstance(rec, dict):
        return None, "loop absent from this harvest"
    if not comparable(baseline, sidecar):
        return None, "harvest not comparable to baseline (window/excluded-projects differ)"
    try:
        new_runs = int(rec["runs"]) - int(baseline["runs"])
        new_conv = int(rec.get("converged", 0)) - int(baseline.get("converged", 0))
        base_pct = int(baseline["success_pct"])
    except (KeyError, TypeError, ValueError):
        return None, "baseline record malformed"
    if new_runs < min_new_runs:
        return None, f"no verdict yet: {max(new_runs, 0)} new run(s), need {min_new_runs}"
    post_pct = round(new_conv / new_runs * 100)
    if post_pct > base_pct:
        status = "improved"
    elif post_pct < base_pct:
        status = "regressed"
    else:
        status = "unchanged"
    new_entry = dict(entry)
    new_entry.update(
        {
            "status": status,
            "recorded_at": now.isoformat(),
            "measured": {
                "harvest_stamp": stamp,
                "new_runs": new_runs,
                "new_converged": new_conv,
                "post_success_pct": post_pct,
                "top_outcome": rec.get("top_outcome"),
            },
        }
    )
    return new_entry, f"{base_pct}% -> {post_pct}% over {new_runs} new run(s)"


def measure(
    entries: list[dict[str, Any]],
    sidecar: dict[str, Any],
    *,
    stamp: str,
    min_new_runs: int,
    now: datetime,
) -> tuple[list[dict[str, Any]], list[tuple[str, str, str]]]:
    """Measure every ``pending`` fix. Returns ``(new_entries, rows)``.

    ``rows`` are ``(loop, status, note)`` for the summary table; a loop that
    stays pending still gets a row so the operator sees why.
    """
    new_entries: list[dict[str, Any]] = []
    rows: list[tuple[str, str, str]] = []
    for loop, entry in sorted(latest_by_loop(entries).items()):
        if entry.get("status") != "pending":
            continue
        new_entry, note = measure_entry(
            entry, sidecar, stamp=stamp, min_new_runs=min_new_runs, now=now
        )
        if new_entry is not None:
            new_entries.append(new_entry)
            rows.append((loop, str(new_entry["status"]), note))
        else:
            rows.append((loop, "pending", note))
    return new_entries, rows


def render_measure_table(rows: list[tuple[str, str, str]]) -> str:
    if not rows:
        return "No pending fixes to measure."
    out = ["| Loop | Verdict | Detail |", "|---|---|---|"]
    out += [f"| `{loop}` | {status} | {note} |" for loop, status, note in rows]
    return "\n".join(out)


def cmd_measure(args: argparse.Namespace) -> int:
    sidecar = load_sidecar(args.sidecar)
    entries = read_ledger(args.ledger)
    new_entries, rows = measure(
        entries,
        sidecar,
        stamp=sidecar_stamp(args.sidecar, sidecar),
        min_new_runs=args.min_new_runs,
        now=utc_now(),
    )
    for entry in new_entries:
        append_ledger(args.ledger, entry)
    print("## Fleet re-measure (fixes recorded by earlier runs)")
    print()
    print(render_measure_table(rows))
    regressed = [loop for loop, status, _ in rows if status == "regressed"]
    if regressed:
        print(
            "\nWARNING: regressed after fix (recorded, not reverted): " + ", ".join(regressed),
            file=sys.stderr,
        )
    return EXIT_YES


# --------------------------------------------------------------------------- #
# check-proposal
# --------------------------------------------------------------------------- #


def check_proposal(artifact: Path) -> str:
    """Validate the specialist's artifact and return its verdict token."""
    try:
        text = artifact.read_text()
    except OSError as e:
        raise FleetImproveError(f"diagnosis artifact not found at {artifact}: {e}") from e
    missing = [h for h in ARTIFACT_SECTIONS if h not in text]
    if missing:
        raise FleetImproveError(f"{artifact}: missing section(s): {', '.join(missing)}")
    start = text.index("## Proposed change") + len("## Proposed change")
    rest = text[start:]
    next_heading = re.search(r"^## ", rest, re.MULTILINE)
    body = rest[: next_heading.start()] if next_heading else rest
    if not body.strip():
        raise FleetImproveError(f"{artifact}: '## Proposed change' is empty")
    verdicts = _VERDICT_RE.findall(text)
    if not verdicts:
        raise FleetImproveError(f"{artifact}: no 'Verdict: fix|not-a-loop-bug|needs-human' line")
    return VERDICT_TOKENS[verdicts[-1]]


def cmd_check_proposal(args: argparse.Namespace) -> int:
    target = load_target(args.run_dir)
    print(check_proposal(Path(target["artifact"])))
    return EXIT_YES


# --------------------------------------------------------------------------- #
# gate
# --------------------------------------------------------------------------- #


def gate(target: dict[str, Any], run_dir: Path, runner: Runner = _run) -> tuple[bool, str]:
    """Deterministic in-run acceptance gate for the applied change.

    The real acceptance signal is the next run's fleet re-measure; this gate
    only rejects changes that are broken *now*: nothing changed, YAML no
    longer parses, ``ll-loop validate`` reports an error or more warnings
    than before the edit, or the built-in-loop test gates (warning ratchet,
    hardcode gate, expected-loop set) fail.
    """
    yaml_path = Path(target["yaml_path"])
    diff = runner(["git", "diff", "--quiet", "--", str(yaml_path)], cwd=Path.cwd(), timeout=30)
    if diff.returncode == 0:
        return False, "no change applied to the built-in YAML"
    try:
        yaml.safe_load(yaml_path.read_text())
    except (OSError, yaml.YAMLError) as e:
        return False, f"YAML no longer parses: {e}"
    try:
        report, _raw = validate_loop(yaml_path, runner)
    except FleetImproveError as e:
        return False, str(e)
    if not report.get("valid", False):
        errors = [
            v.get("message", "")
            for v in report.get("violations", [])
            if isinstance(v, dict) and v.get("severity") == "error"
        ]
        return False, "ll-loop validate reports errors: " + "; ".join(errors)
    baseline_path = run_dir / "gate-baseline.json"
    try:
        baseline = json.loads(baseline_path.read_text())
        baseline_warnings = int(baseline.get("warnings", 0))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        baseline_warnings = 0
    warnings = warning_count(report)
    if warnings > baseline_warnings:
        return False, f"validator warnings grew: {baseline_warnings} -> {warnings}"
    tests_dir = Path(target.get("tests_dir", ""))
    test_files = [
        tests_dir / "test_builtin_loops.py",
        tests_dir / "test_builtin_loop_hardcode_gate.py",
    ]
    existing = [str(p) for p in test_files if p.is_file()]
    if existing:
        proc = runner(
            [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *existing],
            cwd=Path.cwd(),
            timeout=1800,
        )
        if proc.returncode != 0:
            tail = "\n".join(proc.stdout.strip().splitlines()[-15:])
            return False, f"built-in loop tests failed (exit {proc.returncode}):\n{tail}"
    return True, f"gate passed (warnings {baseline_warnings} -> {warnings})"


def cmd_gate(args: argparse.Namespace) -> int:
    target = load_target(args.run_dir)
    ok, detail = gate(target, args.run_dir)
    print(detail)
    return EXIT_YES if ok else EXIT_NO


# --------------------------------------------------------------------------- #
# record
# --------------------------------------------------------------------------- #


def record(
    target: dict[str, Any],
    *,
    status: str,
    reason: str,
    now: datetime,
    head: str,
) -> dict[str, Any]:
    """Build the ledger entry for the current target."""
    return {
        "loop": target["loop"],
        "status": status,
        "recorded_at": now.isoformat(),
        "commit": head if status == "pending" else None,
        "artifact": target.get("artifact"),
        "harvest_stamp": target.get("harvest_stamp"),
        "baseline": target.get("baseline", {}),
        "reason": reason,
    }


def cmd_record(args: argparse.Namespace) -> int:
    target = load_target(args.run_dir)
    head = git_head(_run) if args.status == "pending" else ""
    entry = record(target, status=args.status, reason=args.reason, now=utc_now(), head=head)
    append_ledger(args.ledger, entry)
    if args.status == "pending":
        count = read_fixes_count(args.run_dir) + 1
        (args.run_dir / "fixes.count").write_text(f"{count}\n")
    print(json.dumps(entry, sort_keys=True))
    return EXIT_YES


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m little_loops.fleet_improve",
        description="Helpers for the fleet-loop-improve built-in meta-loop.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--run-dir", type=Path, required=True, help="the loop's ${context.run_dir}")
        p.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)

    p = sub.add_parser("select", help="pick the next flagged built-in loop; exit 1 if none")
    common(p)
    p.add_argument("--sidecar", type=Path, required=True)
    p.add_argument("--threshold", type=int, default=50)
    p.add_argument("--min-runs", type=int, default=3)
    p.add_argument("--dismiss-ttl-days", type=int, default=30)
    p.add_argument("--max-fixes", type=int, default=1)
    p.set_defaults(func=cmd_select)

    p = sub.add_parser("diagnose", help="run diagnose-evaluators/calibrate-budget per project")
    common(p)
    p.set_defaults(func=cmd_diagnose)

    p = sub.add_parser("measure", help="measure pending fixes against a fresh sidecar")
    common(p)
    p.add_argument("--sidecar", type=Path, required=True)
    p.add_argument("--min-new-runs", type=int, default=3)
    p.set_defaults(func=cmd_measure)

    p = sub.add_parser("check-proposal", help="validate the diagnosis artifact; print verdict")
    common(p)
    p.set_defaults(func=cmd_check_proposal)

    p = sub.add_parser("gate", help="deterministic acceptance gate; exit 1 on failure")
    common(p)
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("record", help="append a ledger entry for the current target")
    common(p)
    p.add_argument(
        "--status",
        required=True,
        choices=["pending", "dismissed", "needs-human", "rejected"],
    )
    p.add_argument("--reason", default="")
    p.set_defaults(func=cmd_record)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result: int = args.func(args)
    except FleetImproveError as e:
        print(f"fleet_improve {args.command}: {e}", file=sys.stderr)
        return EXIT_ERROR
    return result


if __name__ == "__main__":
    sys.exit(main())
