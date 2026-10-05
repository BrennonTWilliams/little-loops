"""ll-loop next-loop: Suggest the next loop to run from execution history."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.config.features import NextConfigError
from little_loops.logger import Logger
from little_loops.utility import frequency_score, recency_score, weighted_sum

if TYPE_CHECKING:
    from little_loops.config import BRConfig


@dataclass
class LoopCandidate:
    """A scored loop candidate for next-loop suggestions."""

    loop: str
    score: float
    input: str | None
    context: dict[str, str]
    rationale: str
    command: str
    run_count: int = 0
    last_run: str | None = None
    success_rate: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop": self.loop,
            "input": self.input,
            "context": self.context,
            "score": round(self.score, 4),
            "rationale": self.rationale,
            "command": self.command,
        }


# ---------------------------------------------------------------------------
# History scanning
# ---------------------------------------------------------------------------


def _scan_history(loops_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Scan .loops/.history/ and return per-loop run metadata.

    Returns dict mapping loop_name → list of {status, started_at, iterations}.
    """
    from little_loops.fsm.persistence import HISTORY_DIR, _parse_run_folder

    history_base = loops_dir / HISTORY_DIR
    if not history_base.exists():
        return {}

    per_loop: dict[str, list[dict[str, Any]]] = {}
    for run_dir in sorted(history_base.iterdir()):
        if not run_dir.is_dir():
            continue
        parsed = _parse_run_folder(run_dir.name)
        if not parsed:
            continue
        run_id, loop_name = parsed
        state_file = run_dir / "state.json"
        entry: dict[str, Any] = {"run_id": run_id, "status": None, "started_at": None}
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
                entry["status"] = data.get("status")
                entry["started_at"] = data.get("started_at")
            except (ValueError, OSError):
                pass
        per_loop.setdefault(loop_name, []).append(entry)

    return per_loop


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_SUCCESS_STATUSES = {"completed"}


class _AggregationError(Exception):
    """The additive aggregate rejected the resolved weights/scores (e.g. overflow)."""


def _score_loop(
    runs: list[dict[str, Any]],
    *,
    as_of: datetime,
    weights: Mapping[str, float],
) -> tuple[float, float, str | None]:
    """Return (score, success_rate, last_started_at).

    *weights* must iterate in canonical ``frequency, recency, success`` order (as
    ``NextConfig.resolve_loop_history_weights`` returns) so the additive sum keeps
    its legacy association. Only the aggregate is translated to
    :class:`_AggregationError`; curve exceptions propagate unchanged.
    """
    if not runs:
        return 0.0, 1.0, None

    count = len(runs)
    successes = sum(1 for r in runs if r.get("status") in _SUCCESS_STATUSES)
    success_rate = successes / count if count else 1.0

    # Most recent run for recency
    dated = [r for r in runs if r.get("started_at")]
    dated.sort(key=lambda r: r["started_at"], reverse=True)
    last_started_at = dated[0]["started_at"] if dated else None

    scores = {
        "frequency": frequency_score(count),
        "recency": recency_score(last_started_at, as_of=as_of),
        "success": success_rate,
    }
    try:
        score = weighted_sum(scores, weights)
    except ValueError as exc:
        raise _AggregationError(str(exc)) from exc
    return score, success_rate, last_started_at


# ---------------------------------------------------------------------------
# Parameter resolver registry
# ---------------------------------------------------------------------------

_ParamResolver = dict[str, str | None]  # {input: ..., **context_keys}


def _resolve_autodev_params(_loops_dir: Path) -> _ParamResolver:  # noqa: ARG001
    """Resolve input params for autodev: return space-joined active issue IDs."""
    try:
        from pathlib import Path as _Path

        from little_loops.cli.issues.search import _load_issues_with_status
        from little_loops.config import BRConfig

        config = BRConfig(_Path.cwd())
        raw = _load_issues_with_status(
            config, include_open=True, include_done=False, include_deferred=False
        )
        ids = [issue.issue_id for issue, _ in raw if issue.issue_id]
        if ids:
            return {"input": " ".join(ids)}
    except Exception:
        pass
    return {}


# Registry: loop name → resolver callable
_PARAM_RESOLVERS: dict[str, Any] = {
    "autodev": _resolve_autodev_params,
}


def _resolve_params(loop_name: str, loops_dir: Path) -> _ParamResolver:
    """Return resolved params for a loop, falling back to empty dict."""
    resolver = _PARAM_RESOLVERS.get(loop_name)
    if resolver is not None:
        try:
            return resolver(loops_dir)
        except Exception:
            pass
    return {}


# ---------------------------------------------------------------------------
# Command building
# ---------------------------------------------------------------------------


def _build_command(loop_name: str, params: _ParamResolver) -> str:
    """Build a shell-ready ll-loop run command string."""
    parts = ["ll-loop", "run", loop_name]
    if params.get("input"):
        parts.append(json.dumps(params["input"]))
    for k, v in params.items():
        if k != "input" and v is not None:
            parts.extend(["--context", f"{k}={v}"])
    return " ".join(parts)


