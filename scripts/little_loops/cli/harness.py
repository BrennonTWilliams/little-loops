"""ll-harness: One-shot runner evaluation CLI (FEAT-1851)."""

from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from little_loops.cli.history import _positive_int
from little_loops.cli.output import configure_output, print_json, status_block, use_color_enabled
from little_loops.fsm.evaluators import EvaluationResult, evaluate_llm_structured
from little_loops.fsm.schema import DEFAULT_LLM_MODEL as _JUDGE_MODEL
from little_loops.fsm.verdicts import is_abstention_verdict
from little_loops.git_operations import porcelain_paths
from little_loops.history_reader.harness import (
    BaselineConditions,
    BaselineKey,
    BaselineResult,
    baseline_for,
)
from little_loops.logger import Logger
from little_loops.runner_spec import (
    DEFAULT_STOCHASTIC_SAMPLES,
    ActionSpec,
    RunnerResult,
    RunnerType,
    is_stochastic_runner,
    run_action,
)
from little_loops.session_store import (
    DEFAULT_DB_PATH,
    cli_event_context,
    connect,
    record_attempt,
    record_harness_event,
)
from little_loops.skill_expander import _find_plugin_root, _resolve_content_path
from little_loops.stats import wilson_ci

__all__ = [
    "RunnerResult",
    "DslTask",
    "main_harness",
]


def _now_iso() -> str:
    """Return the current UTC time as a Z-suffixed ISO 8601 string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_output(*args: str) -> str | None:
    """Return stripped stdout of a git command, or None on any failure.

    ENH-3407 broadened this from ``except (OSError, subprocess.TimeoutExpired)``
    to a bare ``except Exception``, matching :func:`_git_dirty`'s existing
    "best-effort, including subprocess oddities under test mocks" contract:
    the ``--retry-of`` gate now calls this pre-run (not just inside the
    ``contextlib.suppress``-wrapped record step), so a test that globally
    patches ``subprocess.Popen`` for the runner under test can otherwise
    surface an unrelated ``ValueError`` from this git call.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:  # noqa: BLE001 — best-effort, never raises
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _git_blob(rel: str, *, ref: str = "HEAD") -> bytes | None:
    """Return the raw bytes of ``<ref>:<rel>``, or None on any failure (BUG-3479).

    Uses ``git cat-file blob`` (plumbing), not ``git show`` (porcelain):
    ``show`` honors ``.gitattributes`` textconv filters and prints a tree
    listing for a directory path, while ``cat-file blob`` emits raw bytes on
    a blob or exits non-zero on anything else. Unlike :func:`_git_output`,
    does not strip the result — an empty tracked file must hash the same via
    this path as via :func:`_hash_file`, so ``b""`` is a valid, non-None
    return. Same best-effort ``except Exception`` contract as `_git_output`.
    """
    try:
        proc = subprocess.run(
            ["git", "cat-file", "blob", f"{ref}:{rel}"],
            capture_output=True,
            text=False,
            timeout=5,
        )
    except Exception:  # noqa: BLE001 — best-effort, never raises
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


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


def _cell_key(runner: str, target: str, head_sha: str | None) -> str:
    """Return the JSON-array cell-key encoding for ``(runner, target, head_sha)`` (ENH-3407).

    ``json.dumps([runner, target, head_sha], separators=(",", ":"))`` — a JSON
    array is used because ``cmd`` targets are arbitrary shell strings (spaces,
    ``|``, ``:``, quotes) with no single safe delimiter. Deterministic,
    stdlib-only, greppable in sqlite. See :func:`record_attempt`'s docstring
    for the ``dirty``/DSL-collision caveats on this encoding.
    """
    return json.dumps([runner, target, head_sha], separators=(",", ":"))


def _retry_refusal(prior: Any, retry_of: int, cell_key: str) -> str | None:
    """Return a ``--retry-of`` refusal message, or None if *prior* is admissible (ENH-3407).

    Rule order mirrors ``cli/queue.py::_not_found_or_ambiguous``'s id-lookup
    -> persisted-state-check -> loud-refusal shape, without a ``--force``
    escape hatch (parent decision: no override).
    """
    if prior is None:
        return f"error: --retry-of {retry_of}: no such attempt"
    if prior.cell_key is None:
        return (
            f"error: --retry-of {retry_of}: attempt has no cell_key "
            "(pre-migration row or DSL aggregate row)"
        )
    if prior.superseded_by is not None:
        return f"error: --retry-of {retry_of}: already superseded by attempt {prior.superseded_by}"
    if prior.cell_key != cell_key:
        return (
            f"error: --retry-of {retry_of}: belongs to a different cell "
            "(different runner, target, or head sha)"
        )
    if not prior.timed_out:
        return (
            f"error: --retry-of {retry_of}: attempt did not time out "
            "(reached grading, or hit a runner error with no persisted signal); "
            "only a retry of a timeout is admissible"
        )
    return None


def _retry_gate(retry_of: int | None, cell_key: str) -> str | None:
    """Resolve ``--retry-of``'s admissibility; return a refusal message, or None.

    Returns None both when *retry_of* is absent and when the prior attempt is
    admissible — callers only need to branch on "refused vs proceed".
    """
    if retry_of is None:
        return None
    from little_loops.history_reader import harness_event_by_id
    from little_loops.session_store import resolve_history_db

    # `harness_event_by_id()` -> `_connect_readonly()` opens whatever path
    # it is handed as-is -- it does not re-resolve a default-shaped path
    # through the env/config chain the way `_pkg.connect()` (the write side)
    # does. Resolve once here, matching `_read_target_history()`'s precedent,
    # so this read lands on the same database file the write path uses.
    prior = harness_event_by_id(resolve_history_db(DEFAULT_DB_PATH), retry_of)
    return _retry_refusal(prior, retry_of, cell_key)


