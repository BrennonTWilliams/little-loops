"""Run finalization for the ``autodev`` built-in loop.

autodev's ``finalize_done`` state (and its ``finalize_step_capped`` step-cap
handler) call ``python3 -m little_loops.autodev_summary`` to:

1. **Promote staged issues** (:func:`promote_staged`). ``check_passed`` and
   friends only *stage* an issue in ``autodev-staged.txt`` once it clears the
   readiness/outcome thresholds; finalization re-reads each staged issue's
   frontmatter status and appends it to ``autodev-passed.txt`` only when it is
   verifiably closed (``done``/``completed``, and -- with the quality gate on --
   a ``GATE_PASS``/``GATE_SKIP`` evidence record in ``quality/<ID>.json``; or
   ``cancelled``). Anything else is appended to ``autodev-unverified.txt``
   (bare ID, or ``ID  quality_gate_failed|quality_gate_infra|
   quality_evidence_missing``) unless that ledger already records the ID.
2. **Build the summary** (:func:`build_summary`) from the run-dir ledgers,
   folding a residual ``autodev-inflight`` sentinel into the unverified bucket
   as ``ID  inflight_at_finalize`` (the run abandoned that issue mid-flight).
3. **Print the operator report** (:func:`render_report`) and **write
   ``summary.json``** (:func:`write_summary`) -- one compact JSON line whose
   16 keys keep a fixed order that downstream tooling reads.

The verdict ladder is ``success`` -> ``partial`` -> ``phantom`` ->
``not_started`` -> ``no-op``; a ``rate_limit`` stop reason overrides it to
``rate_limited`` and a ``max_steps`` stop reason to ``max_steps`` (the run was
interrupted, not failed). Cancelled closures count toward ``closed`` but never
toward ``closed_implemented``, so an all-cancelled run is ``no-op``.

This module is a behaviour-identical port of the shell action the state used to
carry inline (pinned by golden fixtures). Known, deliberate differences: IDs are
matched literally rather than as regular expressions, lists sort by code point
(the shell's ``sort`` followed the locale), the two string values in
``summary.json`` are JSON-escaped, and a missing run directory or an unwritable
ledger/summary is an error (exit 2) instead of a silent no-op.

Exit-code contract (mirrors the state's ``shell_exit`` routes): ``0`` = the run
finished with any non-phantom verdict, ``1`` = ``phantom`` (something staged or
in flight was never verifiably closed), ``2`` = the summary could not be
produced.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from little_loops.file_utils import atomic_write

EXIT_OK = 0
EXIT_PHANTOM = 1
EXIT_ERROR = 2

#: Run-dir ledger and sentinel file names read or written by finalization.
STAGED = "autodev-staged.txt"
PASSED = "autodev-passed.txt"
UNVERIFIED = "autodev-unverified.txt"
SKIPPED = "autodev-skipped.txt"
GATE_BLOCKED = "autodev-gate-blocked.txt"
DECISION_UNRESOLVED = "autodev-decision-unresolved.txt"
NOT_STARTED = "autodev-not-started.txt"
PROOF_GATE_INFRA = "autodev-proof-gate-infra.txt"
SPIKE_INCONCLUSIVE = "autodev-spike-inconclusive.txt"
PROPOSAL_UNSOUND = "autodev-proposal-unsound.txt"
INFLIGHT = "autodev-inflight"
STOP_REASON = "autodev-stop-reason"
QUEUE = "autodev-queue.txt"
QUALITY_DIR = "quality"
SUMMARY = "summary.json"

#: ``--quality-gate`` values (case-insensitive) that switch the gate off.
QUALITY_GATE_OFF = frozenset({"false", "0", "no", "off"})

STOP_COMPLETED = "completed"
STOP_RATE_LIMIT = "rate_limit"
STOP_MAX_STEPS = "max_steps"

#: Stop reasons that replace the verdict ladder's result with a named verdict.
STOP_REASON_VERDICTS: dict[str, str] = {
    STOP_RATE_LIMIT: "rate_limited",
    STOP_MAX_STEPS: "max_steps",
}

_CLOSED_STATUSES = frozenset({"done", "completed"})
_CANCELLED_STATUS = "cancelled"

# POSIX [[:space:]] in the C locale, and awk's default field separators.
_WS = "[ \t\n\r\f\v]"
_WS_RE = re.compile(_WS)
_BLANK_RE = re.compile(f"{_WS}*")
_FIELD_SEP_RE = re.compile("[ \t\n]+")
_QUALITY_REASON_RE = re.compile(f"{_WS}quality_gate_(failed|infra)({_WS}|$)")

#: Maps an issue ID to its lower-cased frontmatter status ("" when unknown).
StatusResolver = Callable[[str], str]


class AutodevSummaryError(Exception):
    """Finalization could not read its inputs or write its outputs."""


@dataclass
class AutodevSummary:
    """Counts and display lists for one autodev run.

    The first 16 fields are the ``summary.json`` payload in its published key
    order (see :meth:`to_dict`); the remaining fields only feed the report.
    """

    verdict: str
    closed: int = 0
    not_closed: int = 0
    skipped: int = 0
    gate_blocked: int = 0
    decision_unresolved: int = 0
    not_started: int = 0
    inflight_unresolved: int = 0
    abandoned: int = 0
    stop_reason: str = STOP_COMPLETED
    pending: int = 0
    proof_gate_infra: int = 0
    closed_implemented: int = 0
    closed_cancelled: int = 0
    quality_failed: int = 0
    quality_gate_infra: int = 0
    # --- report-only -------------------------------------------------------
    passed_ids: list[str] = field(default_factory=list)
    cancelled_ids: list[str] = field(default_factory=list)
    skipped_ids: list[str] = field(default_factory=list)
    infra_skipped_ids: list[str] = field(default_factory=list)
    already_resolved_ids: list[str] = field(default_factory=list)
    blocked_by_unmet_ids: list[str] = field(default_factory=list)
    gate_blocked_ids: list[str] = field(default_factory=list)
    decision_unresolved_ids: list[str] = field(default_factory=list)
    not_started_ids: list[str] = field(default_factory=list)
    spike_inconclusive: str = ""
    proposal_unsound: str = ""
    proof_gate_infra_ids: list[str] = field(default_factory=list)
    quality_failed_list: str = ""
    quality_gate_infra_list: str = ""
    quality_gated: int = 0
    unverified_display_ids: list[str] = field(default_factory=list)
    pending_ids: list[str] = field(default_factory=list)

    #: ``summary.json`` keys, in order.
    KEYS = (
        "verdict",
        "closed",
        "not_closed",
        "skipped",
        "gate_blocked",
        "decision_unresolved",
        "not_started",
        "inflight_unresolved",
        "abandoned",
        "stop_reason",
        "pending",
        "proof_gate_infra",
        "closed_implemented",
        "closed_cancelled",
        "quality_failed",
        "quality_gate_infra",
    )

    def to_dict(self) -> dict[str, Any]:
        """Return the ``summary.json`` payload with keys in published order."""
        return {key: getattr(self, key) for key in self.KEYS}

    def to_json(self) -> str:
        """Return the compact one-line ``summary.json`` text (newline-terminated)."""
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False) + "\n"

    @property
    def exit_code(self) -> int:
        """``EXIT_PHANTOM`` for a phantom verdict, else ``EXIT_OK``."""
        return EXIT_PHANTOM if self.verdict == "phantom" else EXIT_OK


# --------------------------------------------------------------------------- io


def _read(path: Path) -> str:
    """Return *path*'s text, or ``""`` when it is missing or unreadable."""
    try:
        return path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError:
        return ""


