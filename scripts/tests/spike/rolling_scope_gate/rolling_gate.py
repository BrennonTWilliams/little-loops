"""Spike for FEAT-3335: proves the rolling-baseline containment-gate
mechanism (Option B) that has no precedent elsewhere in the tree.

changed_set() mirrors the embedded python3 -c body in
scripts/little_loops/loops/workflow-generator.yaml's init/check_intent_scope
states (tracked-diff-vs-ref UNION untracked, path -> sha256, DELETED
sentinel). run_gate() adds the one capability the landed FEAT-3332 script
does not have: advancing the baseline file to the current snapshot when the
gate passes, so a chain of gates can each attribute violations to the window
since the previous gate rather than since init.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field

EXCL = [":(exclude,glob)**/.loops/**", ":(exclude,glob)**/.ll/**"]
DELETED = "DELETED"


def _run(args: list[str]) -> list[bytes]:
    try:
        out = subprocess.run(args, capture_output=True, check=False).stdout
    except OSError:
        return []
    return [p for p in out.split(b"\0") if p]


def _hash(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return DELETED


def changed_set(root: str, ref: str) -> dict[str, str]:
    """Tracked-diff-vs-ref union untracked, path -> content hash."""
    paths: set[str] = set()
    if ref:
        diff_args = ["git", "-C", root, "diff", "--name-only", "-z", ref, "--", *EXCL]
        for p in _run(diff_args):
            paths.add(p.decode("utf-8", "surrogateescape"))
    ls_args = ["git", "-C", root, "ls-files", "-o", "--exclude-standard", "-z", "--", *EXCL]
    for p in _run(ls_args):
        paths.add(p.decode("utf-8", "surrogateescape"))
    result: dict[str, str] = {}
    for p in paths:
        full = os.path.join(root, p)
        result[p] = _hash(full) if os.path.exists(full) else DELETED
    return result


@dataclass
class GateResult:
    passed: bool
    violations: list[str] = field(default_factory=list)
    snapshot: dict[str, str] = field(default_factory=dict)
    skipped: bool = False


def run_gate(
    root: str,
    ref: str,
    run_dir: str,
    baseline_path: str,
    *,
    advance: bool = True,
) -> GateResult:
    """Diff the current changed-set against baseline_path, restricted to
    paths outside run_dir. On pass (no violations), when advance is True,
    overwrite baseline_path with the current snapshot -- the rolling-baseline
    step Option B needs and the landed FEAT-3332 script does not do. On
    failure, baseline_path is left untouched so the violating window stays
    attributable."""
    try:
        if os.path.getsize(baseline_path) == 0:
            raise ValueError("empty baseline")
        with open(baseline_path) as fh:
            baseline = json.load(fh)
    except (OSError, ValueError):
        return GateResult(passed=True, skipped=True)

    current = changed_set(root, ref)

    flagged: set[str] = set()
    for p, h in current.items():
        if p not in baseline or baseline[p] != h:
            flagged.add(p)
    for p in baseline:
        if p not in current:
            flagged.add(p)

    run_dir_real = os.path.realpath(run_dir)
    violations = []
    for p in sorted(flagged):
        full_real = os.path.realpath(os.path.join(root, p))
        if full_real == run_dir_real or full_real.startswith(run_dir_real + os.sep):
            continue
        violations.append(p)

    if violations:
        return GateResult(passed=False, violations=violations, snapshot=current)

    if advance:
        with open(baseline_path, "w") as fh:
            json.dump(current, fh)

    return GateResult(passed=True, snapshot=current)


def write_baseline(baseline_path: str, snapshot: dict[str, str]) -> None:
    with open(baseline_path, "w") as fh:
        json.dump(snapshot, fh)