def _build_rationale(
    run_count: int,
    success_rate: float,
    last_started_at: str | None,
    param_note: str,
    *,
    as_of: datetime,
) -> str:
    parts = [f"{run_count} run{'s' if run_count != 1 else ''}"]
    if last_started_at:
        try:
            ts = datetime.fromisoformat(last_started_at.replace("Z", "+00:00"))
            ago = as_of - ts
            days = int(ago.total_seconds() / 86400)
            if days == 0:
                parts.append("last run today")
            elif days == 1:
                parts.append("last run yesterday")
            else:
                parts.append(f"last run {days}d ago")
        except (ValueError, TypeError):
            pass
    parts.append(f"{int(success_rate * 100)}% success")
    if param_note:
        parts.append(param_note)
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# cmd_next_loop
# ---------------------------------------------------------------------------


def cmd_next_loop(
    args: argparse.Namespace,
    loops_dir: Path,
    logger: Logger,
    config: BRConfig,
) -> int:
    """Suggest the next loop(s) to run based on execution history.

    Returns 2 (one stderr diagnostic, empty stdout) for invalid ``next`` settings.
    """
    from little_loops.cli.output import colorize, print_json

    count = getattr(args, "count", 1)
    as_json = getattr(args, "json", False)
    execute = getattr(args, "execute", False)
    exclude = set(getattr(args, "exclude", None) or [])

    # Validate before any archive scan so bad config wins even with no history.
    try:
        weights = config.next.resolve_loop_history_weights()
    except NextConfigError as exc:
        print(f"error: invalid next-loop configuration: {exc}", file=sys.stderr)
        return 2

    as_of = datetime.now(UTC)  # one instant shared by scoring and rationale

    history = _scan_history(loops_dir)
    if not history:
        if as_json:
            print_json([])
        else:
            print("No loop history available. Run some loops first.")
        return 1

    # Score each loop
    scored: list[tuple[float, str, float, str | None, int]] = []
    for loop_name, runs in history.items():
        if loop_name in exclude:
            continue
        try:
            score, success_rate, last_started_at = _score_loop(runs, as_of=as_of, weights=weights)
        except _AggregationError as exc:
            print(
                f"error: invalid next-loop configuration: next.loop_history.weights "
                f"cannot score loop {loop_name!r}: {exc}",
                file=sys.stderr,
            )
            return 2
        scored.append((score, loop_name, success_rate, last_started_at, len(runs)))

    if not scored:
        if as_json:
            print_json([])
        else:
            print("No candidates after applying exclusions.")
        return 1

    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:count]

    candidates: list[LoopCandidate] = []
    for score, loop_name, success_rate, last_started_at, run_count in top:
        params = _resolve_params(loop_name, loops_dir)
        param_note = ""
        resolved_input = params.get("input")
        if resolved_input:
            item_count = len(resolved_input.split())
            param_note = (
                f"input resolved ({item_count} items)" if item_count > 1 else "input resolved"
            )
        elif loop_name in _PARAM_RESOLVERS:
            param_note = "input resolver found no active items"

        rationale = _build_rationale(
            run_count, success_rate, last_started_at, param_note, as_of=as_of
        )
        command = _build_command(loop_name, params)

        candidate = LoopCandidate(
            loop=loop_name,
            score=score,
            input=params.get("input"),
            context={k: v for k, v in params.items() if k != "input" and v is not None},
            rationale=rationale,
            command=command,
            run_count=run_count,
            last_run=last_started_at,
            success_rate=success_rate,
        )
        candidates.append(candidate)

    if as_json:
        print_json([c.to_dict() for c in candidates])
        return 0

    # Text output
    label = "suggestion" if len(candidates) == 1 else "suggestions"
    print(colorize(f"Next loop {label}:", "1"))
    print()
    for i, c in enumerate(candidates, 1):
        rank = colorize(f"#{i}", "36;1")
        name = colorize(c.loop, "1")
        score_str = colorize(f"score={c.score:.3f}", "90")
        print(f"  {rank}  {name}  {score_str}")
        print(f"       {colorize(c.rationale, '2')}")
        print(f"       {colorize('$', '32')} {c.command}")
        print()

    if execute:
        top_candidate = candidates[0]
        logger.info(f"Executing: {top_candidate.command}")
        # Build minimal Namespace to call cmd_run
        from little_loops.cli.loop.run import cmd_run

        run_args = argparse.Namespace(
            input=top_candidate.input,
            max_steps=None,
            max_iterations=None,
            delay=None,
            no_llm=False,
            llm_model=None,
            dry_run=False,
            background=False,
            foreground_internal=False,
            instance_id=None,
            quiet=False,
            verbose=False,
            show_diagrams=None,
            diagram_edge_labels=None,
            diagram_state_detail=None,
            diagram_scope=None,
            clear=False,
            queue=False,
            follow=False,
            context=[f"{k}={v}" for k, v in top_candidate.context.items()],
            program_md=None,
            builtin=False,
            worktree=False,
            handoff_threshold=None,
            context_limit=None,
        )
        return cmd_run(top_candidate.loop, run_args, loops_dir, logger)

    return 0
