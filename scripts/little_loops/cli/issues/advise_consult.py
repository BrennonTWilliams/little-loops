"""ll-issues advise-consult: shared second-model readiness consult helper (ENH-3632).

Calls `little_loops.advisor.consult_for_trigger("refine_ready", ..., manual=True)`
in-process, persists the verdict under `--run-dir`, and prints exactly one
routing token (`PROCEED`/`VETO`/`SKIPPED`), always exiting 0. Decomposed from
ENH-3626 (Implementation Steps 1-2); the `refine-to-ready-issue` loop wiring
lives in ENH-3633, the go-no-go waiver veto in ENH-3590.
"""

from __future__ import annotations

import argparse
import logging
import re
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pathlib import Path

    from little_loops.advisor import ConsultOutcome
    from little_loops.config import BRConfig

logger = logging.getLogger(__name__)

AdviseVerdict = Literal["PROCEED", "VETO", "SKIPPED"]

# Excluded from the consult context (and the replay-hash input): frontmatter is
# machine bookkeeping, Session Log/Confidence Check Notes/Codebase Research
# Findings are process trail rather than directive content, and Advisor Veto is
# this helper's own prior verdict -- the advisor must never see its earlier veto.
_TRIM_HEADINGS = (
    "## Session Log",
    "## Confidence Check Notes",
    "### Codebase Research Findings",
    "## Advisor Veto",
)
_TRIM_HEADING_RE = re.compile(
    r"^(?:" + "|".join(re.escape(h) for h in _TRIM_HEADINGS) + r")\s*$",
    re.MULTILINE,
)

# Bounds worst-case consult-context size; generous relative to a typical issue
# body while still capping the pathological case (a heavily-refined issue with
# many research passes folded in).
_CONSULT_CONTEXT_CHAR_LIMIT = 20_000

_PINNED_QUESTION = (
    "Is this issue ready to implement as written? Begin your recommendation with "
    "exactly one word, PROCEED or VETO, then give the reason. VETO only for a "
    "concrete defect that would make implementation fail or be wasted; otherwise "
    "PROCEED."
)


def _strip_named_sections(body: str) -> str:
    """Drop each `_TRIM_HEADINGS` block from *body*, up to the next `#{1,3}` heading.

    Same heading-span-walk shape as `issue_parser._strip_codebase_research_findings`,
    generalized to a fixed list of section names, with the boundary whitespace
    around each removed span normalized (rstrip before / lstrip after, rejoined
    on a blank line). Without this, a removed trailing section (e.g. an
    appended ``## Session Log`` entry) leaves an extra blank line behind that
    it wouldn't otherwise have had -- perturbing the replay-hash input on an
    edit this helper is supposed to treat as a no-op.
    """
    matches = list(_TRIM_HEADING_RE.finditer(body))
    if not matches:
        return body
    kept: list[str] = []
    cursor = 0
    for m in matches:
        kept.append(body[cursor : m.start()].rstrip("\n"))
        next_heading = re.search(r"^#{1,3}\s", body[m.end() :], re.MULTILINE)
        cursor = m.end() + next_heading.start() if next_heading else len(body)
    kept.append(body[cursor:].lstrip("\n"))
    pieces = [piece for piece in kept if piece]
    return "\n\n".join(pieces) + "\n" if pieces else ""


def trim_consult_context(issue_text: str) -> str:
    """Strip frontmatter and process-trail sections from *issue_text*, cap length.

    This is both the text handed to the consult and the replay-hash input
    (Program Design) -- a replayed PROCEED/SKIPPED is discarded when this
    trimmed text changes, but survives edits confined to the stripped
    sections (Session Log appends, a later confidence-check pass).
    """
    from little_loops.frontmatter import strip_frontmatter

    body = strip_frontmatter(issue_text)
    body = _strip_named_sections(body)
    if len(body) > _CONSULT_CONTEXT_CHAR_LIMIT:
        body = body[:_CONSULT_CONTEXT_CHAR_LIMIT]
    return body


def map_advise_verdict(outcome: ConsultOutcome) -> tuple[AdviseVerdict, str]:
    """Map a `ConsultOutcome` to an `AdviseVerdict` plus a log reason.

    `verdict is None` (any `skipped_reason`) -> SKIPPED. Otherwise the
    **leading word** of `recommendation` decides via `parse_lead_word`: `VETO`
    -> VETO, anything else (including no lead match at all, e.g. "no reason to
    VETO") -> PROCEED. No whole-word fallback -- only the lead word counts.
    """
    from little_loops.advisor import parse_lead_word

    if outcome.verdict is None:
        return "SKIPPED", outcome.skipped_reason or "unknown"

    lead = parse_lead_word(outcome.verdict.recommendation, ("PROCEED", "VETO"))
    if lead == "VETO":
        return "VETO", "lead word VETO"
    return "PROCEED", "lead word PROCEED" if lead == "PROCEED" else "no leading VETO"


