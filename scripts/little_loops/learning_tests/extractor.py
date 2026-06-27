"""LLM-based extraction of external API dependencies from issue text (ENH-2209).

Exposes ``extract_learning_targets()`` as an importable callable Python module
so downstream tools (ENH-2210 sprint pre-flight) can import it directly without
a shell-out. The Anthropic SDK is used for SDK-direct invocation; the ``llm_call``
parameter allows mock injection for unit tests.

Follow the same pattern as ``gate.py`` (``is_record_stale``) — importable helper,
unit-testable with mock injection.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from little_loops.issue_parser import slugify

if TYPE_CHECKING:
    from little_loops.issue_parser import IssueInfo

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


def _default_llm_call(prompt: str) -> str:
    """Call the Anthropic API via the SDK and return the response text."""
    import anthropic

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    block = message.content[0]
    if not isinstance(block, anthropic.types.TextBlock):
        return ""
    return block.text


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
            response text. Defaults to SDK-direct Anthropic call.
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