def _records(text: str) -> list[str]:
    """Split *text* into lines the way grep/awk do (no phantom trailing record)."""
    if not text:
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def _nonblank(lines: Iterable[str]) -> list[str]:
    return [line for line in lines if not _BLANK_RE.fullmatch(line)]


def _sorted_unique(lines: Iterable[str]) -> list[str]:
    return sorted(set(lines))


def _ledger(run_dir: Path, name: str) -> list[str]:
    """Sorted, de-duplicated non-blank lines of a run-dir ledger."""
    return _sorted_unique(_nonblank(_records(_read(run_dir / name))))


def _fields(line: str) -> list[str]:
    """awk-style whitespace fields of *line*."""
    return [f for f in _FIELD_SEP_RE.split(line) if f]


def _field(line: str, index: int) -> str:
    fields = _fields(line)
    return fields[index] if index < len(fields) else ""


def _labelled(line: str) -> str:
    """Format a ``ID  reason`` ledger line as ``ID (reason)``."""
    return f"{_field(line, 0)} ({_field(line, 1)})"


def _squash(text: str) -> str:
    """Drop every whitespace character (``tr -d '[:space:]'``)."""
    return _WS_RE.sub("", text)


def _has_id_line(path: Path, issue_id: str) -> bool:
    """True when a line of *path* starts with *issue_id* followed by space or EOL."""
    pattern = re.compile(f"^{re.escape(issue_id)}({_WS}|$)")
    return any(pattern.match(line) for line in _records(_read(path)))