def add_advise_consult_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the advise-consult subparser on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "advise-consult",
        help="Run one in-process second-model readiness consult and print PROCEED/VETO/SKIPPED",
    )
    p.set_defaults(command="advise-consult")
    p.add_argument("issue_id", help="Issue ID (e.g., 3632, ENH-3632, P3-ENH-3632)")
    p.add_argument(
        "--run-dir",
        required=True,
        help="The run's run_dir (the loop's ${context.run_dir}); verdict persists here",
    )
    p.add_argument(
        "--signal",
        default="refine_ready",
        help="Consult trigger/signal (default: refine_ready)",
    )
    p.add_argument(
        "--question",
        default=_PINNED_QUESTION,
        help="Override the pinned readiness question (e.g. for ENH-3590's waiver veto)",
    )
    p.add_argument(
        "--write-note",
        action="store_true",
        help="On VETO, write/replace the issue's ## Advisor Veto section; on PROCEED, "
        "remove a stale one",
    )
    add_config_arg(p)
    return p


_ADVISOR_VETO_HEADING_RE = re.compile(r"^## Advisor Veto\s*$", re.MULTILINE)


def _remove_advisor_veto_section(content: str) -> str:
    """Remove a `## Advisor Veto` block (heading through the next `#{1,2}` heading/EOF)."""
    match = _ADVISOR_VETO_HEADING_RE.search(content)
    if not match:
        return content
    next_heading = re.search(r"^#{1,2}\s", content[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(content)
    before = content[: match.start()].rstrip("\n")
    after = content[end:]
    return f"{before}\n\n{after.lstrip(chr(10))}" if after.strip() else f"{before}\n"


def _apply_write_note(path: Path, verdict: AdviseVerdict, recommendation: str | None) -> None:
    content = path.read_text()
    content = _remove_advisor_veto_section(content)
    if verdict == "VETO" and recommendation:
        content = f"{content.rstrip(chr(10))}\n\n## Advisor Veto\n\n{recommendation}\n"
    path.write_text(content)


def _verdict_path(run_dir: Path, issue_id: str) -> Path:
    return run_dir / f"advise-{issue_id}.verdict"


def _payload_path(run_dir: Path, issue_id: str) -> Path:
    return run_dir / f"advise-{issue_id}.json"


def _persist(run_dir: Path, issue_id: str, payload: dict, token: str, context_hash: str) -> None:
    from little_loops.file_utils import atomic_write_json

    atomic_write_json(_payload_path(run_dir, issue_id), payload)
    atomic_write_json(
        _verdict_path(run_dir, issue_id), {"token": token, "context_hash": context_hash}
    )


def cmd_advise_consult(config: BRConfig, args: argparse.Namespace) -> int:
    """Replay, preflight, consult, persist, print one token; always returns 0.

    Never raises: any unexpected failure (including a `BRConfig` load issue
    surfacing from a lazily-resolved import) is caught and mapped to SKIPPED,
    so this helper can never stall a loop's `next-obligation`-style dispatch.
    """
    try:
        return _cmd_advise_consult_inner(config, args)
    except Exception:
        logger.exception("advise-consult: unexpected failure for %s", args.issue_id)
        print("SKIPPED")
        return 0


def _cmd_advise_consult_inner(config: BRConfig, args: argparse.Namespace) -> int:
    import hashlib
    import os
    from pathlib import Path as _Path

    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter

    run_dir = _Path(args.run_dir)
    issue_path = _resolve_issue_id(config, args.issue_id)
    if issue_path is None:
        print("SKIPPED")
        return 0

    try:
        issue_text = issue_path.read_text()
    except OSError:
        print("SKIPPED")
        return 0

    try:
        fm = parse_frontmatter(issue_text, coerce_types=True)
    except Exception:
        fm = {}
    issue_id = str(fm.get("id") or args.issue_id)

    trimmed = trim_consult_context(issue_text)
    context_hash = hashlib.sha256(trimmed.encode("utf-8")).hexdigest()

    verdict_path = _verdict_path(run_dir, issue_id)
    if verdict_path.exists():
        try:
            import json

            record = json.loads(verdict_path.read_text())
        except (OSError, ValueError):
            record = None
        if record is not None:
            token = record.get("token")
            if token == "VETO" or record.get("context_hash") == context_hash:
                print(token)
                return 0

    if not config.advisor.host:
        logger.warning("advise-consult: advisor.host unset, skipping %s", issue_id)
        _persist(
            run_dir,
            issue_id,
            {"skipped_reason": "not_configured", "preflight": True},
            "SKIPPED",
            context_hash,
        )
        if args.write_note:
            _apply_write_note(issue_path, "SKIPPED", None)
        print("SKIPPED")
        return 0

    os.environ["LL_ISSUE_ID"] = issue_id

    from little_loops.advisor import consult_for_trigger

    outcome = consult_for_trigger(
        args.signal, question=args.question, context=trimmed, config=config, manual=True
    )
    verdict, log_reason = map_advise_verdict(outcome)
    if verdict == "SKIPPED" and log_reason in ("not_configured", "floor_violation"):
        logger.warning("advise-consult: %s (%s)", log_reason, issue_id)

    if outcome.verdict is not None:
        payload = {
            "recommendation": outcome.verdict.recommendation,
            "risks": outcome.verdict.risks,
            "confidence": outcome.verdict.confidence,
            "dissent": outcome.verdict.dissent,
            "host": outcome.verdict.host,
            "model": outcome.verdict.model,
        }
    else:
        payload = {"skipped_reason": outcome.skipped_reason, "error": outcome.error}

    _persist(run_dir, issue_id, payload, verdict, context_hash)

    if args.write_note:
        recommendation = outcome.verdict.recommendation if outcome.verdict is not None else None
        _apply_write_note(issue_path, verdict, recommendation)

    print(verdict)
    return 0
