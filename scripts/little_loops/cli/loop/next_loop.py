"""ll-loop next-loop: Suggest the next loop to run from execution history."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.logger import Logger


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
_DECAY_HALF_LIFE_DAYS = 7.0  # recency decay: halves every 7 days


def _recency_score(started_at: str | None) -> float:
    """Exponential decay score in [0, 1] based on days since last run."""
    if not started_at:
        return 0.0
    try:
        ts = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        days = (now - ts).total_seconds() / 86400.0
        import math

        return math.exp(-days * math.log(2) / _DECAY_HALF_LIFE_DAYS)
    except (ValueError, TypeError):
        return 0.0


def _score_loop(runs: list[dict[str, Any]]) -> tuple[float, float, str | None]:
    """Return (score, success_rate, last_started_at)."""
    if not runs:
        return 0.0, 1.0, None

    count = len(runs)
    successes = sum(1 for r in runs if r.get("status") in _SUCCESS_STATUSES)
    success_rate = successes / count if count else 1.0

    # Most recent run for recency
    dated = [r for r in runs if r.get("started_at")]
    dated.sort(key=lambda r: r["started_at"], reverse=True)
    last_started_at = dated[0]["started_at"] if dated else None

    recency = _recency_score(last_started_at)
    # Weighted: 50% frequency (log-scale), 30% recency, 20% success rate
    import math

    freq_score = math.log1p(count) / math.log1p(50)  # cap normalisation at 50 runs
    score = 0.50 * freq_score + 0.30 * recency + 0.20 * success_rate
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
) -> str:
    parts = [f"{run_count} run{'s' if run_count != 1 else ''}"]
    if last_started_at:
        try:
            ts = datetime.fromisoformat(last_started_at.replace("Z", "+00:00"))
            ago = datetime.now(UTC) - ts
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
) -> int:
    """Suggest the next loop(s) to run based on execution history."""
    from little_loops.cli.output import colorize, print_json

    count = getattr(args, "count", 1)
    as_json = getattr(args, "json", False)
    execute = getattr(args, "execute", False)
    exclude = set(getattr(args, "exclude", None) or [])

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
        score, success_rate, last_started_at = _score_loop(runs)
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
            param_note = f"input resolved ({item_count} items)" if item_count > 1 else "input resolved"
        elif loop_name in _PARAM_RESOLVERS:
            param_note = "input resolver found no active items"

        rationale = _build_rationale(run_count, success_rate, last_started_at, param_note)
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
        score_str = colorize(f"score={c.score:.3f}", "2")
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
            show_diagrams=False,
            clear=False,
            queue=False,
            context=[f"{k}={v}" for k, v in top_candidate.context.items()],
            program_md=None,
            builtin=False,
            worktree=False,
            handoff_threshold=None,
            context_limit=None,
        )
        return cmd_run(top_candidate.loop, run_args, loops_dir, logger)

    return 0