def _append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8", errors="surrogateescape") as fh:
        fh.write(line + "\n")


# --------------------------------------------------------------- issue status


def issue_status_resolver(project_root: Path) -> StatusResolver:
    """Return a resolver reading issue status from frontmatter under *project_root*.

    Issues are located with the same resolver ``ll-issues show`` uses. The
    status is lower-cased; an unknown ID or unreadable file resolves to ``""``.
    """
    from little_loops.config import BRConfig
    from little_loops.frontmatter import parse_frontmatter
    from little_loops.issue_parser import resolve_issue_path

    try:
        config = BRConfig(project_root)
    except Exception:
        return lambda _issue_id: ""

    def resolve(issue_id: str) -> str:
        try:
            path = resolve_issue_path(config, issue_id)
            if path is None:
                return ""
            frontmatter = parse_frontmatter(path.read_text(), coerce_types=True)
        except Exception:
            return ""
        return str(frontmatter.get("status", "open")).lower()

    return resolve


# ----------------------------------------------------------------- promotion


def quality_gate_enabled(value: str) -> bool:
    """Interpret a ``quality_gate`` context value (anything but false/0/no/off is on)."""
    return value.lower() not in QUALITY_GATE_OFF


def _evidence_verdict(path: Path) -> str:
    """The ``verdict`` recorded in a quality evidence file, or ``""``."""
    try:
        with path.open() as fh:
            verdict = json.load(fh).get("verdict") or ""
    except Exception:
        return ""
    return str(verdict).rstrip("\n")


def promote_staged(run_dir: Path, *, quality_gate: bool, status_of: StatusResolver) -> list[str]:
    """Move verifiably closed staged issues into ``autodev-passed.txt``.

    Every whitespace-separated token of the (sorted, de-duplicated) staged
    ledger is resolved to a status. Closed issues are appended to
    ``autodev-passed.txt``; everything else is appended to
    ``autodev-unverified.txt`` unless a line there already starts with the ID.

    Returns:
        The cancelled IDs promoted, in processing order (duplicates kept).
    """
    passed = run_dir / PASSED
    unverified = run_dir / UNVERIFIED
    quality_dir = run_dir / QUALITY_DIR
    tokens = [tok for line in _ledger(run_dir, STAGED) for tok in _fields(line)]
    cancelled: list[str] = []
    for issue_id in tokens:
        status = status_of(issue_id)
        if status in _CLOSED_STATUSES:
            if not quality_gate:
                _append_line(passed, issue_id)
                continue
            verdict = _evidence_verdict(quality_dir / f"{issue_id}.json")
            if verdict in ("GATE_PASS", "GATE_SKIP"):
                _append_line(passed, issue_id)
                continue
            reason = {
                "GATE_FAILED": "quality_gate_failed",
                "GATE_INFRA": "quality_gate_infra",
            }.get(verdict, "quality_evidence_missing")
            if not _has_id_line(unverified, issue_id):
                _append_line(unverified, f"{issue_id}  {reason}")
        elif status == _CANCELLED_STATUS:
            _append_line(passed, issue_id)
            cancelled.append(issue_id)
        elif not _has_id_line(unverified, issue_id):
            _append_line(unverified, issue_id)
    return cancelled


def record_abandoned_inflight(run_dir: Path) -> bool:
    """Fold a residual ``autodev-inflight`` sentinel into the unverified ledger.

    Returns:
        True when an in-flight issue was never promoted (the run abandoned it),
        whether or not a ``ID  inflight_at_finalize`` line had to be appended.
    """
    inflight = _squash(_read(run_dir / INFLIGHT))
    if not inflight or inflight in _records(_read(run_dir / PASSED)):
        return False
    unverified = run_dir / UNVERIFIED
    if not _has_id_line(unverified, inflight):
        _append_line(unverified, f"{inflight}  inflight_at_finalize")
    return True


# ------------------------------------------------------------------- summary


def _quality_entry(path: Path, issue_id: str) -> str | None:
    """``ID@<short sha>[ (dirty)]`` from an evidence record; ``None`` if malformed."""
    try:
        with path.open() as fh:
            record: Any = json.load(fh)
    except Exception:
        record = {}
    try:
        sha = (record.get("head_sha") or "")[:8]
        return issue_id + ("@" + sha if sha else "") + (" (dirty)" if record.get("dirty") else "")
    except Exception:
        return None


