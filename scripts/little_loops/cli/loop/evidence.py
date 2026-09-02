"""ll-loop evidence: deterministic verification-evidence bundle export (FEAT-3182).

Assembles a plain-JSON attestation for a `verify-issue-loop` run from three
deterministic sources only — git predicates, the `loop_runs` row in
`history.db`, and the archived run-directory files under
`.loops/.history/<run_id>/`. LLM-graded verdicts (criterion pass/fail,
`break_found`) are never treated as evidentiary content (Option A, decided
`## Proposed Solution`); they are attached as a segregated, explicitly
labeled `context_non_evidentiary` section for human context only. Promoted
from `scripts/tests/spike/verify_evidence_bundle/` — the spike's 7 tests
proved the segregation mechanism; this module extends it with the allowlist,
gap taxonomy, and run-time git-fact wiring the Program Design decided.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_EVIDENTIARY_SOURCES = frozenset({"git_ref", "history_db_row", "run_dir_file"})

_BUNDLE_COMMENT = (
    "Deterministic verification-evidence bundle (FEAT-3182). Regenerate with "
    "`ll-loop evidence <run>`. `evidentiary` holds only facts re-derivable from "
    "git, history.db, and the archived run directory -- no LLM self-evaluation "
    "contributes to it. `context_non_evidentiary` holds LLM-graded verdicts, "
    "labeled as such, for human context only. `worktree_digest` covers tracked "
    "file content plus untracked file *names* -- not untracked file content. "
    "This file is evidence, not a cache: it is not safe to delete-and-regenerate "
    "if the underlying run directory has since been pruned."
)

# FEAT-3182 step 3d: evidentiary loop_runs fields are an explicit allowlist,
# not a column dump -- `error` (free text, may embed host/LLM output) and
# `evaluator_score` (semantics unpinned) are not guaranteed deterministic in
# origin and go to context_non_evidentiary instead (see _loop_run_context()).
_LOOP_RUN_ALLOWLIST = (
    "run_id",
    "loop_name",
    "started_at",
    "ended_at",
    "final_state",
    "iterations",
    "terminated_by",
    "failure_terminal",
    "head_sha",
    "branch",
)


@dataclass
class EvidenceEntry:
    """One enumerable, source-traced evidentiary fact."""

    key: str
    value: Any
    source: str  # "git_ref" | "history_db_row" | "run_dir_file"

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value, "source": self.source}


@dataclass
class ContextEntry:
    """One segregated, labeled-non-evidentiary fact (LLM-sourced or otherwise
    not guaranteed deterministic)."""

    key: str
    value: Any
    llm_sourced: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value, "llm_sourced": self.llm_sourced}


@dataclass
class GapEntry:
    """One explicit, enumerable evidence gap (never a silent omission)."""

    category: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"category": self.category, "detail": self.detail}


@dataclass
class EvidenceBundle:
    """Top-level Option A bundle: deterministic facts plus segregated context."""

    evidentiary: list[EvidenceEntry] = field(default_factory=list)
    context_non_evidentiary: list[ContextEntry] = field(default_factory=list)
    gaps: list[GapEntry] = field(default_factory=list)
    schema_version: int = 1

    @property
    def has_gaps(self) -> bool:
        return bool(self.gaps)

    def to_dict(self) -> dict[str, Any]:
        """Locked stable-JSON shape -- plain dict/list/str/bool/int, no custom types."""
        return {
            "_comment": _BUNDLE_COMMENT,
            "schema_version": self.schema_version,
            "evidentiary": [e.to_dict() for e in self.evidentiary],
            "context_non_evidentiary": [c.to_dict() for c in self.context_non_evidentiary],
            "gaps": [g.to_dict() for g in self.gaps],
            "has_gaps": self.has_gaps,
        }

    def canonical_json(self) -> str:
        """Byte-identical across renders of unchanged inputs (AC2). No timestamp
        field exists anywhere in the shape, by design."""
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_events(run_dir: Path) -> list[dict[str, Any]]:
    events_file = run_dir / "events.jsonl"
    events: list[dict[str, Any]] = []
    if not events_file.exists():
        return events
    with open(events_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _expected_probe_count(loop_yaml_path: str | None) -> int | None:
    """Best-effort expected probe-state count from the loop YAML that ran.

    Returns None (unknown) when the YAML path was never recorded or the file
    is no longer readable -- `ll-loop scaffold-verify` regenerates its output
    path on every invocation, so the file may have been overwritten or
    removed by export time. `probe-aggregate` is excluded: it aggregates
    over the probes, it is not one itself.
    """
    if not loop_yaml_path:
        return None
    path = Path(loop_yaml_path)
    if not path.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, yaml.YAMLError):
        return None
    states = data.get("states")
    if not isinstance(states, dict):
        return None
    return sum(1 for name in states if name.startswith("probe-") and name != "probe-aggregate")


def _loop_run_context(loop_runs_row_raw: dict[str, Any]) -> list[ContextEntry]:
    """Non-deterministic-origin loop_runs fields, segregated (step 3d)."""
    entries: list[ContextEntry] = []
    error = loop_runs_row_raw.get("error")
    if error is not None:
        entries.append(ContextEntry(key="loop_runs.error", value=error, llm_sourced=False))
    evaluator_score = loop_runs_row_raw.get("evaluator_score")
    if evaluator_score is not None:
        entries.append(
            ContextEntry(key="loop_runs.evaluator_score", value=evaluator_score, llm_sourced=False)
        )
    return entries


def allowlisted_loop_run_dict(loop_runs_row_raw: dict[str, Any]) -> dict[str, Any]:
    """Project a raw loop_runs row dict down to the evidentiary allowlist (step 3d)."""
    return {k: loop_runs_row_raw.get(k) for k in _LOOP_RUN_ALLOWLIST}


def assemble_bundle(
    loop_runs_row: dict[str, Any] | None,
    run_dir: Path | None,
    git_predicates: dict[str, str],
) -> EvidenceBundle:
    """Assemble an Option A bundle from three plain-data inputs.

    *loop_runs_row* is expected pre-allowlisted (``allowlisted_loop_run_dict``);
    the raw row's non-deterministic fields (``error``, ``evaluator_score``) are
    the caller's responsibility to segregate via ``_loop_run_context`` and pass
    separately -- this function never sees them. *git_predicates* are
    export-time-computed git facts (ref liveness, ancestry, issue blob hash),
    distinct from the run-time facts recorded on ``loop_start`` (read from
    *run_dir*'s ``events.jsonl`` below). Any input being absent or incomplete
    produces an explicit `GapEntry` rather than a bundle that silently omits it.
    """
    bundle = EvidenceBundle()

    for gk, gv in sorted(git_predicates.items()):
        bundle.evidentiary.append(EvidenceEntry(key=f"git.{gk}", value=gv, source="git_ref"))

    if loop_runs_row is None:
        bundle.gaps.append(
            GapEntry("missing_loop_runs_row", "no loop_runs row found for this run_id")
        )
    else:
        for k, v in sorted(loop_runs_row.items()):
            bundle.evidentiary.append(
                EvidenceEntry(key=f"loop_runs.{k}", value=v, source="history_db_row")
            )

    if run_dir is None or not run_dir.is_dir():
        bundle.gaps.append(
            GapEntry("missing_run_dir", f"archived run directory not found: {run_dir}")
        )
        return bundle

    for name in ("state.json", "events.jsonl", "summary.json"):
        p = run_dir / name
        if p.exists():
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            bundle.evidentiary.append(
                EvidenceEntry(key=f"file.{name}.sha256", value=digest, source="run_dir_file")
            )

    state_data = _read_json_file(run_dir / "state.json") or {}
    loop_name = str(state_data.get("loop_name", ""))
    raw_context = state_data.get("context")
    issue_path = raw_context.get("issue_path") if isinstance(raw_context, dict) else None

    events = _read_events(run_dir)
    loop_starts = [e for e in events if e.get("event") == "loop_start"]
    loop_completes = [e for e in events if e.get("event") == "loop_complete"]

    # --- run-time facts recorded at loop_start (FEAT-3182 step 3): first
    # loop_start wins across a resumed run; a later disagreeing one is a gap,
    # never silently overwritten (events.jsonl is append-only).
    first_start = loop_starts[0] if loop_starts else {}
    head_sha = first_start.get("head_sha")
    branch = first_start.get("branch")
    start_digest = first_start.get("worktree_digest")
    loop_yaml_path = first_start.get("loop_yaml_path")
    loop_yaml_sha256 = first_start.get("loop_yaml_sha256")

    if not head_sha:
        bundle.gaps.append(
            GapEntry(
                "missing_head_sha",
                "no head_sha recorded at loop_start (pre-FEAT-3182 run, or "
                "capture_git_facts was off)",
            )
        )
    else:
        bundle.evidentiary.append(EvidenceEntry("run.head_sha", head_sha, "run_dir_file"))
    if branch:
        bundle.evidentiary.append(EvidenceEntry("run.branch", branch, "run_dir_file"))
    if start_digest:
        bundle.evidentiary.append(
            EvidenceEntry("run.worktree_digest_at_start", start_digest, "run_dir_file")
        )
    if loop_yaml_path:
        bundle.evidentiary.append(
            EvidenceEntry("run.loop_yaml_path", loop_yaml_path, "run_dir_file")
        )
    if loop_yaml_sha256:
        bundle.evidentiary.append(
            EvidenceEntry("run.loop_yaml_sha256", loop_yaml_sha256, "run_dir_file")
        )

    for later_start in loop_starts[1:]:
        later_sha = later_start.get("head_sha")
        if later_sha and later_sha != head_sha:
            bundle.gaps.append(
                GapEntry(
                    "head_sha_changed_across_resume",
                    f"first loop_start head_sha={head_sha!r}, a later resume recorded "
                    f"{later_sha!r}",
                )
            )
            break

    # --- end-of-run worktree digest (step 3, second half of AC "recorded at
    # both loop_start and loop_complete") plus the missing_loop_complete /
    # loop_runs_row_stale cross-checks (step 3h).
    if not loop_completes:
        bundle.gaps.append(
            GapEntry("missing_loop_complete", "no loop_complete event found in events.jsonl")
        )
    else:
        last_complete = loop_completes[-1]
        end_digest = last_complete.get("worktree_digest")
        if start_digest and end_digest and start_digest != end_digest:
            bundle.gaps.append(
                GapEntry(
                    "worktree_changed_during_run",
                    "worktree_digest differs between loop_start and the last loop_complete",
                )
            )
        if loop_runs_row is not None:
            disagreements = [
                field_name
                for field_name in ("final_state", "terminated_by", "iterations")
                if last_complete.get(field_name) is not None
                and loop_runs_row.get(field_name) != last_complete.get(field_name)
            ]
            if disagreements:
                bundle.gaps.append(
                    GapEntry(
                        "loop_runs_row_stale",
                        "loop_runs row disagrees with the last loop_complete event on: "
                        + ", ".join(disagreements),
                    )
                )

    # --- adversarial-mode probe files (step 3a/3c). Zero is only a gap in
    # adversarial mode; criteria-mode runs never write probe-*.json.
    probe_files = sorted(run_dir.glob("probe-*.json"))
    bundle.evidentiary.append(EvidenceEntry("probe_file_count", len(probe_files), "run_dir_file"))
    adversarial_mode = loop_name.startswith("adversarial-")
    if adversarial_mode:
        if not probe_files:
            bundle.gaps.append(
                GapEntry(
                    "missing_probe_files",
                    "adversarial-mode run archived with zero probe-*.json files",
                )
            )
        else:
            expected = _expected_probe_count(loop_yaml_path)
            if expected is not None and len(probe_files) < expected:
                bundle.gaps.append(
                    GapEntry(
                        "missing_probe_files",
                        f"expected {expected} probe result files, found {len(probe_files)}",
                    )
                )

    # --- the verified criteria: issue file (step 3b). issue_blob_sha comes in
    # via git_predicates (export-time `git rev-parse <head_sha>:<issue_path>`);
    # its absence there means the file wasn't committed at head_sha.
    if not issue_path:
        bundle.gaps.append(
            GapEntry(
                "missing_issue_path",
                "state.json context has no issue_path (pre-FEAT-3182 scaffold run)",
            )
        )
    else:
        bundle.evidentiary.append(EvidenceEntry("run.issue_path", issue_path, "run_dir_file"))
        if "issue_blob_sha" not in git_predicates:
            bundle.gaps.append(
                GapEntry(
                    "issue_not_committed_at_head",
                    f"{issue_path} not resolvable via `git rev-parse <head_sha>:<issue_path>`",
                )
            )
            wt_path = Path(issue_path)
            if wt_path.is_file():
                wt_hash = hashlib.sha256(wt_path.read_bytes()).hexdigest()
                bundle.evidentiary.append(
                    EvidenceEntry("issue_file.working_tree_sha256", wt_hash, "run_dir_file")
                )

    # --- segregated LLM-sourced context: captured verdicts/reasons and every
    # evaluate event carrying llm_model. Predicate mirrors evaluate_llm_structured's
    # details shape (fsm/evaluators.py) and also accepts check_semantic so a future
    # evaluator omitting llm_model still segregates (Design Review item 6).
    captured = state_data.get("captured", {})
    if isinstance(captured, dict):
        for key, entry in sorted(captured.items()):
            if isinstance(entry, dict) and "verdict" in entry:
                bundle.context_non_evidentiary.append(
                    ContextEntry(key=f"captured.{key}.verdict", value=entry["verdict"])
                )
                if "reason" in entry:
                    bundle.context_non_evidentiary.append(
                        ContextEntry(key=f"captured.{key}.reason", value=entry["reason"])
                    )

    for event in events:
        if event.get("event") != "evaluate":
            continue
        if "llm_model" not in event and event.get("type") not in (
            "llm_structured",
            "check_semantic",
        ):
            continue
        state = event.get("state", "?")
        for field_name in ("reason", "evidence", "raw", "llm_model", "llm_prompt"):
            if field_name in event:
                bundle.context_non_evidentiary.append(
                    ContextEntry(key=f"evaluate.{state}.{field_name}", value=event[field_name])
                )

    return bundle


def _run_git(repo_root: Path, args: list[str]) -> tuple[int, str]:
    """Explicit-cwd, timeout-bounded git invocation for export-time predicates only.

    Mirrors FSMExecutor._prepatch_git()'s failure contract (None-shaped here as
    a non-zero exit) -- never raises, never leaks stderr.
    """
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(repo_root), capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return (1, "")
    return (proc.returncode, proc.stdout)


def compute_git_predicates(
    repo_root: Path, head_sha: str | None, issue_path: str | None
) -> dict[str, str]:
    """Export-time-only git facts: ref liveness, ancestry, and the issue blob hash.

    Distinct from the run-time facts (head_sha/branch/worktree_digest) recorded
    at loop_start -- those are read from the archive, never recomputed here.
    """
    predicates: dict[str, str] = {}
    if not head_sha:
        return predicates
    code, _ = _run_git(repo_root, ["cat-file", "-e", head_sha])
    predicates["head_sha_live"] = "true" if code == 0 else "false"
    code, _ = _run_git(repo_root, ["merge-base", "--is-ancestor", head_sha, "HEAD"])
    predicates["head_sha_is_ancestor_of_head"] = "true" if code == 0 else "false"
    if issue_path:
        code, out = _run_git(repo_root, ["rev-parse", f"{head_sha}:{issue_path}"])
        if code == 0 and out.strip():
            predicates["issue_blob_sha"] = out.strip()
    return predicates


def _print_human_summary(bundle: EvidenceBundle, run_id: str) -> None:
    print(f"run_id: {run_id}")
    for entry in bundle.evidentiary:
        if entry.key == "run.head_sha":
            print(f"head_sha: {entry.value}")
            break
    print(f"evidentiary entries: {len(bundle.evidentiary)}")
    print(f"context (non-evidentiary): {len(bundle.context_non_evidentiary)}")
    if bundle.has_gaps:
        print(f"gaps: {len(bundle.gaps)}")
        for g in bundle.gaps:
            print(f"  - {g.category}: {g.detail}")
    else:
        print("gaps: none")


def cmd_evidence(args: argparse.Namespace, loops_dir: Path) -> int:
    """Entry point for ``ll-loop evidence <run> | --latest LOOP [--output PATH] [--json]``."""
    from little_loops.cli.loop.audit import resolve_run
    from little_loops.history_reader import find_loop_run

    try:
        run_dir = resolve_run(getattr(args, "run", None), getattr(args, "latest", None), loops_dir)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    run_id = run_dir.name
    row = find_loop_run(run_id)
    loop_runs_row: dict[str, Any] | None = None
    context_extra: list[ContextEntry] = []
    if row is not None:
        raw = {
            "run_id": row.run_id,
            "loop_name": row.loop_name,
            "started_at": row.started_at,
            "ended_at": row.ended_at,
            "final_state": row.final_state,
            "iterations": row.iterations,
            "terminated_by": row.terminated_by,
            "failure_terminal": row.failure_terminal,
            "head_sha": row.head_sha,
            "branch": row.branch,
            "error": row.error,
            "evaluator_score": row.evaluator_score,
        }
        loop_runs_row = allowlisted_loop_run_dict(raw)
        context_extra = _loop_run_context(raw)

    state_data = _read_json_file(run_dir / "state.json") or {}
    events = _read_events(run_dir)
    loop_starts = [e for e in events if e.get("event") == "loop_start"]
    head_sha = loop_starts[0].get("head_sha") if loop_starts else None
    raw_context = state_data.get("context")
    issue_path = raw_context.get("issue_path") if isinstance(raw_context, dict) else None

    git_predicates = compute_git_predicates(Path.cwd(), head_sha, issue_path)

    bundle = assemble_bundle(loop_runs_row, run_dir, git_predicates)
    bundle.context_non_evidentiary.extend(context_extra)

    canonical = bundle.canonical_json()
    output_path = getattr(args, "output", None)
    if output_path is not None:
        Path(output_path).write_text(canonical + "\n", encoding="utf-8")

    if getattr(args, "json", False):
        print(canonical)
    else:
        _print_human_summary(bundle, run_id)

    if output_path is not None:
        print(f"Wrote: {output_path}")

    return 0
