"""Run ``/ll:ready-issue`` with containment for non-compliant model turns.

``parse_ready_issue_output`` returns ``UNKNOWN`` when the model's reply
contains nothing verdict-shaped. That is a distinct failure from a real
``NOT_READY``: the parser already tries five progressively looser extraction
strategies before giving up, so ``UNKNOWN`` means the model did not answer the
question at all — not that the issue was rejected.

Collapsing the two costs whole runs. An observed autodev failure
(``.loops/runs/autodev-20260801T214427/``) burned 14m17s of successful
refine/wire/confidence work because a single ready-issue turn replied
"I don't see an actual request in your message — just system context." and
exited 0. A byte-identical prompt 21 minutes earlier worked fine, so the
misread is probabilistic, not deterministic — exactly the shape a retry fixes.

The retry is *differentiated*, not a plain re-roll: it re-sends the expanded
skill body with an explicit imperative tail appended, which directly counters
the "this is reference material" misread rather than re-rolling the same dice.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from little_loops.output_parsing import parse_ready_issue_output

if TYPE_CHECKING:  # pragma: no cover - typing only
    from little_loops.config import BRConfig

# NOTE: ``BRConfig`` and ``expand_skill`` are deliberately not imported at
# module scope. ``config.core`` imports ``parallel.types``, whose package
# __init__ pulls in ``worker_pool`` -- one of this module's two callers -- so a
# module-level config import here closes an import cycle. ``expand_skill``
# imports BRConfig itself, so it is imported inside build_retry_command for the
# same reason.

__all__ = ["IMPERATIVE_TAIL", "build_retry_command", "run_ready_issue_with_retry"]

#: Appended to the expanded skill body on a retry. ``{target}`` is the issue ID
#: or path that ``$ARGUMENTS`` was substituted with.
IMPERATIVE_TAIL = (
    "\n\n---\n\n"
    "Now execute the instructions above for: {target}\n"
    "This is a request to act, not reference material. "
    "You MUST end your response with a `## VERDICT` section."
)


def build_retry_command(target: str, config: BRConfig) -> str:
    """Build the differentiated retry prompt for *target*.

    Always the pre-expanded form plus :data:`IMPERATIVE_TAIL`, regardless of
    what the first attempt used, so an ll-parallel worker that opened with the
    slash form still gets the hardened prompt on retry.

    Falls back to a plain ``/ll:ready-issue <target>`` re-roll when
    ``expand_skill`` is unavailable (its documented ``None`` return). The tail
    is deliberately *not* appended in that case: trailing prose on a slash
    command would be swallowed as ``$ARGUMENTS``.
    """
    from little_loops.skill_expander import expand_skill

    body = expand_skill("ready-issue", [target], config)
    if body is None:
        return f"/ll:ready-issue {target}"
    return body + IMPERATIVE_TAIL.format(target=target)


def run_ready_issue_with_retry(
    *,
    target: str,
    initial_command: str,
    run: Callable[[str], subprocess.CompletedProcess[str]],
    config: BRConfig,
    retries: int = 1,
    log: Callable[[str], None] | None = None,
) -> tuple[dict[str, Any], subprocess.CompletedProcess[str]]:
    """Run ready-issue, retrying only when the verdict comes back ``UNKNOWN``.

    Args:
        target: Issue ID or path — what ``$ARGUMENTS`` resolves to.
        initial_command: First-attempt command, already built by the caller.
        run: Callable that executes a command and returns a CompletedProcess.
        config: Project config, used to build the retry prompt.
        retries: Additional attempts allowed after an ``UNKNOWN`` verdict.
            ``0`` disables retrying entirely.
        log: Optional sink for retry notices.

    Returns:
        ``(parsed, result)`` from the final attempt, so all downstream handling
        (path validation, corrections, CLOSE/BLOCKED/NOT_READY) runs unchanged
        against whichever attempt won.

    A non-zero return code is never retried — that is a different failure mode
    which both callers already handle on their own terms.
    """
    result = run(initial_command)
    parsed = parse_ready_issue_output(result.stdout or "")

    attempts_left = max(0, retries)
    while attempts_left > 0 and result.returncode == 0 and parsed["verdict"] == "UNKNOWN":
        attempts_left -= 1
        if log is not None:
            log(
                f"ready-issue returned no parseable verdict for {target} — "
                f"retrying with an explicit execution directive "
                f"({retries - attempts_left}/{retries})"
            )
        result = run(build_retry_command(target, config))
        parsed = parse_ready_issue_output(result.stdout or "")

    return parsed, result