def _quality_list(run_dir: Path, reason: str) -> str:
    pattern = re.compile(f"{_WS}{reason}({_WS}|$)")
    ids = _sorted_unique(
        _field(line, 0) for line in _records(_read(run_dir / UNVERIFIED)) if pattern.search(line)
    )
    lines: list[str] = []
    for issue_id in ids:
        entry = _quality_entry(run_dir / QUALITY_DIR / f"{issue_id}.json", issue_id)
        if entry is not None:
            lines.extend(entry.split("\n"))
    return ",".join(lines)


def _count_matching(run_dir: Path, name: str, reason: str) -> int:
    pattern = re.compile(f"{_WS}{reason}({_WS}|$)")
    return sum(1 for line in _records(_read(run_dir / name)) if pattern.search(line))


def _quality_gated(run_dir: Path) -> int:
    quality_dir = run_dir / QUALITY_DIR
    try:
        names = os.listdir(quality_dir)
    except OSError:
        return 0
    return sum(1 for name in names if fnmatch.fnmatchcase(name, "*.json"))


def _read_stop_reason(run_dir: Path, override: str | None) -> str:
    if override is not None:
        return _squash(override) or STOP_COMPLETED
    return _squash(_read(run_dir / STOP_REASON)) or STOP_COMPLETED


def compute_verdict(
    closed_implemented: int, not_closed: int, abandoned: int, not_started: int, stop_reason: str
) -> str:
    """Apply the verdict ladder, then any stop-reason override."""
    if closed_implemented > 0 and not_closed == 0 and abandoned == 0:
        verdict = "success"
    elif closed_implemented > 0:
        verdict = "partial"
    elif not_closed > 0 or abandoned > 0:
        verdict = "phantom"
    elif not_started > 0:
        verdict = "not_started"
    else:
        verdict = "no-op"
    return STOP_REASON_VERDICTS.get(stop_reason, verdict)


def build_summary(
    run_dir: Path, *, cancelled_ids: list[str], stop_reason: str | None = None
) -> AutodevSummary:
    """Summarise a run dir whose staged issues were already promoted.

    Has one side effect: :func:`record_abandoned_inflight`.

    Args:
        run_dir: The loop's run directory.
        cancelled_ids: IDs :func:`promote_staged` promoted as cancelled.
        stop_reason: Overrides ``autodev-stop-reason`` when given.
    """
    passed_ids = _ledger(run_dir, PASSED)
    skipped_lines = _records(_read(run_dir / SKIPPED))
    skipped_ids = _sorted_unique(
        line
        for line in _nonblank(skipped_lines)
        if "refine_failed_infra" not in line
        and not re.search(f"{_WS}(already_|blocked_by_unmet|notstarted_)", line)
    )
    infra_skipped_ids = _sorted_unique(
        _nonblank(_field(line, 0) for line in skipped_lines if "refine_failed_infra" in line)
    )
    already_resolved_ids = _sorted_unique(
        _labelled(line).replace("already_", "", 1)
        for line in skipped_lines
        if re.search(f"{_WS}already_", line)
    )
    blocked_by_unmet_ids = _sorted_unique(
        _nonblank(
            _field(line, 0) for line in skipped_lines if re.search(f"{_WS}blocked_by_unmet", line)
        )
    )
    not_started_ids = _sorted_unique(
        _nonblank(_labelled(line) for line in _records(_read(run_dir / NOT_STARTED)))
    )
    proof_gate_lines = _nonblank(_records(_read(run_dir / PROOF_GATE_INFRA)))

    abandoned = 1 if record_abandoned_inflight(run_dir) else 0
    unverified_ids = _ledger(run_dir, UNVERIFIED)
    stop = _read_stop_reason(run_dir, stop_reason)
    closed = len(passed_ids)
    closed_cancelled = len(cancelled_ids)
    closed_implemented = closed - closed_cancelled
    not_started = len(not_started_ids)

    summary = AutodevSummary(
        verdict=compute_verdict(
            closed_implemented, len(unverified_ids), abandoned, not_started, stop
        ),
        closed=closed,
        not_closed=len(unverified_ids),
        skipped=len(skipped_ids),
        gate_blocked=0,
        decision_unresolved=0,
        not_started=not_started,
        inflight_unresolved=abandoned,
        abandoned=abandoned,
        stop_reason=stop,
        proof_gate_infra=len(proof_gate_lines),
        closed_implemented=closed_implemented,
        closed_cancelled=closed_cancelled,
        quality_failed=_count_matching(run_dir, UNVERIFIED, "quality_gate_failed"),
        quality_gate_infra=_count_matching(run_dir, UNVERIFIED, "quality_gate_infra"),
        passed_ids=passed_ids,
        cancelled_ids=list(cancelled_ids),
        skipped_ids=skipped_ids,
        infra_skipped_ids=infra_skipped_ids,
        already_resolved_ids=already_resolved_ids,
        blocked_by_unmet_ids=blocked_by_unmet_ids,
        gate_blocked_ids=_ledger(run_dir, GATE_BLOCKED),
        decision_unresolved_ids=_ledger(run_dir, DECISION_UNRESOLVED),
        not_started_ids=not_started_ids,
        spike_inconclusive=",".join(_ledger(run_dir, SPIKE_INCONCLUSIVE)),
        proposal_unsound=",".join(_ledger(run_dir, PROPOSAL_UNSOUND)),
        proof_gate_infra_ids=_sorted_unique(proof_gate_lines),
        quality_failed_list=_quality_list(run_dir, "quality_gate_failed"),
        quality_gate_infra_list=_quality_list(run_dir, "quality_gate_infra"),
        quality_gated=_quality_gated(run_dir),
        unverified_display_ids=[i for i in unverified_ids if not _QUALITY_REASON_RE.search(i)],
        pending_ids=_nonblank(_records(_read(run_dir / QUEUE))),
    )
    summary.gate_blocked = len(summary.gate_blocked_ids)
    summary.decision_unresolved = len(summary.decision_unresolved_ids)
    summary.pending = len(summary.pending_ids)
    return summary