def _record_harness_event(
    *,
    runner: str,
    target: str,
    exit_code: int | None,
    semantic_verdict: str | None,
    semantic_passed: bool | None,
    timed_out: bool,
    duration_ms: int,
    head_sha: str | None,
    cell_key: str,
    retry_of: int | None = None,
    parent_id: int | None = None,
    target_content_hash: str | None = None,
    target_path: str | None = None,
    dirty: int | None = None,
    loud: bool = False,
    semantic_prompt: str | None = None,
    semantic_model: str | None = None,
    subject_model: str | None = None,
    timeout_s: int | None = None,
    host_cli: str | None = None,
    input_hash: str | None = None,
    conditions_fp: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    cache_creation_tokens: int | None = None,
    tool_calls: int | None = None,
    channels_json: str | None = None,
) -> int | None:
    """Record one attempt against *cell_key* via :func:`record_attempt` (ENH-3407).

    Returns the new attempt's id (ENH-3408: callers use it to scope
    ``admissions_by_reason()`` to the ids a run actually wrote), or ``None``
    when the write is best-effort-suppressed and fails.

    ENH-141 adds ``target_content_hash`` / ``target_path`` / ``dirty`` kwargs;
    all three default to None so existing callers (v38 row shape) continue to
    work unchanged.

    ENH-3435 adds ``loud`` plus the seven condition kwargs. The condition
    kwargs land on the v50 ``harness_events`` columns; ``input_hash`` and
    ``conditions_fp`` are always non-NULL on the baseline paths so a stored
    baseline is matchable (and pre-baseline rows are excluded by
    construction). With either baseline flag set, a swallowed write would
    mean the baseline (or the candidate rows the next baseline reuses)
    silently never landed, so ``loud=True`` propagates write failures the
    same way the ``--retry-of`` path already does.

    Without ``retry_of`` and without ``loud``, this stays best-effort
    (``contextlib.suppress``) as before — a failed write never affects the
    harness exit code.
    """

    def _write() -> int:
        return record_attempt(
            DEFAULT_DB_PATH,
            cell_key=cell_key,
            attempt_kind="infra_retry" if retry_of is not None else "repetition",
            retry_of=retry_of,
            reason="timeout" if retry_of is not None else None,
            ts=_now_iso(),
            runner=runner,
            target=target,
            exit_code=exit_code,
            semantic_verdict=semantic_verdict,
            semantic_passed=semantic_passed,
            timed_out=timed_out,
            duration_ms=duration_ms,
            head_sha=head_sha,
            branch=_git_output("rev-parse", "--abbrev-ref", "HEAD"),
            parent_id=parent_id,
            target_content_hash=target_content_hash,
            target_path=target_path,
            dirty=dirty,
            semantic_prompt=semantic_prompt,
            semantic_model=semantic_model,
            subject_model=subject_model,
            timeout_s=timeout_s,
            host_cli=host_cli,
            input_hash=input_hash,
            conditions_fp=conditions_fp,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
            tool_calls=tool_calls,
            channels_json=channels_json,
        )

    if retry_of is not None or loud:
        return _write()
    try:
        return _write()
    except Exception:
        return None


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
        p.add_argument(
            "--retry-of",
            dest="retry_of",
            type=int,
            default=None,
            metavar="ID",
            help=(
                "Attempt id (harness_events.id) this run retries (ENH-3407). "
                "Gated before the run: refused with exit 1 unless the prior "
                "attempt exists, has a cell_key, is not already superseded, "
                "matches this invocation's cell (runner/target/head sha), "
                "and timed out. On success, records attempt_kind='infra_retry' "
                "and admits the retry in one transaction."
            ),
        )
        p.add_argument(
            "--samples",
            dest="samples",
            type=_positive_int,
            default=None,
            metavar="N",
            help=(
                "Number of times to run the subject and grade it (ENH-3415). "
                "Default: DEFAULT_STOCHASTIC_SAMPLES (3) for stochastic runners "
                "(skill, prompt), 1 for deterministic runners (cmd, mcp). An "
                "explicit value overrides in both directions. Wall time and "
                "--timeout budget scale with n. Ignored (forced to 1) when "
                "--retry-of is given without an explicit --samples. Refused "
                "on the dsl runner when > 1."
            ),
        )
        p.add_argument(
            "--measure-baseline",
            dest="measure_baseline",
            action="store_true",
            help=(
                "Run the effective n repetitions on the subject as it exists on "
                "disk and record them as the baseline for that content (ENH-3435). "
                "A full, condition-matched baseline is reused without re-running. "
                "The exit code follows the normal banding (a 0/n baseline exits 1 "
                "and is still recorded). Not supported on the dsl runner."
            ),
        )
        p.add_argument(
            "--compare-baseline",
            dest="compare_baseline",
            action="store_true",
            help=(
                "Run n repetitions on the (mutated) subject and report a delta "
                "against the measured baseline for the incumbent content "
                "(ENH-3435). Refuses with exit 2 before any invocation when no "
                "condition-matched baseline exists -- never compares against a "
                "remembered number, never re-measures. skill resolves the "
                "incumbent from HEAD; prompt/cmd/mcp require --baseline-of. "
                "Not supported on the dsl runner."
            ),
        )
        p.add_argument(
            "--baseline-of",
            dest="baseline_of",
            type=int,
            default=None,
            metavar="ID",
            help=(
                "Attempt id (harness_events.id) whose (runner, target, input, "
                "content) names the baseline to compare against (ENH-3435). "
                "Required for --compare-baseline on prompt/cmd/mcp; an explicit "
                "override of the HEAD resolution on skill."
            ),
        )
        p.add_argument(
            "--evidence",
            action="append",
            default=[],
            choices=["stderr"],
            metavar="{stderr}",
            help=(
                "Additional channel(s) to send to the --semantic judge, beyond "
                "stdout (always examined); repeatable (ENH-3462). E.g. "
                "--evidence stderr."
            ),
        )
        p.add_argument(
            "--require-artifact",
            action="append",
            default=[],
            metavar="PATH",
            help=(
                "Path (relative to the process cwd) that must have been written "
                "by the run; repeatable (ENH-3462, moved from trace-mode-only). "
                "Enforced: missing, unreadable, or pre-existing-and-untouched "
                "fails the run (exit 1). When present and touched, its content "
                "is sent to the --semantic judge."
            ),
        )
        p.add_argument(
            "--forbid-path",
            action="append",
            default=[],
            metavar="PATH",
            help=(
                "Path (relative to the process cwd) that must NOT be created or "
                "content-modified by the run; repeatable (ENH-3462, moved from "
                "trace-mode-only). A pre-existing directory passes "
                "(existence-only check); a newly created one fails."
            ),
        )
        p.add_argument(
            "--expect-no-git-changes",
            dest="expect_no_git_changes",
            action="store_true",
            help=(
                "Fail if the run introduces any new git change (tracked or "
                "untracked) relative to its state before the run, or further "
                "modifies an already-dirty tracked file (ENH-3462). Does not "
                "require the tree to be clean beforehand."
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
class SampleTally:
    """Aggregated per-sample grading counts for an n-sample invocation (ENH-3415 D8).

    `graded` is `passed + failed` (D3) -- abstained/errored samples are
    recorded but excluded from the graded denominator.
    """

    requested: int
    graded: int = 0
    passed: int = 0
    failed: int = 0
    abstained: int = 0
    errored: int = 0
    ci_lo: float | None = None
    ci_hi: float | None = None

    def record(self, rc: int) -> None:
        """Tally one sample's `_grade()` exit code (ENH-3415 D3)."""
        if rc == 2:
            self.errored += 1
        elif rc == 3:
            self.abstained += 1
        elif rc == 0:
            self.passed += 1
            self.graded += 1
        else:  # rc == 1
            self.failed += 1
            self.graded += 1


@dataclass
class ChannelRecord:
    """One evidence channel's read/pass status on a `HarnessEvalOutcome` (ENH-3462).

    `examined=False, content=None` means the channel was never declared/read;
    `examined=True, content=""` means it was read and found empty — the two
    are distinguishable so an unread channel isn't mistaken for an
    examined-and-empty one. `passed` is `None` when the channel carries no
    pass/fail verdict of its own (stdout/stderr, or an undeclared side
    effect); `True`/`False` for a declared side effect (`--require-artifact`,
    `--forbid-path`, `--expect-no-git-changes`) — `_grade()` folds any
    `False` into the overall verdict. `passed` is internal fold state, not
    part of the D2 JSON shape.
    """

    name: str
    examined: bool
    content: str | None
    note: str | None = None
    passed: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Render the `--json`/report shape: `{name, examined, chars, note}` (no `content`)."""
        return {
            "name": self.name,
            "examined": self.examined,
            "chars": None if self.content is None else len(self.content),
            "note": self.note,
        }

    def to_row_dict(self) -> dict[str, Any]:
        """Render the persisted `harness_events.channels_json` shape (ENH-3476 D2).

        `{name, examined, chars, note, passed}` — adds `passed` on top of
        `to_dict()`'s `--json` shape (needed to persist per-side-effect
        pass/fail) but still never includes raw `content`.
        """
        row = self.to_dict()
        row["passed"] = self.passed
        return row


def _channels_json(channels: list[ChannelRecord]) -> str | None:
    """Serialize *channels* for `harness_events.channels_json`, or `None` if empty (ENH-3476 D3/D4).

    `None` means "no graded channel evidence" uniformly for pre-v52 rows and
    ungraded rows (timeout/runner-error, DSL aggregate, DSL malformed-task)
    alike -- never the string `"[]"`.
    """
    if not channels:
        return None
    return json.dumps([c.to_row_dict() for c in channels])


@dataclass
class HarnessEvalOutcome:
    """Evaluation outcome carried alongside `_evaluate_and_report()`'s exit code."""

    passed: bool
    verdict: str | None
    eval_result: EvaluationResult | None
    abstained: bool = False
    sample_pass_rate: float | None = None
    samples: SampleTally | None = None
    channels: list[ChannelRecord] = field(default_factory=list)
    # ENH-3464: efficiency vector, copied from RunnerResult (never read by any
    # gate -- passed/verdict/abstained above are computed with no knowledge
    # of these). duration_ms is stamped by the caller that measures it.
    duration_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    tool_calls: int | None = None


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

    ENH-3408: superseded rows (an infra-retried timeout's losing attempt) are
    excluded from both denominators -- a retry chain contributes one row (its
    surviving attempt) to `n`, not one row per attempt. When the surviving
    population has any admitted retries, `history_admissions` tabulates them
    by reason.
    """
    from little_loops.history_reader import (
        admissions_by_reason,
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
    authoritative_events = [e for e in events if e.superseded_by is None]
    pass_scored = sum(1 for e in authoritative_events if e.semantic_passed is not None)
    judged_scored = sum(1 for e in authoritative_events if e.semantic_verdict is not None)

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
    admissions = admissions_by_reason(db_path, [e.id for e in events if e.id is not None])
    if admissions:
        history["history_admissions"] = admissions
    history["history_since"] = since
    return history


def _format_target_history_line(history: dict) -> str:
    """Render `_read_target_history()`'s dict as one status line (target-scoped)."""
    parts = []
    if "history_pass_rate" in history:
        runs_part = f"{history['history_pass_rate_runs']} runs"
        admissions = history.get("history_admissions")
        if admissions:
            breakdown = ", ".join(
                f"{reason}×{count}"
                for reason, count in sorted(admissions.items(), key=lambda kv: -kv[1])
            )
            runs_part += f", {sum(admissions.values())} infra retries admitted: {breakdown}"
        parts.append(f"pass {history['history_pass_rate']:.0%} ({runs_part})")
    if "history_abstention_rate" in history:
        parts.append(
            f"abstention {history['history_abstention_rate']:.0%} "
            f"({history['history_judged_runs']} judged)"
        )
    since_date = history["history_since"][:10]
    return f"Target history since {since_date}: " + ", ".join(parts)


def _truncate_keep_last(text: str, limit: int = 4000) -> str:
    """Return the last *limit* chars of *text*, matching `evaluate_llm_structured()`'s budget."""
    return text[-limit:] if len(text) > limit else text


@dataclass
class _PathSnapshot:
    """One declared path's pre-run state (ENH-3462 D5)."""

    exists: bool
    sha256: str | None
    mtime_ns: int | None
    is_dir: bool


@dataclass
class SideEffectSnapshot:
    """Pre-run state for every declared side effect, taken before one invocation (ENH-3462 D5)."""

    require_artifact: dict[str, _PathSnapshot]
    forbid_path: dict[str, _PathSnapshot]
    pre_porcelain: frozenset[str]
    pre_dirty_hashes: dict[str, str]
    git_declared: bool


def _git_status_porcelain_z(cwd: Path) -> str | None:
    """Return raw `git status --porcelain -z` output for *cwd*, or None on failure.

    Deliberately does NOT reuse `_git_dirty()`'s subprocess call: that call
    passes `--untracked-files=no`, which would miss a run that adds an
    untracked path (AC5) — this criterion needs the default `normal` mode.
    """
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "-z"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
    except Exception:  # noqa: BLE001 — best-effort, never raises
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _snapshot_path(p: Path) -> _PathSnapshot:
    """Snapshot one path's existence/content/mtime for later touched-detection (ENH-3462 D5)."""
    if not p.exists():
        return _PathSnapshot(exists=False, sha256=None, mtime_ns=None, is_dir=False)
    if p.is_dir():
        return _PathSnapshot(exists=True, sha256=None, mtime_ns=None, is_dir=True)
    try:
        data = p.read_bytes()
        stat = p.stat()
    except OSError:
        return _PathSnapshot(exists=True, sha256=None, mtime_ns=None, is_dir=False)
    return _PathSnapshot(
        exists=True,
        sha256=hashlib.sha256(data).hexdigest(),
        mtime_ns=stat.st_mtime_ns,
        is_dir=False,
    )


def _snapshot_side_effects(args: argparse.Namespace, cwd: Path) -> SideEffectSnapshot:
    """Pre-run snapshot for every declared `--require-artifact`/`--forbid-path`/git check.

    All reads via `getattr(args, name, default)` (D10): the shared
    `_make_namespace()` test fixture and `cmd_dsl`'s aggregate `args` predate
    these flags, so a bare `args.evidence` would raise across ~100 tests.
    """
    require_artifact = getattr(args, "require_artifact", None) or []
    forbid_path = getattr(args, "forbid_path", None) or []
    expect_no_git_changes = getattr(args, "expect_no_git_changes", False)
    ra_snap = {path_str: _snapshot_path(cwd / path_str) for path_str in require_artifact}
    fp_snap = {path_str: _snapshot_path(cwd / path_str) for path_str in forbid_path}
    pre_porcelain: frozenset[str] = frozenset()
    pre_dirty_hashes: dict[str, str] = {}
    if expect_no_git_changes:
        raw = _git_status_porcelain_z(cwd)
        pre_porcelain = frozenset(porcelain_paths(raw)) if raw is not None else frozenset()
        for path_str in pre_porcelain:
            p = cwd / path_str
            if p.is_file():
                try:
                    pre_dirty_hashes[path_str] = hashlib.sha256(p.read_bytes()).hexdigest()
                except OSError:
                    pass
    return SideEffectSnapshot(
        require_artifact=ra_snap,
        forbid_path=fp_snap,
        pre_porcelain=pre_porcelain,
        pre_dirty_hashes=pre_dirty_hashes,
        git_declared=bool(expect_no_git_changes),
    )


def _check_require_artifact(path_str: str, pre: _PathSnapshot, cwd: Path) -> ChannelRecord:
    """Post-run check for one `--require-artifact` path (ENH-3462 AC3)."""
    p = cwd / path_str
    if not p.exists() or not p.is_file():
        return ChannelRecord(
            name=path_str, examined=True, content=None, note="missing", passed=False
        )
    try:
        data = p.read_bytes()
        post_mtime = p.stat().st_mtime_ns
    except OSError as exc:
        return ChannelRecord(
            name=path_str, examined=True, content=None, note=f"unreadable: {exc}", passed=False
        )
    post_sha = hashlib.sha256(data).hexdigest()
    # Touched = created, content changed, or rewritten with identical bytes
    # (mtime still advances) -- sha256 alone would false-fail a deterministic
    # rewrite under --samples N (AC8).
    touched = (not pre.exists) or (post_sha != pre.sha256) or (post_mtime != pre.mtime_ns)
    text = data.decode("utf-8", errors="replace")
    if not touched:
        return ChannelRecord(
            name=path_str, examined=True, content=text, note="pre-existing, unchanged", passed=False
        )
    return ChannelRecord(name=path_str, examined=True, content=text, note=None, passed=True)


def _check_forbid_path(path_str: str, pre: _PathSnapshot, cwd: Path) -> ChannelRecord:
    """Post-run check for one `--forbid-path` path (ENH-3462 AC4)."""
    p = cwd / path_str
    if not p.exists():
        return ChannelRecord(name=path_str, examined=True, content=None, note=None, passed=True)
    if p.is_dir():
        if pre.exists and pre.is_dir:
            return ChannelRecord(name=path_str, examined=True, content=None, note=None, passed=True)
        return ChannelRecord(
            name=path_str, examined=True, content=None, note="created", passed=False
        )
    try:
        data = p.read_bytes()
    except OSError as exc:
        return ChannelRecord(
            name=path_str, examined=True, content=None, note=f"unreadable: {exc}", passed=False
        )
    if not pre.exists or pre.is_dir:
        return ChannelRecord(
            name=path_str, examined=True, content=None, note="created", passed=False
        )
    post_sha = hashlib.sha256(data).hexdigest()
    if post_sha == pre.sha256:
        return ChannelRecord(name=path_str, examined=True, content=None, note=None, passed=True)
    return ChannelRecord(name=path_str, examined=True, content=None, note="modified", passed=False)


def _check_git_side_effect(snapshot: SideEffectSnapshot, cwd: Path) -> ChannelRecord:
    """Post-run check for `--expect-no-git-changes` (ENH-3462 AC5)."""
    if not snapshot.git_declared:
        return ChannelRecord(name="git", examined=False, content=None)
    raw = _git_status_porcelain_z(cwd)
    post_paths = frozenset(porcelain_paths(raw)) if raw is not None else frozenset()
    new_paths = post_paths - snapshot.pre_porcelain
    modified: list[str] = []
    for path_str in snapshot.pre_porcelain & post_paths:
        pre_hash = snapshot.pre_dirty_hashes.get(path_str)
        if pre_hash is None:
            continue
        try:
            post_hash = hashlib.sha256((cwd / path_str).read_bytes()).hexdigest()
        except OSError:
            continue
        if post_hash != pre_hash:
            modified.append(path_str)
    offending = sorted(new_paths) + sorted(modified)
    if offending:
        return ChannelRecord(
            name="git",
            examined=True,
            content=None,
            note="changed: " + ", ".join(offending),
            passed=False,
        )
    return ChannelRecord(name="git", examined=True, content=None, note=None, passed=True)


def _check_side_effects(
    snapshot: SideEffectSnapshot, args: argparse.Namespace, cwd: Path
) -> list[ChannelRecord]:
    """Post-run check for every declared side effect (ENH-3462 D5)."""
    channels: list[ChannelRecord] = []
    for path_str, pre in snapshot.require_artifact.items():
        channels.append(_check_require_artifact(path_str, pre, cwd))
    for path_str, pre in snapshot.forbid_path.items():
        channels.append(_check_forbid_path(path_str, pre, cwd))
    channels.append(_check_git_side_effect(snapshot, cwd))
    return channels


def _invoke_with_side_effects(
    invoke: Callable[[], tuple[RunnerResult, int]], args: argparse.Namespace
) -> tuple[RunnerResult, int, list[ChannelRecord]]:
    """Snapshot, invoke, then check declared side effects around one run (ENH-3462 D5).

    Wraps the four single-run call sites and `cmd_dsl`'s per-task action. The
    `invoke: Callable[[], tuple[RunnerResult, int]]` contract shared with
    `_run_baseline_phase()` is unchanged -- `_run_sample_loop()` does its own
    inline snapshot/check instead of going through this wrapper.
    """
    cwd = Path.cwd()
    snapshot = _snapshot_side_effects(args, cwd)
    result, duration_ms = invoke()
    side_effects = _check_side_effects(snapshot, args, cwd)
    return result, duration_ms, side_effects


def _compose_judge_evidence(
    result: RunnerResult, args: argparse.Namespace, side_effects: list[ChannelRecord] | None
) -> str:
    """Tag-wrap and concatenate declared channels for the judge (ENH-3462 D3).

    Only called when the declaration is non-default (`--evidence`/
    `--require-artifact` given) -- the default path passes raw `result.stdout`
    unchanged (AC2). Each channel gets its own keep-last 4000-char budget
    before composition, matching `evaluate_contract()`'s per-file precedent.
    """
    evidence = getattr(args, "evidence", None) or []
    require_artifact = getattr(args, "require_artifact", None) or []
    parts = [f"<stdout>\n{_truncate_keep_last(result.stdout)}\n</stdout>"]
    if "stderr" in evidence:
        parts.append(f"<stderr>\n{_truncate_keep_last(result.stderr)}\n</stderr>")
    if side_effects:
        by_name = {c.name: c for c in side_effects}
        for path_str in require_artifact:
            ch = by_name.get(path_str)
            if ch is not None and ch.content is not None:
                parts.append(
                    f'<artifact path="{path_str}">\n{_truncate_keep_last(ch.content)}\n</artifact>'
                )
    return "\n\n".join(parts)


def _grade(
    runner_label: str,
    result: RunnerResult,
    args: argparse.Namespace,
    *,
    expected_grade: ExpectedGrade | None = None,
    side_effects: list[ChannelRecord] | None = None,
    duration_ms: int | None = None,
) -> tuple[int, HarnessEvalOutcome]:
    """Grade *result* against criteria. No stdout or DB writes (ENH-3415).

    Extracted from `_evaluate_and_report()` so an n-sample loop can grade each
    sample without also printing/persisting per-sample. Still performs the
    `--semantic` judge call (`evaluate_llm_structured()`) when set -- that is
    not a side effect this function's contract excludes, just not a pure one.

    ENH-3462: *side_effects* carries the declared-side-effect `ChannelRecord`s
    computed around the invocation (`_invoke_with_side_effects()` /
    `_run_sample_loop()`'s inline snapshot/check); `None` when no such check
    ran (e.g. a direct `_grade()` call in a test, or a Namespace predating
    the new flags -- AC14), in which case only stdout/stderr are recorded and
    the `git` channel is synthesized as unexamined.

    ENH-3464: *duration_ms* is measured by the caller (`time.monotonic()`
    around the invocation) and copied onto the outcome verbatim -- never read
    by any gate here. `result`'s five efficiency fields are copied the same
    way. Both stay `None` on the timed-out/errored early return below (stdout
    is empty/unavailable in both cases) except `duration_ms`, which is still
    stamped -- wall-clock is measured regardless of outcome.
    """
    if result.timed_out or result.error is not None:
        return 2, HarnessEvalOutcome(
            passed=False, verdict=None, eval_result=None, duration_ms=duration_ms
        )

    passed = True
    abstained = False
    eval_result: EvaluationResult | None = None

    if args.exit_code is not None and result.exit_code != args.exit_code:
        passed = False

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

    evidence = getattr(args, "evidence", None) or []
    channels: list[ChannelRecord] = [
        ChannelRecord(name="stdout", examined=True, content=result.stdout),
        ChannelRecord(
            name="stderr",
            examined="stderr" in evidence,
            content=result.stderr if "stderr" in evidence else None,
        ),
    ]
    if side_effects is not None:
        channels.extend(side_effects)
    else:
        channels.append(ChannelRecord(name="git", examined=False, content=None))

    # ENH-3462 D5: every side effect that fails sets passed=False (exit 1),
    # same precedence as --exit-code; they never abstain.
    if any(c.passed is False for c in channels):
        passed = False

    require_artifact = getattr(args, "require_artifact", None) or []
    if args.semantic is not None:
        # ENH-3435: pass the judge model explicitly so the value recorded as
        # `semantic_model` on baseline paths is the one actually used, not a
        # re-derivation at the write site.
        if evidence or require_artifact:
            # ENH-3462 D3: non-default declaration -- pre-compose the
            # multi-channel string and disable the evaluator's own
            # truncation, which would otherwise re-truncate the whole
            # composed string and silently drop earlier channels' tags.
            composed = _compose_judge_evidence(result, args, side_effects)
            eval_result = evaluate_llm_structured(
                output=composed, prompt=args.semantic, model=_JUDGE_MODEL, max_output_chars=None
            )
        else:
            eval_result = evaluate_llm_structured(
                output=result.stdout, prompt=args.semantic, model=_JUDGE_MODEL
            )
        # ENH-3185 AC9: an abstention is neither a pass nor a failure — report
        # it separately rather than folding it into `passed = False`. Precedence
        # is fail > abstain > pass, so a mixed exit_code-fail + semantic-abstain
        # run still reports FAIL/exit 1.
        if is_abstention_verdict(eval_result.verdict):
            abstained = True
        elif eval_result.verdict != "yes":
            passed = False

    outcome = HarnessEvalOutcome(
        passed=passed,
        verdict=eval_result.verdict if eval_result is not None else None,
        eval_result=eval_result,
        abstained=abstained,
        channels=channels,
        duration_ms=duration_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cache_read_tokens=result.cache_read_tokens,
        cache_creation_tokens=result.cache_creation_tokens,
        tool_calls=result.tool_calls,
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


def _effective_samples(args: argparse.Namespace, runner: RunnerType) -> int:
    """Resolve the effective sample count for one invocation (ENH-3415 D7).

    An explicit ``--samples`` always wins (raising n on a deterministic
    runner is a legitimate way to chase flakiness). Otherwise ``--retry-of``
    without ``--samples`` pins n to 1 (D2) -- a retry supersedes exactly one
    attempt. Absent both, a stochastic ``RunnerType`` defaults to
    ``DEFAULT_STOCHASTIC_SAMPLES``; everything else defaults to 1.
    """
    samples = getattr(args, "samples", None)
    if samples is not None:
        return samples
    if getattr(args, "retry_of", None) is not None:
        return 1
    if is_stochastic_runner(runner):
        return DEFAULT_STOCHASTIC_SAMPLES
    return 1


def _band_samples(tally: SampleTally) -> tuple[str, int]:
    """Band a SampleTally into a verdict label + exit code (ENH-3415 D3/D4/D5).

    Precedence: no graded sample and >=1 errored -> ERROR/2; no graded
    sample (all abstained) -> ABSTAIN/3; every requested sample graded and
    passed -> PASS/0; every graded sample failed -> FAIL/1; otherwise
    (mixed, or passes alongside any abstention/error) -> INCONCLUSIVE/3.
    """
    if tally.graded == 0 and tally.errored > 0:
        return "ERROR", 2
    if tally.graded == 0:
        return "ABSTAIN", 3
    if tally.passed == tally.requested:
        return "PASS", 0
    if tally.passed == 0 and tally.graded > 0:
        return "FAIL", 1
    return "INCONCLUSIVE", 3


def _report_samples(
    runner_label: str,
    tally: SampleTally,
    sample_results: list[dict[str, Any]],
    args: argparse.Namespace,
    *,
    label: str,
    prepatch_evidence: dict | None,
    target_history: dict | None,
    baseline: BaselineResult | None = None,
    delta: BaselineDelta | None = None,
    head_sha_differs: bool = False,
) -> None:
    """Print one aggregate report for an n>1 sample invocation (ENH-3415 D8).

    Called once, after the sample loop -- never per sample -- so the JSON
    payload stays a single object and the history/prepatch lines are not
    duplicated n times. ENH-3435 adds the optional ``baseline`` (a measure
    run's provenance) and ``delta`` (a compare run's delta + provenance)
    renderings; both are additive and absent when no baseline flag was given.
    ``head_sha_differs`` carries the different-HEAD note on measure-reuse
    reports (a compare report derives it from ``delta`` instead).
    """
    if tally.graded > 0:
        tally.ci_lo, tally.ci_hi = wilson_ci(tally.passed, tally.graded)
    sample_pass_rate = tally.passed / tally.graded if tally.graded else None

    if args.output == "json":
        payload: dict[str, Any] = {
            "runner": runner_label,
            "result": label,
            "sample_pass_rate": sample_pass_rate,
            "samples": {
                "requested": tally.requested,
                "graded": tally.graded,
                "passed": tally.passed,
                "failed": tally.failed,
                "abstained": tally.abstained,
                "errored": tally.errored,
                "ci_lo": tally.ci_lo,
                "ci_hi": tally.ci_hi,
                "results": sample_results,
            },
        }
        if baseline is not None or delta is not None:
            shown = delta.baseline if delta is not None else baseline
            assert shown is not None  # guarded by the or above
            baseline_payload: dict[str, Any] = {
                "source": shown.source,
                "n": shown.tally.requested,
                "conditions": {
                    "semantic_prompt": shown.conditions.semantic_prompt,
                    "semantic_model": shown.conditions.semantic_model,
                    "subject_model": shown.conditions.subject_model,
                    "timeout_s": shown.conditions.timeout_s,
                    "host_cli": shown.conditions.host_cli,
                },
                "conditions_fp": shown.conditions.conditions_fp,
                "head_sha": shown.head_sha,
                "head_sha_differs": bool(
                    delta.head_sha_differs if delta is not None else head_sha_differs
                ),
                "attempt_ids": shown.attempt_ids,
                "notes": _baseline_notes(shown),
                "baseline_pass_rate": (
                    shown.tally.passed / shown.tally.graded if shown.tally.graded else None
                ),
                "baseline_ci": [shown.tally.ci_lo, shown.tally.ci_hi],
            }
            if delta is not None:
                baseline_payload["delta"] = delta.delta
                baseline_payload["candidate_pass_rate"] = sample_pass_rate
                baseline_payload["candidate_ci"] = [tally.ci_lo, tally.ci_hi]
            payload["baseline"] = baseline_payload
        if prepatch_evidence is not None:
            payload["prepatch_evidence"] = prepatch_evidence
        if target_history is not None:
            payload.update(target_history)
        print_json(payload)
        return

    print(status_block({"Runner": runner_label, "Result": label}))
    if tally.graded > 0:
        samples_line = (
            f"Samples: {tally.passed}/{tally.graded} graded  "
            f"[{tally.ci_lo:.2f}, {tally.ci_hi:.2f}] (95% CI)"
        )
    else:
        samples_line = f"Samples: {tally.passed}/{tally.graded} graded"
    extras = []
    if tally.errored:
        extras.append(f"{tally.errored} errored")
    if tally.abstained:
        extras.append(f"{tally.abstained} abstained")
    if extras:
        samples_line += ", " + ", ".join(extras)
    print(samples_line)
    if baseline is not None or delta is not None:
        shown = delta.baseline if delta is not None else baseline
        assert shown is not None  # guarded by the or above
        differs = delta.head_sha_differs if delta is not None else head_sha_differs
        line = f"Baseline: {shown.source} n={shown.tally.requested} head_sha={shown.head_sha}"
        if differs:
            line += " (measured at a different HEAD)"
        if shown.attempt_ids:
            line += "  attempts=" + ",".join(str(i) for i in shown.attempt_ids)
        print(line)
        for note in _baseline_notes(shown):
            print(f"  {note}")
    if delta is not None:
        if delta.delta is None:
            print("Delta: n/a (no graded candidate samples)")
        else:
            baseline_rate = delta.baseline.tally.passed / delta.baseline.tally.graded
            baseline_ci = f"[{delta.baseline.tally.ci_lo:.2f}, {delta.baseline.tally.ci_hi:.2f}]"
            candidate_ci = f"[{tally.ci_lo:.2f}, {tally.ci_hi:.2f}]"
            print(
                f"Delta: {delta.delta:+.2f} "
                f"(candidate {sample_pass_rate:.2f} {candidate_ci} "
                f"vs baseline {baseline_rate:.2f} {baseline_ci})"
            )
    if prepatch_evidence is not None:
        print(f"Pre-patch check: {prepatch_evidence.get('verdict', 'unknown')}")
    if target_history is not None:
        print(_format_target_history_line(target_history))
    for entry in sample_results:
        stdout = entry.get("stdout")
        if not stdout:
            continue
        if args.verbose or entry.get("result") != "PASS":
            print(f"--- sample {entry['index']} ---")
            sys.stdout.write(stdout)
            if not stdout.endswith("\n"):
                print()


def _retry_samples_refusal(retry_of: int | None, args: argparse.Namespace) -> str | None:
    """Refuse ``--retry-of`` combined with an explicit ``--samples`` > 1 (ENH-3415 D2)."""
    samples = getattr(args, "samples", None)
    if retry_of is not None and samples is not None and samples > 1:
        return (
            f"error: --retry-of {retry_of}: cannot combine with --samples {samples} "
            "(a retry supersedes exactly one attempt)"
        )
    return None


# ---------------------------------------------------------------------------
# ENH-3435: the measured-baseline arm. A baseline *is* the set of authoritative
# harness_events rows for the incumbent's content under matching conditions
# (Program Design, Option A) — there is no second store.
# ---------------------------------------------------------------------------


@dataclass
class BaselineDelta:
    """A compare run's delta with its baseline provenance (ENH-3435).

    ``delta`` is the pass-rate difference (candidate − baseline); ``None``
    when the candidate arm has zero graded samples. Never a banded verdict —
    the run's exit code still comes from ``_band_samples`` on the candidate
    tally alone.
    """

    candidate: SampleTally
    baseline: BaselineResult
    delta: float | None
    source: str
    head_sha_differs: bool


def _resolved_host_cli() -> str | None:
    """Return the active host CLI's name for the conditions fingerprint, or None."""
    try:
        from little_loops.host_runner import resolve_host

        return resolve_host().name
    except Exception:  # noqa: BLE001 — best-effort condition provenance, never raises
        return None


def _input_hash(value: Any) -> str:
    """Return the content hash of one runner input (ENH-3435).

    ``skill`` hashes its canonical ``runner_args`` (the task); ``mcp`` hashes
    the canonical ``--args`` JSON. ``cmd``/``prompt`` never call this — their
    target *is* the input, carried by ``target_content_hash`` — so their rows
    record ``input_hash = ""``.
    """
    return _hash_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _conditions_fp(args: argparse.Namespace, judge_model: str | None = None) -> str:
    """Return the sha256 conditions fingerprint for one invocation (ENH-3435).

    Covers every condition-relevant argument: the readable conditions
    (semantic prompt, judge model, subject model, timeout, host CLI) plus
    ``--exit-code``, the trace flags, and ``--hosts``. Never NULL on
    baseline-eligible rows, so pre-migration rows are excluded from baseline
    matching by construction and no NULL-vs-NULL vacuous match can occur.
    ``judge_model`` defaults to the model ``_grade`` will pass when
    ``--semantic`` is set, so an fp computed here matches the row written
    under the same args.
    """
    if judge_model is None:
        judge_model = _JUDGE_MODEL if getattr(args, "semantic", None) else None
    payload = {
        "evidence": getattr(args, "evidence", None) or None,
        "exit_code": getattr(args, "exit_code", None),
        "expect_no_git_changes": getattr(args, "expect_no_git_changes", False) or None,
        "forbid_path": getattr(args, "forbid_path", None) or None,
        "host_cli": _resolved_host_cli(),
        "hosts": getattr(args, "hosts", None),
        "require_artifact": getattr(args, "require_artifact", None) or None,
        "require_order": getattr(args, "require_order", None),
        "semantic_model": judge_model,
        "semantic_prompt": getattr(args, "semantic", None),
        "subject_model": getattr(args, "model", None),
        "timeout_s": getattr(args, "timeout", None),
        "trace_mode": bool(getattr(args, "trace_mode", False)),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"enah-3435-v1|{canonical}".encode()).hexdigest()


def _baseline_conditions(args: argparse.Namespace, n: int) -> BaselineConditions:
    """Build the readable BaselineConditions for this invocation (ENH-3435)."""
    return BaselineConditions(
        n=n,
        conditions_fp=_conditions_fp(args),
        semantic_prompt=getattr(args, "semantic", None),
        semantic_model=_JUDGE_MODEL if getattr(args, "semantic", None) else None,
        subject_model=getattr(args, "model", None),
        timeout_s=getattr(args, "timeout", None),
        host_cli=_resolved_host_cli(),
    )


def _baseline_record_extras(args: argparse.Namespace, *, input_hash: str) -> dict[str, Any]:
    """Condition kwargs for ``_record_harness_event`` on the baseline paths (ENH-3435)."""
    return {
        "semantic_prompt": getattr(args, "semantic", None),
        "semantic_model": _JUDGE_MODEL if getattr(args, "semantic", None) else None,
        "subject_model": getattr(args, "model", None),
        "timeout_s": getattr(args, "timeout", None),
        "host_cli": _resolved_host_cli(),
        "input_hash": input_hash,
        "conditions_fp": _conditions_fp(args),
    }


def _baseline_flag_refusal(
    args: argparse.Namespace, n: int, *, runner: str, file_shaped: bool
) -> str | None:
    """Refuse invalid baseline-flag combinations before any work (ENH-3435, exit 2)."""
    measure = getattr(args, "measure_baseline", False)
    compare = getattr(args, "compare_baseline", False)
    retry_of = getattr(args, "retry_of", None)
    if measure and compare:
        return "error: --measure-baseline and --compare-baseline cannot be combined"
    if (measure or compare) and retry_of is not None:
        flag = "--measure-baseline" if measure else "--compare-baseline"
        return f"error: {flag} cannot be combined with --retry-of {retry_of}"
    if compare:
        if n < 2:
            return (
                "error: --compare-baseline: requires n >= 2 (a delta between two "
                "single runs is not a measurement); use --samples N >= 2"
            )
        if not file_shaped and getattr(args, "baseline_of", None) is None:
            return (
                f"error: --compare-baseline: requires --baseline-of <attempt-id> on "
                f"the {runner} runner (no HEAD-resolvable incumbent)"
            )
    return None


def _incumbent_content_hash(target_path: Path | None) -> str | None:
    """Return the HEAD-blob content hash of *target_path*, or None (ENH-3435).

    For the ``skill`` runner the incumbent is the HEAD version of the target
    file — ``harness-optimize.yaml`` commits accepted candidates and reverts
    rejected ones, so the incumbent always equals HEAD content. Reads the raw
    blob via :func:`_git_blob` (BUG-3479: not ``git show``, whose text-mode
    strip mismatched :func:`_hash_file`'s raw-byte hash); never checks out or
    stashes anything. Returns None when git is unavailable, the file is
    untracked, or the path is not file-shaped, so the caller can produce the
    refusal message.
    """
    if target_path is None:
        return None
    root = _git_output("rev-parse", "--show-toplevel")
    if root is None:
        return None
    try:
        rel = os.path.relpath(target_path, root)
    except ValueError:
        return None
    blob = _git_blob(rel)
    if blob is None:
        return None
    return _hash_bytes(blob)


def _resolve_baseline_of(attempt_id: int, *, current_input_hash: str) -> BaselineKey | str:
    """Resolve ``--baseline-of`` into a BaselineKey, or a refusal message (ENH-3435)."""
    from little_loops.history_reader import harness_event_by_id
    from little_loops.session_store import resolve_history_db

    prior = harness_event_by_id(resolve_history_db(DEFAULT_DB_PATH), attempt_id)
    if prior is None:
        return f"error: --baseline-of {attempt_id}: no such attempt"
    if not prior.target_content_hash or prior.input_hash is None or prior.conditions_fp is None:
        return (
            f"error: --baseline-of {attempt_id}: attempt predates baseline support "
            "(no recorded input/conditions); it cannot name a baseline"
        )
    if prior.input_hash != current_input_hash:
        return (
            f"error: --baseline-of {attempt_id}: baseline was measured on a different "
            f"input ({prior.input_hash or '(none)'} != {current_input_hash or '(none)'}); "
            "the candidate must run the same input the baseline measured"
        )
    return BaselineKey(
        runner=prior.runner or "",
        target=prior.target or "",
        input_hash=prior.input_hash,
        target_content_hash=prior.target_content_hash,
    )


def read_baseline(key: BaselineKey, conditions: BaselineConditions) -> BaselineResult | None:
    """Read the stored baseline for *key* under *conditions* (ENH-3435).

    Thin CLI-side wrapper over :func:`history_reader.harness.baseline_for`
    with ``DEFAULT_DB_PATH`` resolved through ``resolve_history_db`` — the
    same precedent as ``_retry_gate``, so the read lands on the same database
    file the write path uses.
    """
    from little_loops.session_store import resolve_history_db

    return baseline_for(
        resolve_history_db(DEFAULT_DB_PATH),
        runner=key.runner,
        target=key.target,
        input_hash=key.input_hash,
        target_content_hash=key.target_content_hash,
        conditions=conditions,
    )


def _baseline_notes(baseline: BaselineResult) -> list[str]:
    """Honesty notes riding on a reported baseline/delta (ENH-3435)."""
    notes: list[str] = []
    if baseline.subject_model is None:
        notes.append("subject model not pinned")
    if baseline.dirty_rows:
        notes.append("measured on a dirty tree")
    return notes


def _run_baseline_phase(
    runner_label: str,
    args: argparse.Namespace,
    n: int,
    invoke: Callable[[], tuple[RunnerResult, int]],
    record: Callable[[RunnerResult, int, HarnessEvalOutcome], int | None],
    key: BaselineKey,
    conditions: BaselineConditions,
    head_sha: str | None,
) -> int:
    """Measure the baseline arm: reuse a full match, else run n loud samples (ENH-3435).

    Only reached with ``--measure-baseline``. A full, condition-matched
    baseline for this content is reused without re-running the subject — the
    "paid once" half of the bidirectional store. Otherwise n samples run with
    loud recording (a swallowed write here would mean the baseline silently
    never landed), and the exit code follows the normal banding: a 0/n
    baseline is valid information, not an error.
    """
    existing = read_baseline(key, conditions)
    if existing is not None:
        label, exit_code = _band_samples(existing.tally)
        _report_samples(
            runner_label,
            existing.tally,
            [],
            args,
            label=label,
            prepatch_evidence=None,
            target_history=None,
            baseline=existing,
            head_sha_differs=existing.head_sha is not None and existing.head_sha != head_sha,
        )
        return exit_code
    written_ids: list[int] = []

    def _recording(
        result: RunnerResult, duration_ms: int, outcome: HarnessEvalOutcome
    ) -> int | None:
        new_id = record(result, duration_ms, outcome)
        if new_id is not None:
            written_ids.append(new_id)
        return new_id

    try:
        res = _run_sample_loop(runner_label, args, n, invoke, _recording)
    except Exception as exc:
        print(f"error: baseline sample was not recorded: {exc}", file=sys.stderr)
        return 1
    fresh = BaselineResult(
        key=key,
        conditions=conditions,
        tally=res.tally,
        attempt_ids=written_ids,
        head_sha=head_sha,
        measured_at=_now_iso(),
        subject_model=conditions.subject_model,
        dirty_rows=False,
        source="measured",
    )
    _report_samples(
        runner_label,
        res.tally,
        res.entries,
        args,
        label=res.label,
        prepatch_evidence=res.prepatch_evidence,
        target_history=res.target_history,
        baseline=fresh,
    )
    return res.exit_code


def _compare_baseline_refusal(key: BaselineKey, conditions: BaselineConditions) -> str | None:
    """Pre-run compare gate: refuse unless a full baseline exists (ENH-3435).

    Computable without running anything — gating before the candidate arm
    matches the ``--retry-of`` precedent, so a refused compare performs zero
    subject invocations and writes no candidate rows.
    """
    baseline = read_baseline(key, conditions)
    if baseline is None:
        return (
            f"error: --compare-baseline: no measured baseline for {key.runner} "
            f"{key.target} (incumbent content {key.target_content_hash or '(none)'}) "
            "under the current conditions; run --measure-baseline on the unmutated "
            "subject first"
        )
    return None


def _run_compare_arm(
    runner_label: str,
    args: argparse.Namespace,
    n: int,
    invoke: Callable[[], tuple[RunnerResult, int]],
    record: Callable[[RunnerResult, int, HarnessEvalOutcome], int | None],
    baseline: BaselineResult | None,
    head_sha: str | None,
) -> int:
    """Run the candidate arm and report the delta against *baseline* (ENH-3435).

    Only reached with ``--compare-baseline`` after the pre-run gate passed, so
    *baseline* is not None in practice. Recording is loud (a swallowed write
    here would mean the candidate rows the next baseline reuses silently
    never landed). The exit code comes from the candidate tally's banding
    alone; the delta is additive report content.
    """
    assert baseline is not None  # the pre-run gate refused when None
    try:
        res = _run_sample_loop(runner_label, args, n, invoke, record)
    except Exception as exc:
        print(f"error: baseline candidate sample was not recorded: {exc}", file=sys.stderr)
        return 1
    candidate_rate = res.tally.passed / res.tally.graded if res.tally.graded else None
    baseline_rate = baseline.tally.passed / baseline.tally.graded
    delta = BaselineDelta(
        candidate=res.tally,
        baseline=baseline,
        delta=None if candidate_rate is None else candidate_rate - baseline_rate,
        source=baseline.source,
        head_sha_differs=baseline.head_sha is not None and baseline.head_sha != head_sha,
    )
    _report_samples(
        runner_label,
        res.tally,
        res.entries,
        args,
        label=res.label,
        prepatch_evidence=res.prepatch_evidence,
        target_history=res.target_history,
        delta=delta,
    )
    return res.exit_code


@dataclass
class SampleLoopResult:
    """One completed sample loop's aggregate (ENH-3415 D8 / ENH-3435 refactor).

    ENH-3435 split the report call out of the loop so the baseline paths can
    attach delta/provenance to the same single report. The prepatch/history
    reads still happen inside the loop, once, before the first sample.
    """

    exit_code: int
    label: str
    tally: SampleTally
    entries: list[dict[str, Any]]
    prepatch_evidence: dict | None
    target_history: dict | None


def _run_sample_loop(
    runner_label: str,
    args: argparse.Namespace,
    n: int,
    invoke: Callable[[], tuple[RunnerResult, int]],
    record: Callable[[RunnerResult, int, HarnessEvalOutcome], int | None],
) -> SampleLoopResult:
    """Run *invoke* n times, grading/tallying/recording each sample (ENH-3415).

    Shared by the four non-DSL ``cmd_*`` handlers. *invoke* performs one
    runner invocation and returns ``(result, duration_ms)``; *record* persists
    one sample via ``_record_harness_event()`` (D1: one ``repetition`` row per
    sample) and returns its row id (ENH-3435: the baseline phase collects
    them). The loop never stops early on a pass (D9): all *n* samples run.
    History/prepatch are read once, before the first sample (D8); the caller
    prints the single aggregate report from the returned
    :class:`SampleLoopResult`.
    """
    prepatch_evidence = _read_prepatch_evidence(getattr(args, "issue_id", None))
    target_history = _read_target_history(args.target)
    tally = SampleTally(requested=n)
    sample_results: list[dict[str, Any]] = []
    cwd = Path.cwd()
    for i in range(n):
        # ENH-3462 D5/D8: snapshot/check inline around each sample so the
        # shared `invoke: Callable[[], tuple[RunnerResult, int]]` contract
        # (also used by `_run_baseline_phase()`) stays unchanged, while each
        # of the n samples gets its own re-snapshotted side-effect check.
        snapshot = _snapshot_side_effects(args, cwd)
        result, duration_ms = invoke()
        side_effects = _check_side_effects(snapshot, args, cwd)
        rc, outcome = _grade(
            runner_label, result, args, side_effects=side_effects, duration_ms=duration_ms
        )
        tally.record(rc)
        record(result, duration_ms, outcome)
        label = {2: "ERROR", 3: "ABSTAIN", 0: "PASS"}.get(rc, "FAIL")
        error = (
            result.error if result.error is not None else ("timeout" if result.timed_out else None)
        )
        entry: dict[str, Any] = {
            "index": i,
            "exit_code": result.exit_code,
            "exit_code_check": (
                str(result.exit_code)
                if args.exit_code is None
                else f"{result.exit_code} (expected {args.exit_code})"
            ),
            "semantic": outcome.verdict if outcome.verdict is not None else "[not checked]",
            "result": label,
            "error": error,
            "channels": [c.to_dict() for c in outcome.channels],
            "duration_ms": outcome.duration_ms,
            "input_tokens": outcome.input_tokens,
            "output_tokens": outcome.output_tokens,
            "cache_read_tokens": outcome.cache_read_tokens,
            "cache_creation_tokens": outcome.cache_creation_tokens,
            "tool_calls": outcome.tool_calls,
        }
        if args.verbose or label != "PASS":
            entry["stdout"] = result.stdout
            entry["stderr"] = result.stderr
        sample_results.append(entry)
    verdict_label, exit_code = _band_samples(tally)
    return SampleLoopResult(
        exit_code=exit_code,
        label=verdict_label,
        tally=tally,
        entries=sample_results,
        prepatch_evidence=prepatch_evidence,
        target_history=target_history,
    )


def _format_efficiency_line(outcome: HarnessEvalOutcome) -> str | None:
    """Render the efficiency vector as one text-summary line, omitting `None` fields.

    Returns `None` when every field is `None` (nothing to show -- e.g. a
    CMD/MCP run, or an unrecognized host stdout shape).
    """
    parts: list[str] = []
    token_bits = []
    if outcome.input_tokens is not None:
        token_bits.append(f"in={outcome.input_tokens}")
    if outcome.output_tokens is not None:
        token_bits.append(f"out={outcome.output_tokens}")
    if outcome.cache_read_tokens is not None:
        token_bits.append(f"cache_r={outcome.cache_read_tokens}")
    if outcome.cache_creation_tokens is not None:
        token_bits.append(f"cache_w={outcome.cache_creation_tokens}")
    if token_bits:
        parts.append("tokens " + "/".join(token_bits))
    if outcome.tool_calls is not None:
        parts.append(f"tool_calls={outcome.tool_calls}")
    if outcome.duration_ms is not None:
        parts.append(f"duration_ms={outcome.duration_ms}")
    if not parts:
        return None
    return "Efficiency: " + " ".join(parts)


def _evaluate_and_report(
    runner_label: str,
    result: RunnerResult,
    args: argparse.Namespace,
    *,
    expected_grade: ExpectedGrade | None = None,
    skip_history: bool = False,
    side_effects: list[ChannelRecord] | None = None,
    duration_ms: int | None = None,
) -> tuple[int, HarnessEvalOutcome]:
    """Evaluate result against criteria and print the report. Returns (exit_code, outcome)."""
    if result.timed_out:
        _report(runner_label, result, args, error_msg="timeout")
        return 2, HarnessEvalOutcome(
            passed=False, verdict=None, eval_result=None, duration_ms=duration_ms
        )
    if result.error is not None:
        _report(runner_label, result, args, error_msg=result.error)
        return 2, HarnessEvalOutcome(
            passed=False, verdict=None, eval_result=None, duration_ms=duration_ms
        )

    exit_code, outcome = _grade(
        runner_label,
        result,
        args,
        expected_grade=expected_grade,
        side_effects=side_effects,
        duration_ms=duration_ms,
    )
    passed = outcome.passed
    abstained = outcome.abstained
    eval_result = outcome.eval_result

    exit_code_display = str(result.exit_code)
    if args.exit_code is not None:
        exit_code_display = f"{result.exit_code} (expected {args.exit_code})"
    semantic_display = eval_result.verdict if eval_result is not None else "[not checked]"

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

    channels_payload = [c.to_dict() for c in outcome.channels]

    if args.output == "json":
        payload = {
            "runner": runner_label,
            "exit_code": result.exit_code,
            "exit_code_check": exit_code_display,
            "semantic": semantic_display,
            "result": overall,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "channels": channels_payload,
            "duration_ms": outcome.duration_ms,
            "input_tokens": outcome.input_tokens,
            "output_tokens": outcome.output_tokens,
            "cache_read_tokens": outcome.cache_read_tokens,
            "cache_creation_tokens": outcome.cache_creation_tokens,
            "tool_calls": outcome.tool_calls,
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
        if channels_payload:
            print("Channels:")
            for ch in channels_payload:
                state = "examined" if ch["examined"] else "not examined"
                if ch["chars"] is not None:
                    detail = f"{ch['chars']} chars"
                elif ch["note"]:
                    detail = ch["note"]
                else:
                    detail = "missing"
                line = f"  {ch['name']}: {state} | {detail}"
                if ch["note"] and ch["chars"] is not None:
                    line += f" ({ch['note']})"
                print(line)
        efficiency_line = _format_efficiency_line(outcome)
        if efficiency_line is not None:
            print(efficiency_line)
        if show_output and result.stdout:
            print("---")
            sys.stdout.write(result.stdout)
            if not result.stdout.endswith("\n"):
                print()

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
    head_sha = _git_output("rev-parse", "HEAD")
    cell_key = _cell_key("skill", args.target, head_sha)
    retry_of = getattr(args, "retry_of", None)
    samples_refusal = _retry_samples_refusal(retry_of, args)
    if samples_refusal is not None:
        print(samples_refusal, file=sys.stderr)
        return 1
    n = _effective_samples(args, RunnerType.SKILL)
    # ENH-3435: baseline flag refusals gate before the retry gate so a
    # baseline+--retry-of combo reports the baseline refusal (exit 2), and a
    # clean baseline invocation never pays the retry-gate DB lookup.
    baseline_refusal = _baseline_flag_refusal(args, n, runner="skill", file_shaped=True)
    if baseline_refusal is not None:
        print(baseline_refusal, file=sys.stderr)
        return 2
    refusal = _retry_gate(retry_of, cell_key)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 1
    skill_path = _resolve_skill_target_path(args.target)
    target_path_str = str(skill_path) if skill_path is not None else None
    target_hash = _hash_file(skill_path) if skill_path is not None else None
    measure_baseline = getattr(args, "measure_baseline", False)
    compare_baseline = getattr(args, "compare_baseline", False)
    input_hash = _input_hash(runner_args)
    baseline_mode = bool(measure_baseline or compare_baseline)
    record_extras = _baseline_record_extras(args, input_hash=input_hash) if baseline_mode else {}

    def _invoke() -> tuple[RunnerResult, int]:
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
        return result, duration_ms

    def _record(result: RunnerResult, duration_ms: int, outcome: HarnessEvalOutcome) -> int | None:
        dirty_val = _git_dirty()
        dirty_int: int | None = None if dirty_val is None else int(dirty_val)
        return _record_harness_event(
            runner="skill",
            target=args.target,
            exit_code=result.exit_code,
            semantic_verdict=outcome.verdict,
            semantic_passed=None if outcome.abstained else outcome.passed,
            timed_out=result.timed_out,
            duration_ms=duration_ms,
            head_sha=head_sha,
            cell_key=cell_key,
            retry_of=retry_of,
            target_content_hash=(
                (target_hash if target_hash is not None else "") if baseline_mode else target_hash
            ),
            target_path=target_path_str,
            dirty=dirty_int,
            loud=baseline_mode,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_tokens=result.cache_read_tokens,
            cache_creation_tokens=result.cache_creation_tokens,
            tool_calls=result.tool_calls,
            channels_json=_channels_json(outcome.channels),
            **record_extras,
        )

    if measure_baseline:
        key = BaselineKey("skill", args.target, input_hash, target_hash or "")
        return _run_baseline_phase(
            runner_label,
            args,
            n,
            _invoke,
            _record,
            key,
            _baseline_conditions(args, n),
            head_sha,
        )

    if compare_baseline:
        resolved: BaselineKey | str
        baseline_of = getattr(args, "baseline_of", None)
        if baseline_of is not None:
            resolved = _resolve_baseline_of(baseline_of, current_input_hash=input_hash)
        else:
            incumbent = _incumbent_content_hash(skill_path)
            if incumbent is None:
                print(
                    f"error: --compare-baseline: cannot resolve incumbent content for "
                    f"skill {args.target} (git cat-file blob HEAD:<target> unavailable — "
                    "untracked file or no git repo)",
                    file=sys.stderr,
                )
                return 2
            if incumbent == (target_hash or ""):
                print(
                    "error: --compare-baseline: subject is unmutated; nothing to compare",
                    file=sys.stderr,
                )
                return 2
            resolved = BaselineKey("skill", args.target, input_hash, incumbent)
        if isinstance(resolved, str):
            print(resolved, file=sys.stderr)
            return 2
        conditions = _baseline_conditions(args, n)
        cmp_refusal = _compare_baseline_refusal(resolved, conditions)
        if cmp_refusal is not None:
            print(cmp_refusal, file=sys.stderr)
            return 2
        return _run_compare_arm(
            runner_label, args, n, _invoke, _record, read_baseline(resolved, conditions), head_sha
        )

    if n > 1:
        res = _run_sample_loop(runner_label, args, n, _invoke, _record)
        _report_samples(
            runner_label,
            res.tally,
            res.entries,
            args,
            label=res.label,
            prepatch_evidence=res.prepatch_evidence,
            target_history=res.target_history,
        )
        return res.exit_code

    result, duration_ms, side_effects = _invoke_with_side_effects(_invoke, args)
    rc, outcome = _evaluate_and_report(
        runner_label, result, args, side_effects=side_effects, duration_ms=duration_ms
    )
    try:
        _record(result, duration_ms, outcome)
    except Exception as exc:
        print(f"error: retry of attempt {retry_of} was not recorded: {exc}", file=sys.stderr)
        return 1
    return rc


def cmd_cmd(args: argparse.Namespace) -> int:
    """Run a shell command with deadlock-safe stderr draining."""
    runner_label = f"cmd {args.target}"
    head_sha = _git_output("rev-parse", "HEAD")
    cell_key = _cell_key("cmd", args.target, head_sha)
    retry_of = getattr(args, "retry_of", None)
    samples_refusal = _retry_samples_refusal(retry_of, args)
    if samples_refusal is not None:
        print(samples_refusal, file=sys.stderr)
        return 1
    n = _effective_samples(args, RunnerType.CMD)
    # ENH-3435: baseline flag refusals gate before the retry gate so a
    # baseline+--retry-of combo reports the baseline refusal (exit 2), and a
    # clean baseline invocation never pays the retry-gate DB lookup.
    baseline_refusal = _baseline_flag_refusal(args, n, runner="cmd", file_shaped=False)
    if baseline_refusal is not None:
        print(baseline_refusal, file=sys.stderr)
        return 2
    refusal = _retry_gate(retry_of, cell_key)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 1
    measure_baseline = getattr(args, "measure_baseline", False)
    compare_baseline = getattr(args, "compare_baseline", False)
    baseline_mode = bool(measure_baseline or compare_baseline)
    # cmd's target is its own input/content — no separate hashes exist, so the
    # baseline paths pin both to "" (never NULL, so rows stay matchable).
    record_extras = _baseline_record_extras(args, input_hash="") if baseline_mode else {}

    def _invoke() -> tuple[RunnerResult, int]:
        spec = ActionSpec(
            name=args.target,
            runner=RunnerType.CMD,
            target=args.target,
            timeout=args.timeout,
        )
        start = time.monotonic()
        result = run_action(spec)
        duration_ms = int((time.monotonic() - start) * 1000)
        return result, duration_ms

    def _record(result: RunnerResult, duration_ms: int, outcome: HarnessEvalOutcome) -> int | None:
        dirty_val = _git_dirty()
        dirty_int: int | None = None if dirty_val is None else int(dirty_val)
        return _record_harness_event(
            runner="cmd",
            target=args.target,
            exit_code=result.exit_code,
            semantic_verdict=outcome.verdict,
            semantic_passed=None if outcome.abstained else outcome.passed,
            timed_out=result.timed_out,
            duration_ms=duration_ms,
            head_sha=head_sha,
            cell_key=cell_key,
            retry_of=retry_of,
            target_content_hash="" if baseline_mode else None,
            dirty=dirty_int,
            loud=baseline_mode,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_tokens=result.cache_read_tokens,
            cache_creation_tokens=result.cache_creation_tokens,
            tool_calls=result.tool_calls,
            channels_json=_channels_json(outcome.channels),
            **record_extras,
        )

    if measure_baseline:
        key = BaselineKey("cmd", args.target, "", "")
        return _run_baseline_phase(
            runner_label, args, n, _invoke, _record, key, _baseline_conditions(args, n), head_sha
        )

    if compare_baseline:
        baseline_of = getattr(args, "baseline_of", None)
        assert baseline_of is not None  # refused above when missing
        resolved = _resolve_baseline_of(baseline_of, current_input_hash="")
        if isinstance(resolved, str):
            print(resolved, file=sys.stderr)
            return 2
        conditions = _baseline_conditions(args, n)
        cmp_refusal = _compare_baseline_refusal(resolved, conditions)
        if cmp_refusal is not None:
            print(cmp_refusal, file=sys.stderr)
            return 2
        return _run_compare_arm(
            runner_label, args, n, _invoke, _record, read_baseline(resolved, conditions), head_sha
        )

    if n > 1:
        res = _run_sample_loop(runner_label, args, n, _invoke, _record)
        _report_samples(
            runner_label,
            res.tally,
            res.entries,
            args,
            label=res.label,
            prepatch_evidence=res.prepatch_evidence,
            target_history=res.target_history,
        )
        return res.exit_code

    result, duration_ms, side_effects = _invoke_with_side_effects(_invoke, args)
    rc, outcome = _evaluate_and_report(
        runner_label, result, args, side_effects=side_effects, duration_ms=duration_ms
    )
    try:
        _record(result, duration_ms, outcome)
    except Exception as exc:
        print(f"error: retry of attempt {retry_of} was not recorded: {exc}", file=sys.stderr)
        return 1
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

    head_sha = _git_output("rev-parse", "HEAD")
    cell_key = _cell_key("mcp", args.target, head_sha)
    retry_of = getattr(args, "retry_of", None)
    samples_refusal = _retry_samples_refusal(retry_of, args)
    if samples_refusal is not None:
        print(samples_refusal, file=sys.stderr)
        return 1
    n = _effective_samples(args, RunnerType.MCP)
    # ENH-3435: baseline flag refusals gate before the retry gate so a
    # baseline+--retry-of combo reports the baseline refusal (exit 2), and a
    # clean baseline invocation never pays the retry-gate DB lookup.
    baseline_refusal = _baseline_flag_refusal(args, n, runner="mcp", file_shaped=False)
    if baseline_refusal is not None:
        print(baseline_refusal, file=sys.stderr)
        return 2
    refusal = _retry_gate(retry_of, cell_key)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 1
    measure_baseline = getattr(args, "measure_baseline", False)
    compare_baseline = getattr(args, "compare_baseline", False)
    baseline_mode = bool(measure_baseline or compare_baseline)
    input_hash = _input_hash(params)  # what was asked: the canonical --args JSON
    record_extras = _baseline_record_extras(args, input_hash=input_hash) if baseline_mode else {}

    def _invoke() -> tuple[RunnerResult, int]:
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
        return result, duration_ms

    def _record(result: RunnerResult, duration_ms: int, outcome: HarnessEvalOutcome) -> int | None:
        dirty_val = _git_dirty()
        dirty_int: int | None = None if dirty_val is None else int(dirty_val)
        return _record_harness_event(
            runner="mcp",
            target=args.target,
            exit_code=result.exit_code,
            semantic_verdict=outcome.verdict,
            semantic_passed=None if outcome.abstained else outcome.passed,
            timed_out=result.timed_out,
            duration_ms=duration_ms,
            head_sha=head_sha,
            cell_key=cell_key,
            retry_of=retry_of,
            target_content_hash="" if baseline_mode else None,
            dirty=dirty_int,
            loud=baseline_mode,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_tokens=result.cache_read_tokens,
            cache_creation_tokens=result.cache_creation_tokens,
            tool_calls=result.tool_calls,
            channels_json=_channels_json(outcome.channels),
            **record_extras,
        )

    if measure_baseline:
        key = BaselineKey("mcp", args.target, input_hash, "")
        return _run_baseline_phase(
            runner_label, args, n, _invoke, _record, key, _baseline_conditions(args, n), head_sha
        )

    if compare_baseline:
        baseline_of = getattr(args, "baseline_of", None)
        assert baseline_of is not None  # refused above when missing
        resolved = _resolve_baseline_of(baseline_of, current_input_hash=input_hash)
        if isinstance(resolved, str):
            print(resolved, file=sys.stderr)
            return 2
        conditions = _baseline_conditions(args, n)
        cmp_refusal = _compare_baseline_refusal(resolved, conditions)
        if cmp_refusal is not None:
            print(cmp_refusal, file=sys.stderr)
            return 2
        return _run_compare_arm(
            runner_label, args, n, _invoke, _record, read_baseline(resolved, conditions), head_sha
        )

    if n > 1:
        res = _run_sample_loop(runner_label, args, n, _invoke, _record)
        _report_samples(
            runner_label,
            res.tally,
            res.entries,
            args,
            label=res.label,
            prepatch_evidence=res.prepatch_evidence,
            target_history=res.target_history,
        )
        return res.exit_code

    result, duration_ms, side_effects = _invoke_with_side_effects(_invoke, args)
    rc, outcome = _evaluate_and_report(
        runner_label, result, args, side_effects=side_effects, duration_ms=duration_ms
    )
    try:
        _record(result, duration_ms, outcome)
    except Exception as exc:
        print(f"error: retry of attempt {retry_of} was not recorded: {exc}", file=sys.stderr)
        return 1
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
    head_sha = _git_output("rev-parse", "HEAD")
    cell_key = _cell_key("prompt", args.target, head_sha)
    retry_of = getattr(args, "retry_of", None)
    samples_refusal = _retry_samples_refusal(retry_of, args)
    if samples_refusal is not None:
        print(samples_refusal, file=sys.stderr)
        return 1
    n = _effective_samples(args, RunnerType.PROMPT)
    # ENH-3435: baseline flag refusals gate before the retry gate so a
    # baseline+--retry-of combo reports the baseline refusal (exit 2), and a
    # clean baseline invocation never pays the retry-gate DB lookup.
    baseline_refusal = _baseline_flag_refusal(args, n, runner="prompt", file_shaped=False)
    if baseline_refusal is not None:
        print(baseline_refusal, file=sys.stderr)
        return 2
    refusal = _retry_gate(retry_of, cell_key)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 1
    measure_baseline = getattr(args, "measure_baseline", False)
    compare_baseline = getattr(args, "compare_baseline", False)
    baseline_mode = bool(measure_baseline or compare_baseline)
    # The prompt text is both the input and the content (a mutated prompt is a
    # different cell with no discoverable incumbent) — input_hash stays "".
    record_extras = _baseline_record_extras(args, input_hash="") if baseline_mode else {}
    target_hash = _hash_bytes(args.target.encode("utf-8"))

    def _invoke() -> tuple[RunnerResult, int]:
        return _run_prompt_action(args.target, args)

    def _record(result: RunnerResult, duration_ms: int, outcome: HarnessEvalOutcome) -> int | None:
        dirty_val = _git_dirty()
        dirty_int: int | None = None if dirty_val is None else int(dirty_val)
        return _record_harness_event(
            runner="prompt",
            target=args.target,
            exit_code=result.exit_code,
            semantic_verdict=outcome.verdict,
            semantic_passed=None if outcome.abstained else outcome.passed,
            timed_out=result.timed_out,
            duration_ms=duration_ms,
            head_sha=head_sha,
            cell_key=cell_key,
            retry_of=retry_of,
            target_content_hash=target_hash,
            dirty=dirty_int,
            loud=baseline_mode,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_tokens=result.cache_read_tokens,
            cache_creation_tokens=result.cache_creation_tokens,
            tool_calls=result.tool_calls,
            channels_json=_channels_json(outcome.channels),
            **record_extras,
        )

    if measure_baseline:
        key = BaselineKey("prompt", args.target, "", target_hash)
        return _run_baseline_phase(
            runner_label, args, n, _invoke, _record, key, _baseline_conditions(args, n), head_sha
        )

    if compare_baseline:
        baseline_of = getattr(args, "baseline_of", None)
        assert baseline_of is not None  # refused above when missing
        resolved = _resolve_baseline_of(baseline_of, current_input_hash="")
        if isinstance(resolved, str):
            print(resolved, file=sys.stderr)
            return 2
        conditions = _baseline_conditions(args, n)
        cmp_refusal = _compare_baseline_refusal(resolved, conditions)
        if cmp_refusal is not None:
            print(cmp_refusal, file=sys.stderr)
            return 2
        return _run_compare_arm(
            runner_label, args, n, _invoke, _record, read_baseline(resolved, conditions), head_sha
        )

    if n > 1:
        res = _run_sample_loop(runner_label, args, n, _invoke, _record)
        _report_samples(
            runner_label,
            res.tally,
            res.entries,
            args,
            label=res.label,
            prepatch_evidence=res.prepatch_evidence,
            target_history=res.target_history,
        )
        return res.exit_code

    result, duration_ms, side_effects = _invoke_with_side_effects(_invoke, args)
    rc, outcome = _evaluate_and_report(
        runner_label, result, args, side_effects=side_effects, duration_ms=duration_ms
    )
    try:
        _record(result, duration_ms, outcome)
    except Exception as exc:
        print(f"error: retry of attempt {retry_of} was not recorded: {exc}", file=sys.stderr)
        return 1
    return rc


def cmd_dsl(args: argparse.Namespace) -> int:  # noqa: PLR0912, PLR0915 — grading state machine
    """Run a DSL task set, grading each task against its own `expected:` mapping.

    BUG-3196: a flagless run previously reported a 100% pass rate unconditionally.
    See the issue's "Decision: exit codes" table for the full precedence.
    """
    from little_loops.history_reader import admissions_by_reason
    from little_loops.session_store import resolve_history_db

    # ENH-3435 Scope Boundaries: a DSL baseline arm is a task-set-breadth
    # question, not a repetition-depth one (the dsl runner has no per-task n
    # of the shape the baseline phase needs), so both flags are refused here;
    # a follow-up issue defines the DSL baseline arm.
    if getattr(args, "measure_baseline", False) or getattr(args, "compare_baseline", False):
        print(
            "error: --measure-baseline/--compare-baseline: not supported on the dsl "
            "runner (a DSL baseline arm is a follow-up)",
            file=sys.stderr,
        )
        return 2

    # ENH-3415 Scope Boundaries: the dsl runner already resamples across
    # tasks with its own parent/child harness_events rows; per-task
    # resampling would multiply cost and complicate that row structure, so
    # it is a follow-up, not this issue.
    samples = getattr(args, "samples", None)
    if samples is not None and samples > 1:
        print(
            f"error: --samples {samples}: not supported on the dsl runner "
            "(it already resamples across tasks)",
            file=sys.stderr,
        )
        return 1

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

    retry_of = getattr(args, "retry_of", None)
    if retry_of is not None and path.is_dir():
        print(
            f"error: --retry-of {retry_of}: requires a single task-file path, "
            f"got a directory: {path}",
            file=sys.stderr,
        )
        return 1

    head_sha = _git_output("rev-parse", "HEAD")

    if retry_of is not None:
        retry_cell_key = _cell_key("dsl-task", task_files[0].name, head_sha)
        refusal = _retry_gate(retry_of, retry_cell_key)
        if refusal is not None:
            print(refusal, file=sys.stderr)
            return 1

    total = 0
    graded_pass = 0
    graded_total = 0
    ungraded_count = 0
    abstain_count = 0
    errored_count = 0
    failures: list[str] = []
    written_ids: list[int] = []

    aggregate_ts = _now_iso()
    aggregate_id: int | None = None
    dirty_val = _git_dirty()
    dirty_int: int | None = None if dirty_val is None else int(dirty_val)
    with contextlib.suppress(Exception):
        aggregate_id = record_harness_event(
            DEFAULT_DB_PATH,
            ts=aggregate_ts,
            runner="dsl",
            target=str(path),
            head_sha=head_sha,
            branch=_git_output("rev-parse", "--abbrev-ref", "HEAD"),
            target_path=str(path),
            target_content_hash=_hash_file(path),
            dirty=dirty_int,
        )

    for task_file in task_files:
        total += 1
        task = _load_task(task_file)

        task_retry_of = retry_of if task_file is task_files[0] else None
        task_cell_key = _cell_key("dsl-task", task_file.name, head_sha)

        if task is None:
            failures.append(f"{task_file.name} (malformed task file)")
            graded_total += 1
            try:
                written_id = _record_harness_event(
                    runner="dsl-task",
                    target=task_file.name,
                    exit_code=1,
                    semantic_verdict=None,
                    semantic_passed=False,
                    timed_out=False,
                    duration_ms=0,
                    head_sha=head_sha,
                    cell_key=task_cell_key,
                    retry_of=task_retry_of,
                    parent_id=aggregate_id,
                    target_path=str(task_file),
                    target_content_hash=_hash_file(task_file),
                    dirty=dirty_int,
                )
                if written_id is not None:
                    written_ids.append(written_id)
            except Exception as exc:
                print(
                    f"error: retry of attempt {task_retry_of} was not recorded: {exc}",
                    file=sys.stderr,
                )
                return 1
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
            # ENH-3462 D1/D9: copy the declared-evidence flags per task so
            # they aren't silently inert on the dsl runner (AC11).
            evidence=getattr(args, "evidence", None) or [],
            require_artifact=getattr(args, "require_artifact", None) or [],
            forbid_path=getattr(args, "forbid_path", None) or [],
            expect_no_git_changes=getattr(args, "expect_no_git_changes", False),
        )
        result, duration_ms, side_effects = _invoke_with_side_effects(
            functools.partial(_run_prompt_action, prompt_text, task_args), task_args
        )

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
            runner_label,
            result,
            task_args,
            expected_grade=expected_grade,
            skip_history=True,
            side_effects=side_effects,
            duration_ms=duration_ms,
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

        try:
            written_id = _record_harness_event(
                runner="dsl-task",
                target=task_file.name,
                exit_code=result.exit_code,
                semantic_verdict=outcome.verdict,
                semantic_passed=None if outcome.abstained else outcome.passed,
                timed_out=result.timed_out,
                duration_ms=duration_ms,
                head_sha=head_sha,
                cell_key=task_cell_key,
                retry_of=task_retry_of,
                parent_id=aggregate_id,
                target_path=str(task_file),
                target_content_hash=_hash_file(task_file),
                dirty=dirty_int,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cache_read_tokens=result.cache_read_tokens,
                cache_creation_tokens=result.cache_creation_tokens,
                tool_calls=result.tool_calls,
                channels_json=_channels_json(outcome.channels),
            )
            if written_id is not None:
                written_ids.append(written_id)
        except Exception as exc:
            print(
                f"error: retry of attempt {task_retry_of} was not recorded: {exc}",
                file=sys.stderr,
            )
            return 1

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
    admissions = admissions_by_reason(resolve_history_db(DEFAULT_DB_PATH), written_ids)
    if admissions:
        breakdown = ", ".join(
            f"{reason}×{count}"
            for reason, count in sorted(admissions.items(), key=lambda kv: -kv[1])
        )
        lines.append(f"  admissions: {sum(admissions.values())} ({breakdown})")
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
