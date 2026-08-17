"""ll-harness: One-shot runner evaluation CLI (FEAT-1851)."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from little_loops.cli.output import configure_output, print_json, status_block, use_color_enabled
from little_loops.fsm.evaluators import EvaluationResult, evaluate_llm_structured
from little_loops.fsm.verdicts import is_abstention_verdict
from little_loops.logger import Logger
from little_loops.runner_spec import ActionSpec, RunnerResult, RunnerType, run_action
from little_loops.session_store import (
    DEFAULT_DB_PATH,
    cli_event_context,
    connect,
    record_harness_event,
)
from little_loops.skill_expander import _find_plugin_root, _resolve_content_path

__all__ = [
    "RunnerResult",
    "DslTask",
    "main_harness",
]


def _now_iso() -> str:
    """Return the current UTC time as a Z-suffixed ISO 8601 string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_output(*args: str) -> str | None:
    """Return stripped stdout of a git command, or None on any failure."""
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _git_dirty() -> bool | None:
    """Return whether the working tree has tracked modifications, or None on failure.

    ENH-141: pairs with the v38 ``base_dirty`` column on ``orchestration_runs``
    and ``_is_main_repo_dirty`` in parallel/worker_pool. Uses
    ``git status --porcelain --untracked-files=no`` so untracked scratch files
    don't pollute the result (mirroring the rationale at worker_pool.py). Returns
    ``True`` if there are tracked modifications, ``False`` if clean, ``None``
    when git is unavailable, the call times out, or the process returns non-zero
    (not a repo, etc.). The NULL-means-unknown contract matches
    ``issue_manager._resolve_base_state``.

    Best-effort: any failure (including subprocess oddities under test mocks)
    yields ``None`` so callers can pass it through without aborting.
    """
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:  # noqa: BLE001 — best-effort telemetry, never raises
        return None
    try:
        if proc.returncode != 0:
            return None
        return bool(proc.stdout.strip())
    except Exception:  # noqa: BLE001 — defensive against mocked return shapes
        return None


def _hash_bytes(data: bytes) -> str:
    """Return the 16-char SHA-256 prefix of *data* — ENH-141 content fingerprint."""
    return hashlib.sha256(data).hexdigest()[:16]


def _hash_file(path: Path) -> str | None:
    """Return the 16-char SHA-256 prefix of *path*'s bytes, or None on read failure.

    ENH-141: used to populate ``target_content_hash`` for file-shaped runners
    (skill, dsl-task). Returns None on OSError so callers can fall back to NULL
    without affecting the harness exit code.
    """
    try:
        return _hash_bytes(path.read_bytes())
    except OSError:
        return None


def _resolve_skill_target_path(name: str) -> Path | None:
    """Return the resolved path of skill *name*, or None if unresolvable.

    ENH-141: thin wrapper over :func:`_resolve_content_path` so the harness
    call sites don't need to know about the plugin-root convention.
    """
    try:
        return _resolve_content_path(_find_plugin_root(), name)
    except OSError:
        return None


def _record_harness_event(
    *,
    runner: str,
    target: str,
    exit_code: int | None,
    semantic_verdict: str | None,
    semantic_passed: bool | None,
    timed_out: bool,
    duration_ms: int,
    parent_id: int | None = None,
    target_content_hash: str | None = None,
    target_path: str | None = None,
    dirty: int | None = None,
) -> None:
    """Best-effort write to ``harness_events`` — never affects the harness exit code.

    ENH-141 adds ``target_content_hash`` / ``target_path`` / ``dirty`` kwargs;
    all three default to None so existing callers (v38 row shape) continue to
    work unchanged.
    """
    with contextlib.suppress(Exception):
        record_harness_event(
            DEFAULT_DB_PATH,
            ts=_now_iso(),
            runner=runner,
            target=target,
            exit_code=exit_code,
            semantic_verdict=semantic_verdict,
            semantic_passed=semantic_passed,
            timed_out=timed_out,
            duration_ms=duration_ms,
            head_sha=_git_output("rev-parse", "HEAD"),
            branch=_git_output("rev-parse", "--abbrev-ref", "HEAD"),
            parent_id=parent_id,
            target_content_hash=target_content_hash,
            target_path=target_path,
            dirty=dirty,
        )


@dataclass
class DslTask:
    """A single DSL evaluation task loaded from a task YAML file."""

    prompt: str
    blanks: list[str]
    expected: dict[str, str]
    source_dsl: str
    task_type: str
    source_file: str = ""
    generated_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DslTask:
        return cls(
            prompt=data["prompt"],
            blanks=data.get("blanks") or [],
            expected=data.get("expected") or {},
            source_dsl=data.get("source_dsl", ""),
            task_type=data.get("task_type", ""),
            source_file=data.get("source_file", ""),
            generated_at=data.get("generated_at", ""),
        )