# -------------------------------------------------------------------- report


def _list_count(joined: str) -> int:
    """Entries in a comma-joined list, counted the way ``tr ',' '\\n' | wc -l`` does."""
    return joined.count(",") + 1


def render_report(summary: AutodevSummary) -> str:
    """Render the operator-facing ``=== Autodev Summary ===`` block."""
    s = summary
    passed = ",".join(s.passed_ids) or "none"
    out = ["\n=== Autodev Summary ===\n\n"]
    if s.closed_cancelled > 0:
        out.append(
            f"Passed       ({s.closed}): {passed}  ({s.closed_implemented} implemented, "
            f"{s.closed_cancelled} cancelled: {','.join(s.cancelled_ids)})\n"
        )
    else:
        out.append(f"Passed       ({s.closed}): {passed}\n")
    out.append(f"Skipped      ({s.skipped}): {','.join(s.skipped_ids) or 'none'}\n")
    if s.infra_skipped_ids:
        out.append(
            f"Infra-skipped ({len(s.infra_skipped_ids)}): {','.join(s.infra_skipped_ids)}"
            "  (transient kill — just re-run)\n"
        )
    if s.already_resolved_ids:
        out.append(
            f"Already-resolved ({len(s.already_resolved_ids)}): "
            f"{','.join(s.already_resolved_ids)}"
            "  (pre-flight skip — no refinement attempted)\n"
        )
    if s.blocked_by_unmet_ids:
        out.append(
            f"Blocked-by-unmet ({len(s.blocked_by_unmet_ids)}): "
            f"{','.join(s.blocked_by_unmet_ids)}"
            "  (unmet blocked_by deps — resolve them, then re-run)\n"
        )
    if s.gate_blocked > 0:
        out.append(
            f"Gate-blocked ({s.gate_blocked}): {','.join(s.gate_blocked_ids)}"
            "  (prove deps with /ll:explore-api, then re-run)\n"
        )
    if s.decision_unresolved > 0:
        out.append(
            f"Decision-unresolved ({s.decision_unresolved}): "
            f"{','.join(s.decision_unresolved_ids)}"
            "  (resolve with /ll:decide-issue, then re-run)\n"
        )
    if s.spike_inconclusive:
        out.append(
            f"Spike-inconclusive ({_list_count(s.spike_inconclusive)}): {s.spike_inconclusive}"
            "  (fix the cause, run /ll:spike <ID> --force, then re-run)\n"
        )
    if s.proposal_unsound:
        out.append(
            f"Proposal-unsound ({_list_count(s.proposal_unsound)}): {s.proposal_unsound}"
            "  (selected proposal refuted, no alternative; revise ## Proposed Solution,"
            " then re-run)\n"
        )
    if s.proof_gate_infra_ids:
        out.append(
            f"Proof-gate-infra [infra] ({s.proof_gate_infra}): {','.join(s.proof_gate_infra_ids)}"
            "  (check-gate produced no verdict before implement; retry later)\n"
        )
    if s.not_started > 0:
        out.append(
            f"Not-started  ({s.not_started}): {','.join(s.not_started_ids)}"
            "  (never reached implementation — Phase 1 rejected)\n"
        )
    if s.quality_failed > 0:
        out.append(
            f"Quality-failed ({s.quality_failed}): {s.quality_failed_list}"
            "  (marked done but gate failed — review these commits; rerun will not re-gate)\n"
        )
    if s.quality_gate_infra > 0:
        out.append(
            f"Quality-gate-infra [infra] ({s.quality_gate_infra}): {s.quality_gate_infra_list}"
            "  (gate crashed — re-run the oracle manually)\n"
        )
    if s.quality_gated > 0 and s.quality_failed + s.quality_gate_infra == s.quality_gated:
        out.append(
            "Hint: every gated issue failed the quality gate — if the base branch is already"
            " red, re-run with --context quality_gate=false (auto-refine-and-implement"
            " forwards quality_gate too)\n"
        )
    if s.unverified_display_ids:
        out.append(
            f"Unverified   ({len(s.unverified_display_ids)}): "
            f"{','.join(s.unverified_display_ids)}"
            "  (threshold passed; implementation did not close — re-queue to retry)\n"
        )
    if s.stop_reason != STOP_COMPLETED:
        out.append(
            f"Stopped early: {s.stop_reason} — pending ({s.pending}): "
            f"{','.join(s.pending_ids) or 'none'}  (re-run to continue)\n"
        )
    out.append("\n")
    return "".join(out)


