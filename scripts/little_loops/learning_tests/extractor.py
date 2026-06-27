"""LLM-based extraction of external API dependencies from issue text (ENH-2209).

Exposes ``extract_learning_targets()`` as an importable callable Python module
so downstream tools (ENH-2210 sprint pre-flight) can import it directly without
a shell-out. The default LLM call shells out through the active host CLI via
``resolve_host()`` (the same host abstraction used by
``session_store._call_llm_for_summary``) so extraction works with whichever
backend ``ll-auto`` / ``ll-sprint`` / ``ll-parallel`` is configured to use, not
just Anthropic. The ``llm_call`` parameter allows mock injection for unit tests.

Follow the same pattern as ``gate.py`` (``is_record_stale``) — importable helper,
unit-testable with mock injection.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from collections.abc import Callable
from typing import TYPE_CHECKING

from little_loops.host_runner import resolve_host
from little_loops.issue_parser import slugify

if TYPE_CHECKING:
    from little_loops.issue_parser import IssueInfo

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
Analyze the following issue text and identify all external packages, SDKs, or \
third-party API surfaces that the implementation plan assumes behavior of.

Include:
- Third-party Python packages (e.g. anthropic, requests, boto3, stripe)
- External APIs and services (e.g. Stripe webhooks, GitHub API)
- SDKs for external platforms or cloud services
- Non-obvious stdlib components whose contract is non-trivial (e.g. asyncio, multiprocessing)

Exclude:
- Code internal to the project being built
- Standard Python builtins (str, dict, list, int, etc.)
- Contract-stable stdlib modules (os, sys, pathlib, json, re, datetime)

For each identified dependency, provide its canonical short name only \
(no version qualifier, no description).

Return a JSON object as the LAST line of your response in exactly this format:
TARGETS_JSON:{{"targets": ["name1", "name2"], "count": N}}

If there are no external dependencies, return:
TARGETS_JSON:{{"targets": [], "count": 0}}

Issue text to analyze:
---
{issue_text}
---\
"""

_TARGETS_JSON_RE = re.compile(r"TARGETS_JSON:(\{.*\})", re.MULTILINE)

# Host-call timeout for the default extraction call (seconds), matching
# session_store._call_llm_for_summary.
_LLM_TIMEOUT_S = 60


def _default_llm_call(prompt: str) -> str:
    """Call the active host CLI for extraction and return the response prose.

    Routes through ``resolve_host().build_blocking_json()`` (mirroring
    ``session_store._call_llm_for_summary``) so extraction respects the
    configured backend (``LL_HOST_CLI`` / ``orchestration.host_cli``) instead of
    instantiating the Anthropic SDK directly. ``model=None`` lets the host pick
    its own default model — a hardcoded Anthropic model id would fail against a
    non-Anthropic backend.

    Fails soft: returns ``""`` on any host-call or parse failure (logged as a
    warning). The learning gate is a best-effort safety net, so a failed
    extraction must degrade to "no targets" rather than abort the whole run.
    """
    try:
        inv = resolve_host().build_blocking_json(prompt=prompt, model=None)
        proc = subprocess.run(
            [inv.binary, *inv.args],
            env={**os.environ, **inv.env},
            capture_output=True,
            text=True,
            timeout=_LLM_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        logger.warning("_default_llm_call: host CLI timed out after %ds", _LLM_TIMEOUT_S)
        return ""
    except FileNotFoundError:
        logger.warning(
            "_default_llm_call: host CLI not found. Install the active host CLI (see LL_HOST_CLI)."
        )
        return ""

    if proc.returncode != 0:
        stderr_preview = proc.stderr.strip()[:200] if proc.stderr else "(no stderr)"
        logger.warning(
            "_default_llm_call: host CLI returned exit code %d (stderr: %s)",
            proc.returncode,
            stderr_preview,
        )
        return ""

    if not proc.stdout.strip():
        logger.warning("_default_llm_call: host CLI returned empty stdout on exit 0")
        return ""

    # Parse the JSON envelope and extract the prose 'result' field — the same
    # pattern as session_store._call_llm_for_summary. The prose still carries the
    # TARGETS_JSON:{...} line that _TARGETS_JSON_RE scans for downstream.
    try:
        stdout = proc.stdout.strip()
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            # Try JSONL: take the last non-empty line
            lines = [line for line in stdout.split("\n") if line.strip()]
            if not lines:
                raise
            envelope = json.loads(lines[-1])

        if envelope.get("subtype") == "error_max_structured_output_retries":
            logger.warning(
                "_default_llm_call: host CLI could not produce valid output after retries"
            )
            return ""
        if envelope.get("is_error", False):
            err_text = str(envelope.get("result", "") or "")[:200]
            logger.warning("_default_llm_call: host CLI reported error: %s", err_text)
            return ""

        result = envelope.get("result", "")
        return str(result) if result else ""
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raw_preview = proc.stdout[:300] if proc.stdout else "(empty)"
        logger.warning(
            "_default_llm_call: failed to parse host response: %s (raw: %s)", e, raw_preview
        )
        return ""


def extract_learning_targets(
    issue_text: str,
    *,
    llm_call: Callable[[str], str] | None = None,
) -> list[str]:
    """Extract external API dependency names from issue text via LLM.

    Returns a deduplicated list of target names. Issues with no external
    dependencies return an empty list; callers should omit the frontmatter
    field rather than writing an empty list.

    Args:
        issue_text: Full issue file content (frontmatter + body).
        llm_call: Optional callable accepting a prompt string and returning
            response text. Defaults to a host-aware call via ``resolve_host()``.
            Inject a mock for unit tests.

    Returns:
        Deduplicated list of target names (first-seen form preserved),
        e.g. ``["anthropic", "requests"]``.
    """
    caller = llm_call if llm_call is not None else _default_llm_call
    prompt = _EXTRACTION_PROMPT.format(issue_text=issue_text)
    response = caller(prompt)

    match = _TARGETS_JSON_RE.search(response)
    if not match:
        return []

    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, KeyError):
        return []

    raw_targets: list[str] = data.get("targets") or []
    seen: set[str] = set()
    result: list[str] = []
    for t in raw_targets:
        name = t.strip()
        if not name:
            continue
        slug = slugify(name)
        if slug not in seen:
            seen.add(slug)
            result.append(name)
    return result


def resolve_learning_targets(
    issue: IssueInfo,
    *,
    llm_call: Callable[[str], str] | None = None,
) -> list[str]:
    """Return learning-test targets for an issue.

    Returns ``issue.learning_tests_required`` when non-None (field-first).
    Falls back to JIT extraction from issue text via ``extract_learning_targets``.
    Returns [] on OSError (unreadable issue file).

    The ``is not None`` sentinel is intentional: ``[]`` means "proven empty —
    no external deps" and must NOT trigger JIT extraction; ``None`` means
    "field not yet populated" and must trigger it.
    """
    if issue.learning_tests_required is not None:
        return issue.learning_tests_required
    try:
        text = issue.path.read_text()
    except OSError:
        return []
    return extract_learning_targets(text, llm_call=llm_call)