class GradeStatus(Enum):
    """Per-task `expected:` grading outcome (BUG-3196)."""

    PASS = "pass"  # every expected key matched
    FAIL = "fail"  # answer parsed, >=1 key mismatched
    UNPARSEABLE = "unparseable"  # expected declared, no answer object recovered -> counts FAIL
    UNGRADED = "ungraded"  # no expected and no --semantic -> excluded from denominator
    MALFORMED = "malformed"  # task file unloadable / expected not a mapping -> counts FAIL


@dataclass(frozen=True)
class ExpectedGrade:
    """Result of comparing one response against one task's `expected:` mapping."""

    status: GradeStatus
    matched: dict[str, str]
    mismatched: dict[str, tuple[str, str | None]]
    raw_answer: str | None

    @property
    def passed(self) -> bool:
        return self.status is GradeStatus.PASS


_FENCED_JSON_RE = re.compile(r"```json\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _try_parse_answer_object(text: str) -> dict[str, object] | None:
    """Parse *text* as a flat JSON object (scalar values only), or return None."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    for value in obj.values():
        if isinstance(value, (dict, list)):
            return None
    return obj


def _iter_balanced_brace_spans(text: str) -> list[str]:
    """Return every top-level balanced ``{...}`` substring of *text*, in order."""
    spans: list[str] = []
    depth = 0
    start: int | None = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    spans.append(text[start : i + 1])
                    start = None
    return spans


def _extract_answer_object(
    stdout: str, expected_keys: set[str] | None = None
) -> dict[str, object] | None:
    """Recover the model's answer object from *stdout*.

    Tries the last fenced ```json block first (accepted unconditionally), then
    falls back to the last balanced ``{...}`` span. The bare-brace fallback is
    accepted only if its key set intersects *expected_keys* — otherwise an
    unrelated JSON payload already in the response (e.g. a `--semantic` judge
    verdict) would be misread as the answer (BUG-3196 AC2b).
    """
    fenced_matches = _FENCED_JSON_RE.findall(stdout)
    if fenced_matches:
        candidate = _try_parse_answer_object(fenced_matches[-1])
        if candidate is not None:
            return candidate

    spans = _iter_balanced_brace_spans(stdout)
    if not spans:
        return None
    candidate = _try_parse_answer_object(spans[-1])
    if candidate is None:
        return None
    if expected_keys is not None and not (set(candidate.keys()) & expected_keys):
        return None
    return candidate


def _normalize_answer(value: object) -> str:
    """Normalize one answer-object value for exact comparison.

    Strips surrounding whitespace and one layer of matching outer quotes or
    backticks. `bool` is the one documented case-significance exception: it
    lower-cases to `"true"`/`"false"` so a JSON `true` matches a YAML `true`
    (both are the same value with different Python reprs).
    """
    if isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = str(value).strip()
    if len(text) >= 2:
        for quote in ('"', "'", "`"):
            if text.startswith(quote) and text.endswith(quote):
                text = text[1:-1]
                break
    return text


def _grade_expected(stdout: str, expected: object) -> ExpectedGrade:
    """Grade *stdout* against a task's `expected` mapping (BUG-3196)."""
    if not isinstance(expected, dict):
        return ExpectedGrade(
            status=GradeStatus.MALFORMED, matched={}, mismatched={}, raw_answer=None
        )

    expected_keys = set(expected.keys())
    answer = _extract_answer_object(stdout, expected_keys)
    if answer is None:
        return ExpectedGrade(
            status=GradeStatus.UNPARSEABLE, matched={}, mismatched={}, raw_answer=None
        )

    matched: dict[str, str] = {}
    mismatched: dict[str, tuple[str, str | None]] = {}
    for key, expected_value in expected.items():
        expected_norm = _normalize_answer(expected_value)
        if key in answer:
            actual_norm = _normalize_answer(answer[key])
            if actual_norm == expected_norm:
                matched[key] = actual_norm
            else:
                mismatched[key] = (expected_norm, actual_norm)
        else:
            mismatched[key] = (expected_norm, None)

    status = GradeStatus.PASS if not mismatched else GradeStatus.FAIL
    return ExpectedGrade(
        status=status, matched=matched, mismatched=mismatched, raw_answer=json.dumps(answer)
    )


def _answer_contract_suffix(blanks: list[str], expected: object) -> str:
    """Build the text appended to a DSL task's prompt (replaces the list-repr hint)."""
    if isinstance(expected, dict) and expected:
        keys = ", ".join(sorted(expected.keys()))
        return (
            "\n\nAnswer contract: end your response with a single fenced "
            f"```json code block containing an object with exactly these keys: {keys}."
        )
    if blanks:
        return f"\n\nBlanks to fill: {', '.join(blanks)}"
    return ""


def _load_task(path: Path) -> DslTask | None:
    """Load one DSL task YAML, returning None on any load/shape error (BUG-3196 AC5e)."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return DslTask.from_dict(data)
    except (KeyError, TypeError):
        return None


def _build_harness_parser() -> argparse.ArgumentParser:
    """Build the ll-harness argument parser (exposed for testing)."""
    parser = argparse.ArgumentParser(
        prog="ll-harness",
        description="One-shot runner evaluation for little-loops skills and commands",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ll-harness skill check-code
  ll-harness cmd "echo hello" --exit-code 0
  ll-harness mcp my-server:my-tool --args '{"key": "val"}' --semantic "tool returned results"
  ll-harness prompt "What is 2+2?" --semantic "response contains a number"
  ll-harness cmd "echo hello" --issue-id ENH-1234 --output json  # includes prepatch_evidence when a bundle exists
  ll-harness skill check-code --output json  # includes history_pass_rate/history_abstention_rate (target-scoped, last 30d) once enough runs exist

Exit codes:
  0  PASS
  1  FAIL
  2  Internal error / timeout
  3  ABSTAIN (no failure, but the semantic judge could not evaluate the check)
""",
    )

    subparsers = parser.add_subparsers(dest="runner", metavar="RUNNER")
    subparsers.required = True

    def _add_evaluator_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--exit-code",
            dest="exit_code",
            type=int,
            default=None,
            metavar="INT",
            help="Expected exit code (default: not checked)",
        )
        p.add_argument(
            "--semantic",
            type=str,
            default=None,
            metavar="TEXT",
            help="Natural-language criterion for output evaluation",
        )
        p.add_argument(
            "--timeout",
            type=int,
            default=120,
            metavar="SECONDS",
            help="Runner timeout in seconds (default: 120)",
        )
        p.add_argument(
            "--output",
            choices=["text", "json"],
            default="text",
            help="Output format (default: text)",
        )
        p.add_argument(
            "--verbose",
            action="store_true",
            help="Show full captured output even on pass",
        )
        p.add_argument(
            "--issue-id",
            dest="issue_id",
            type=str,
            default=None,
            metavar="ID",
            help=(
                "Issue ID (ENH-2998) to look up a persisted pre-patch check "
                "evidence bundle for, from .ll/history.db. Read-only: does "
                "not run the check. Absent when no bundle is found or when "
                "unset (includes prepatch_evidence key in --output json)."
            ),
        )

    def _add_trace_flags(p: argparse.ArgumentParser) -> None:
        """FEAT-2878: trace-assertion mode flags, layered onto SKILL/PROMPT.

        Opt-in via ``--trace-mode``; the default (unset) run is unaffected.
        """
        p.add_argument(
            "--trace-mode",
            action="store_true",
            help=(
                "Run against a scoped temporary workspace and assert on the "
                "live ordered tool-call trace instead of stdout (FEAT-2878)"
            ),
        )
        p.add_argument(
            "--require-order",
            type=str,
            default=None,
            metavar="TOOL,TOOL,...",
            help="Comma-separated tool names that must appear in this relative order",
        )
        p.add_argument(
            "--require-artifact",
            action="append",
            default=[],
            metavar="PATH",
            help="Path (relative to the workspace) that must have been written; repeatable",
        )
        p.add_argument(
            "--forbid-path",
            action="append",
            default=[],
            metavar="PATH",
            help="Path (relative to the workspace) that must NOT have been written; repeatable",
        )
        p.add_argument(
            "--keep-workspace",
            action="store_true",
            help="Do not delete the scoped temporary workspace after the run",
        )
        p.add_argument(
            "--hosts",
            type=str,
            default=None,
            metavar="HOST,HOST,...",
            help=(
                "Opt-in multi-host divergence: comma-separated host names to run "
                "against (default: the single resolved host). Hosts that are "
                "unconfigured or unavailable are skipped with a reported reason."
            ),
        )

    skill_p = subparsers.add_parser(
        "skill",
        help="Invoke a little-loops skill",
        description="Invoke a little-loops skill via the active host CLI",
    )
    skill_p.add_argument("target", help="Skill name (e.g. check-code, refine-issue)")
    skill_p.add_argument(
        "runner_args",
        nargs="*",
        help="Additional arguments passed to the skill",
    )
    _add_evaluator_flags(skill_p)
    _add_trace_flags(skill_p)

    cmd_p = subparsers.add_parser(
        "cmd",
        help="Run a shell command",
        description="Run a shell command and capture its output",
    )
    cmd_p.add_argument("target", help="Shell command to execute")
    _add_evaluator_flags(cmd_p)

    mcp_p = subparsers.add_parser(
        "mcp",
        help="Call an MCP tool",
        description="Call an MCP tool via JSON-RPC",
    )
    mcp_p.add_argument("target", help="MCP server and tool (format: server:tool)")
    mcp_p.add_argument(
        "--args",
        dest="mcp_args",
        type=str,
        default="{}",
        metavar="JSON",
        help="JSON arguments to pass to the MCP tool (default: {})",
    )
    _add_evaluator_flags(mcp_p)

    prompt_p = subparsers.add_parser(
        "prompt",
        help="Send a raw prompt to Claude",
        description="Send a raw prompt to Claude via the active host CLI",
    )
    prompt_p.add_argument("target", help="Prompt text to send")
    prompt_p.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help="Override Claude model (e.g. claude-haiku-4-5-20251001)",
    )
    _add_evaluator_flags(prompt_p)

    dsl_p = subparsers.add_parser(
        "dsl",
        help="Run a DSL task set and report pass rates by model",
        description="Load and run DSL eval task YAML files, reporting pass rate with Wilson CI",
    )
    dsl_p.add_argument("path", help="DSL task file or directory of .yaml task files")
    dsl_p.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help="Override Claude model (e.g. claude-haiku-4-5-20251001)",
    )
    _add_evaluator_flags(dsl_p)

    return parser