def write_summary(run_dir: Path, summary: AutodevSummary) -> Path:
    """Atomically write ``summary.json`` into *run_dir*; return its path."""
    path = run_dir / SUMMARY
    atomic_write(path, summary.to_json(), shared_mode=True)
    return path


def finalize(
    run_dir: Path,
    *,
    quality_gate: bool,
    status_of: StatusResolver,
    stop_reason: str | None = None,
) -> tuple[AutodevSummary, str]:
    """Promote, summarise, and write ``summary.json``; return the summary and report."""
    cancelled = promote_staged(run_dir, quality_gate=quality_gate, status_of=status_of)
    summary = build_summary(run_dir, cancelled_ids=cancelled, stop_reason=stop_reason)
    return summary, render_report(summary)


# ----------------------------------------------------------------------- cli


def build_parser() -> argparse.ArgumentParser:
    """Build the ``python3 -m little_loops.autodev_summary`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="python3 -m little_loops.autodev_summary",
        description=(
            "Finalize an autodev run: promote verified closures, print the run "
            "report, and write summary.json. Exit 0 = done, 1 = phantom, 2 = error."
        ),
    )
    parser.add_argument("--run-dir", type=Path, required=True, help="the loop's ${context.run_dir}")
    parser.add_argument(
        "--quality-gate",
        default="true",
        help="the loop's quality_gate context value (false/0/no/off disable the gate)",
    )
    parser.add_argument(
        "--stop-reason",
        default=None,
        help="override autodev-stop-reason (e.g. max_steps from the step-cap handler)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="project whose issue files are read (default: current directory)",
    )
    return parser


def _emit(text: str) -> None:
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        sys.stdout.write(text)
    else:
        sys.stdout.flush()
        buffer.write(text.encode("utf-8", errors="surrogateescape"))
    sys.stdout.flush()


def main(argv: list[str] | None = None, *, status_of: StatusResolver | None = None) -> int:
    """CLI entry point; *status_of* replaces frontmatter status lookup (tests)."""
    args = build_parser().parse_args(argv)
    run_dir: Path = args.run_dir
    try:
        if not run_dir.is_dir():
            raise AutodevSummaryError(f"run dir not found: {run_dir}")
        resolver = status_of or issue_status_resolver(args.project_root or Path.cwd())
        summary, report = finalize(
            run_dir,
            quality_gate=quality_gate_enabled(args.quality_gate),
            status_of=resolver,
            stop_reason=args.stop_reason,
        )
        _emit(report)
        write_summary(run_dir, summary)
    except (AutodevSummaryError, OSError, ValueError) as exc:
        print(f"autodev_summary: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return summary.exit_code


if __name__ == "__main__":
    sys.exit(main())