def _parse_harness_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse argv into a Namespace (exposed for testing)."""
    return _build_harness_parser().parse_args(argv)


@dataclass
class HarnessEvalOutcome:
    """Evaluation outcome carried alongside `_evaluate_and_report()`'s exit code."""

    passed: bool
    verdict: str | None
    eval_result: EvaluationResult | None
    abstained: bool = False


def _read_prepatch_evidence(issue_id: str | None) -> dict | None:
    """Read the persisted pre-patch check bundle (ENH-2998) for *issue_id*, if any.

    Reads-only: does not call `run_prepatch_check()` and does not re-implement
    the check. `ll-harness` is hand-run and has no `run_dir`, so
    `.ll/history.db` is the only surface it can discover a bundle by issue ID.
    """
    if not issue_id:
        return None
    from little_loops.history_reader import read_prepatch_evidence

    return read_prepatch_evidence(issue_id, db=DEFAULT_DB_PATH)


# ENH-3223: window and noise-floor for the historical rate read below. Both are
# display-only tuning knobs -- a wrong value degrades signal quality but cannot
# change an exit code, so they are picked pragmatically rather than measured.
_HISTORY_WINDOW_DAYS = 30
_HISTORY_MIN_SCORED = 3


def _read_target_history(target: str) -> dict | None:
    """Best-effort read of historical pass/abstention rates for *target* (ENH-3223).

    Target-scoped, not criterion-scoped: ``semantic_prompt`` is never written by
    any caller today, so this cannot attribute abstention to a specific
    ``--semantic`` string, only to the target as a whole (see issue Summary).
    Called from `_evaluate_and_report()` before that run's own
    `_record_harness_event()` call, so the reported figures exclude the current
    run. Each rate is suppressed independently when its own denominator is
    below `_HISTORY_MIN_SCORED` -- a single row would render as a meaningless
    0%/100% figure (AC7). Returns None (never raises) when neither rate clears
    the threshold, mirroring `_read_prepatch_evidence()`'s absent-is-not-an-error
    contract.
    """
    from little_loops.history_reader import (
        harness_eval_abstention_rate,
        harness_eval_pass_rate,
        recent_harness_events,
    )
    from little_loops.session_store import resolve_history_db

    # `_connect_readonly()` opens whatever path it is handed as-is -- it does
    # not re-resolve a default-shaped path through the env/config chain
    # (root-anchored callers like `ll-mcp`'s `history_search` rely on that,
    # BUG-3181). Resolve once here, the same way `_record_harness_event()`'s
    # `connect(DEFAULT_DB_PATH)` resolves for the write side, so this read
    # lands on the same database file.
    db_path = resolve_history_db(DEFAULT_DB_PATH)
    since = (datetime.now(UTC) - timedelta(days=_HISTORY_WINDOW_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    # `harness_eval_pass_rate()`/`harness_eval_abstention_rate()` return only a
    # rate, not the row count behind it -- pull the events once to derive both
    # denominators for the AC7 suppression check without duplicating their SQL.
    events = recent_harness_events(target=target, since=since, limit=1000, db=db_path)
    pass_scored = sum(1 for e in events if e.semantic_passed is not None)
    judged_scored = sum(1 for e in events if e.semantic_verdict is not None)

    history: dict[str, Any] = {}
    if pass_scored >= _HISTORY_MIN_SCORED:
        rate = harness_eval_pass_rate(target, since=since, db=db_path)
        if rate is not None:
            history["history_pass_rate"] = rate
            history["history_pass_rate_runs"] = pass_scored
    if judged_scored >= _HISTORY_MIN_SCORED:
        abstention = harness_eval_abstention_rate(target, since=since, db=db_path)
        if abstention is not None:
            history["history_abstention_rate"] = abstention["abstention_rate"]
            history["history_judged_runs"] = judged_scored
    if not history:
        return None
    history["history_since"] = since
    return history


def _format_target_history_line(history: dict) -> str:
    """Render `_read_target_history()`'s dict as one status line (target-scoped)."""
    parts = []
    if "history_pass_rate" in history:
        parts.append(
            f"pass {history['history_pass_rate']:.0%} ({history['history_pass_rate_runs']} runs)"
        )
    if "history_abstention_rate" in history:
        parts.append(
            f"abstention {history['history_abstention_rate']:.0%} "
            f"({history['history_judged_runs']} judged)"
        )
    since_date = history["history_since"][:10]
    return f"Target history since {since_date}: " + ", ".join(parts)


def _evaluate_and_report(
    runner_label: str,
    result: RunnerResult,
    args: argparse.Namespace,
    *,
    expected_grade: ExpectedGrade | None = None,
    skip_history: bool = False,
) -> tuple[int, HarnessEvalOutcome]:
    """Evaluate result against criteria and print the report. Returns (exit_code, outcome)."""
    if result.timed_out:
        _report(runner_label, result, args, error_msg="timeout")
        return 2, HarnessEvalOutcome(passed=False, verdict=None, eval_result=None)
    if result.error is not None:
        _report(runner_label, result, args, error_msg=result.error)
        return 2, HarnessEvalOutcome(passed=False, verdict=None, eval_result=None)

    passed = True
    abstained = False
    exit_code_display = str(result.exit_code)
    semantic_display = "[not checked]"
    eval_result: EvaluationResult | None = None

    if args.exit_code is not None:
        if result.exit_code != args.exit_code:
            passed = False
        exit_code_display = f"{result.exit_code} (expected {args.exit_code})"

    # BUG-3196: an `expected:` mismatch is a hard failure that outranks
    # abstention (folded before the --semantic block, same as --exit-code).
    # UNGRADED is deliberately excluded here — it carries no verdict of its
    # own and must not force `passed = False`; cmd_dsl reads its status
    # directly to exclude the task from the denominator instead.
    if (
        expected_grade is not None
        and expected_grade.status is not GradeStatus.UNGRADED
        and not expected_grade.passed
    ):
        passed = False

    if args.semantic is not None:
        eval_result = evaluate_llm_structured(output=result.stdout, prompt=args.semantic)
        semantic_display = eval_result.verdict
        # ENH-3185 AC9: an abstention is neither a pass nor a failure — report
        # it separately rather than folding it into `passed = False`. Precedence
        # is fail > abstain > pass, so a mixed exit_code-fail + semantic-abstain
        # run still reports FAIL/exit 1.
        if is_abstention_verdict(eval_result.verdict):
            abstained = True
        elif eval_result.verdict != "yes":
            passed = False

    if not passed:
        overall = "FAIL"
    elif abstained:
        overall = "ABSTAIN"
    else:
        overall = "PASS"
    show_output = not passed or args.verbose

    # ENH-2998: additive, read-only pre-patch check evidence lookup -- absent
    # (not an error) when no --issue-id was given or no bundle exists.
    prepatch_evidence = _read_prepatch_evidence(getattr(args, "issue_id", None))

    # ENH-3223: additive, read-only historical pass/abstention-rate lookup for
    # the target. `skip_history` covers the DSL per-task call path, where
    # `args.target` is the raw prompt text rather than the value actually
    # written to `harness_events.target` (task_file.name) -- see AC4.
    target_history = None if skip_history else _read_target_history(args.target)

    expected_display: str | None = None
    if expected_grade is not None:
        if expected_grade.status is GradeStatus.PASS:
            expected_display = "match"
        elif expected_grade.status is GradeStatus.UNPARSEABLE:
            expected_display = "unparseable answer"
        elif expected_grade.status is GradeStatus.MALFORMED:
            expected_display = "malformed task"
        elif expected_grade.status is GradeStatus.UNGRADED:
            expected_display = "ungraded"
        else:
            mismatches = ", ".join(
                f"{k}: expected {ev!r} got {av!r}"
                for k, (ev, av) in expected_grade.mismatched.items()
            )
            expected_display = f"mismatch ({mismatches})"

    if args.output == "json":
        payload = {
            "runner": runner_label,
            "exit_code": result.exit_code,
            "exit_code_check": exit_code_display,
            "semantic": semantic_display,
            "result": overall,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        if expected_display is not None:
            payload["expected"] = expected_display
        if prepatch_evidence is not None:
            payload["prepatch_evidence"] = prepatch_evidence
        if target_history is not None:
            payload.update(target_history)
        print_json(payload)
    else:
        status_fields = {
            "Runner": runner_label,
            "Exit": exit_code_display,
            "Semantic": semantic_display,
        }
        if expected_display is not None:
            status_fields["Expected"] = expected_display
        status_fields["Result"] = overall
        print(status_block(status_fields))
        if prepatch_evidence is not None:
            print(f"Pre-patch check: {prepatch_evidence.get('verdict', 'unknown')}")
        if target_history is not None:
            print(_format_target_history_line(target_history))
        if show_output and result.stdout:
            print("---")
            sys.stdout.write(result.stdout)
            if not result.stdout.endswith("\n"):
                print()

    outcome = HarnessEvalOutcome(
        passed=passed,
        verdict=eval_result.verdict if eval_result is not None else None,
        eval_result=eval_result,
        abstained=abstained,
    )
    # ENH-3185 AC9: 0=pass, 1=fail (unchanged), 2=harness/infra error (already
    # taken above, never reused here), 3=inconclusive (no failure, >=1 abstention).
    if not passed:
        exit_code = 1
    elif abstained:
        exit_code = 3
    else:
        exit_code = 0
    return exit_code, outcome


def _report(
    runner_label: str,
    result: RunnerResult,
    args: argparse.Namespace,
    error_msg: str,
) -> None:
    """Print an error/timeout report."""
    if args.output == "json":
        print_json(
            {
                "runner": runner_label,
                "result": "ERROR",
                "error": error_msg,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
    else:
        print(status_block({"Runner": runner_label, "Result": f"ERROR ({error_msg})"}))


def cmd_skill(args: argparse.Namespace) -> int:
    """Invoke a little-loops skill via the active host CLI."""
    runner_args: list[str] = getattr(args, "runner_args", None) or []
    runner_label = f"skill {args.target}"
    spec = ActionSpec(
        name=args.target,
        runner=RunnerType.SKILL,
        target=args.target,
        args={"runner_args": runner_args},
        timeout=args.timeout,
    )
    start = time.monotonic()
    result = run_action(spec)
    duration_ms = int((time.monotonic() - start) * 1000)
    rc, outcome = _evaluate_and_report(runner_label, result, args)
    skill_path = _resolve_skill_target_path(args.target)
    target_path_str = str(skill_path) if skill_path is not None else None
    target_hash = _hash_file(skill_path) if skill_path is not None else None
    dirty_val = _git_dirty()
    dirty_int: int | None = None if dirty_val is None else int(dirty_val)
    _record_harness_event(
        runner="skill",
        target=args.target,
        exit_code=result.exit_code,
        semantic_verdict=outcome.verdict,
        semantic_passed=None if outcome.abstained else outcome.passed,
        timed_out=result.timed_out,
        duration_ms=duration_ms,
        target_content_hash=target_hash,
        target_path=target_path_str,
        dirty=dirty_int,
    )
    return rc


def cmd_cmd(args: argparse.Namespace) -> int:
    """Run a shell command with deadlock-safe stderr draining."""
    runner_label = f"cmd {args.target}"
    spec = ActionSpec(
        name=args.target,
        runner=RunnerType.CMD,
        target=args.target,
        timeout=args.timeout,
    )
    start = time.monotonic()
    result = run_action(spec)
    duration_ms = int((time.monotonic() - start) * 1000)
    rc, outcome = _evaluate_and_report(runner_label, result, args)
    dirty_val = _git_dirty()
    dirty_int: int | None = None if dirty_val is None else int(dirty_val)
    _record_harness_event(
        runner="cmd",
        target=args.target,
        exit_code=result.exit_code,
        semantic_verdict=outcome.verdict,
        semantic_passed=None if outcome.abstained else outcome.passed,
        timed_out=result.timed_out,
        duration_ms=duration_ms,
        dirty=dirty_int,
    )
    return rc


def cmd_mcp(args: argparse.Namespace) -> int:
    """Call an MCP tool and evaluate the result."""
    if ":" not in args.target:
        print(
            f"Error: MCP target must be 'server:tool', got: {args.target!r}",
            file=sys.stderr,
        )
        return 2

    runner_label = f"mcp {args.target}"

    try:
        params: dict[str, Any] = json.loads(args.mcp_args)
    except json.JSONDecodeError as e:
        print(f"Error: --args is not valid JSON: {e}", file=sys.stderr)
        return 2

    spec = ActionSpec(
        name=args.target,
        runner=RunnerType.MCP,
        target=args.target,
        args={"mcp_params": params},
        timeout=args.timeout,
    )
    start = time.monotonic()
    result = run_action(spec)
    duration_ms = int((time.monotonic() - start) * 1000)
    rc, outcome = _evaluate_and_report(runner_label, result, args)
    dirty_val = _git_dirty()
    dirty_int: int | None = None if dirty_val is None else int(dirty_val)
    _record_harness_event(
        runner="mcp",
        target=args.target,
        exit_code=result.exit_code,
        semantic_verdict=outcome.verdict,
        semantic_passed=None if outcome.abstained else outcome.passed,
        timed_out=result.timed_out,
        duration_ms=duration_ms,
        dirty=dirty_int,
    )
    return rc


def _run_prompt_action(target: str, args: argparse.Namespace) -> tuple[RunnerResult, int]:
    """Run a PROMPT action and return (result, duration_ms).

    Extracted from `cmd_prompt` (BUG-3196) so `cmd_dsl` can grade `result.stdout`
    against a task's `expected:` mapping — `cmd_prompt` itself returns only `int`.
    """
    label_text = target[:40] + ("..." if len(target) > 40 else "")
    spec = ActionSpec(
        name=label_text,
        runner=RunnerType.PROMPT,
        target=target,
        args={"model": args.model},
        timeout=args.timeout,
    )
    start = time.monotonic()
    result = run_action(spec)
    duration_ms = int((time.monotonic() - start) * 1000)
    return result, duration_ms


def cmd_prompt(args: argparse.Namespace) -> int:
    """Send a raw prompt to Claude and evaluate the response."""
    label_text = args.target[:40] + ("..." if len(args.target) > 40 else "")
    runner_label = f"prompt {label_text}"
    result, duration_ms = _run_prompt_action(args.target, args)
    rc, outcome = _evaluate_and_report(runner_label, result, args)
    dirty_val = _git_dirty()
    dirty_int: int | None = None if dirty_val is None else int(dirty_val)
    _record_harness_event(
        runner="prompt",
        target=args.target,
        exit_code=result.exit_code,
        semantic_verdict=outcome.verdict,
        semantic_passed=None if outcome.abstained else outcome.passed,
        timed_out=result.timed_out,
        duration_ms=duration_ms,
        target_content_hash=_hash_bytes(args.target.encode("utf-8")),
        dirty=dirty_int,
    )
    return rc


def cmd_dsl(args: argparse.Namespace) -> int:  # noqa: PLR0912, PLR0915 — grading state machine
    """Run a DSL task set, grading each task against its own `expected:` mapping.

    BUG-3196: a flagless run previously reported a 100% pass rate unconditionally.
    See the issue's "Decision: exit codes" table for the full precedence.
    """
    from little_loops.stats import wilson_ci

    path = Path(args.path)
    if path.is_dir():
        task_files = sorted(path.glob("*.yaml"))
    elif path.is_file():
        task_files = [path]
    else:
        print(f"Error: DSL path not found: {path}", file=sys.stderr)
        return 2

    if not task_files:
        print(f"Error: no .yaml task files found in {path}", file=sys.stderr)
        return 2

    total = 0
    graded_pass = 0
    graded_total = 0
    ungraded_count = 0
    abstain_count = 0
    errored_count = 0
    failures: list[str] = []

    aggregate_ts = _now_iso()
    aggregate_id: int | None = None
    dirty_val = _git_dirty()
    dirty_int: int | None = None if dirty_val is None else int(dirty_val)
    with contextlib.suppress(Exception):
        record_harness_event(
            DEFAULT_DB_PATH,
            ts=aggregate_ts,
            runner="dsl",
            target=str(path),
            head_sha=_git_output("rev-parse", "HEAD"),
            branch=_git_output("rev-parse", "--abbrev-ref", "HEAD"),
            target_path=str(path),
            target_content_hash=_hash_file(path),
            dirty=dirty_int,
        )
        conn = connect(DEFAULT_DB_PATH)
        try:
            row = conn.execute("SELECT id FROM harness_events ORDER BY id DESC LIMIT 1").fetchone()
            aggregate_id = row[0] if row is not None else None
        finally:
            conn.close()

    for task_file in task_files:
        total += 1
        task = _load_task(task_file)

        if task is None:
            failures.append(f"{task_file.name} (malformed task file)")
            graded_total += 1
            _record_harness_event(
                runner="dsl-task",
                target=task_file.name,
                exit_code=1,
                semantic_verdict=None,
                semantic_passed=False,
                timed_out=False,
                duration_ms=0,
                parent_id=aggregate_id,
                target_path=str(task_file),
                target_content_hash=_hash_file(task_file),
                dirty=dirty_int,
            )
            continue

        has_expected = bool(task.expected)
        prompt_text = task.prompt + _answer_contract_suffix(task.blanks, task.expected)

        task_args = argparse.Namespace(
            target=prompt_text,
            exit_code=args.exit_code,
            semantic=args.semantic,
            timeout=args.timeout,
            output=args.output,
            verbose=args.verbose,
            model=args.model,
            issue_id=None,
        )
        result, duration_ms = _run_prompt_action(prompt_text, task_args)

        expected_grade: ExpectedGrade | None
        if has_expected:
            expected_grade = _grade_expected(result.stdout, task.expected)
        elif args.semantic is None:
            # BUG-3196: no `expected:` and no `--semantic` — nothing can grade
            # this task. Ungraded, not the false pass the bug reported.
            expected_grade = ExpectedGrade(
                status=GradeStatus.UNGRADED, matched={}, mismatched={}, raw_answer=None
            )
        else:
            expected_grade = None

        label_text = prompt_text[:40] + ("..." if len(prompt_text) > 40 else "")
        runner_label = f"prompt {label_text}"
        rc, outcome = _evaluate_and_report(
            runner_label, result, task_args, expected_grade=expected_grade, skip_history=True
        )

        if expected_grade is not None and expected_grade.status is GradeStatus.UNGRADED:
            ungraded_count += 1
        elif rc == 2:
            errored_count += 1
        elif rc == 3:
            abstain_count += 1
        else:
            graded_total += 1
            if rc == 0:
                graded_pass += 1
            else:
                detail = ""
                if expected_grade is not None:
                    if expected_grade.status is GradeStatus.UNPARSEABLE:
                        detail = " (unparseable answer — no JSON object in response)"
                    elif expected_grade.status is GradeStatus.FAIL:
                        mismatches = ", ".join(
                            f"{k}: expected {ev!r} got {av!r}"
                            for k, (ev, av) in expected_grade.mismatched.items()
                        )
                        detail = f" ({mismatches})"
                failures.append(f"{task_file.name}{detail}")

        _record_harness_event(
            runner="dsl-task",
            target=task_file.name,
            exit_code=result.exit_code,
            semantic_verdict=outcome.verdict,
            semantic_passed=None if outcome.abstained else outcome.passed,
            timed_out=result.timed_out,
            duration_ms=duration_ms,
            parent_id=aggregate_id,
            target_path=str(task_file),
            target_content_hash=_hash_file(task_file),
            dirty=dirty_int,
        )

    def _update_aggregate(exit_code: int, semantic_passed: bool) -> None:
        with contextlib.suppress(Exception):
            conn = connect(DEFAULT_DB_PATH)
            try:
                conn.execute(
                    "UPDATE harness_events SET exit_code = ?, semantic_passed = ? WHERE id = ?",
                    (exit_code, int(semantic_passed), aggregate_id),
                )
                conn.commit()
            finally:
                conn.close()

    # BUG-3196 "Decision: exit codes" — ungraded-first, then errored, then
    # abstained, so a wholly mis-configured or wholly-broken run reports the
    # actionable `2` rather than the softer `3`.
    if ungraded_count == total:
        print(
            f"\nDSL pass-rate: n/a (all {total} task(s) ungraded — "
            "no `expected:` and no --semantic)"
        )
        _update_aggregate(2, False)
        return 2

    if graded_total == 0:
        if errored_count > 0:
            print(f"\nDSL pass-rate: n/a (all {total} task(s) errored)")
            _update_aggregate(2, False)
            return 2
        print(f"\nDSL pass-rate: n/a (all {total} task(s) abstained)")
        _update_aggregate(3, False)
        return 3

    lo, hi = wilson_ci(graded_pass, graded_total)
    lines = [f"\nDSL pass-rate: {graded_pass}/{graded_total}  [{lo:.2f}, {hi:.2f}] (95% CI)"]
    if ungraded_count:
        lines.append(
            f"  graded {graded_total} of {total} tasks — {ungraded_count} ungradable "
            "(no `expected:` and no --semantic)"
        )
    if failures:
        lines.append("  failed: " + "\n          ".join(failures))
    print("\n".join(lines))

    all_graded_passed = graded_pass == graded_total
    _update_aggregate(
        0 if (all_graded_passed and ungraded_count == 0 and abstain_count == 0) else 1,
        all_graded_passed,
    )

    if errored_count > 0:
        return 2
    if not all_graded_passed:
        return 1
    if ungraded_count > 0:
        return 1
    if abstain_count > 0:
        return 3
    return 0


def main_harness(argv: list[str] | None = None) -> int:
    """Entry point for ll-harness CLI."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-harness", sys.argv[1:]):
        args = _parse_harness_args(argv)
        configure_output()
        Logger(use_color=use_color_enabled())

        if args.runner == "skill":
            return cmd_skill(args)
        elif args.runner == "cmd":
            return cmd_cmd(args)
        elif args.runner == "mcp":
            return cmd_mcp(args)
        elif args.runner == "prompt":
            return cmd_prompt(args)
        elif args.runner == "dsl":
            return cmd_dsl(args)
        else:
            print(f"Unknown runner: {args.runner}", file=sys.stderr)
            return 2
