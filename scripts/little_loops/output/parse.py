"""Stop-sequence + prefill JSON output helpers (FEAT-2470, EPIC-2456 pass-2 #7).

Two recipes for extracting structured data from LLM output while keeping the
model's *output* token budget small:

- :func:`extract_between_tags` pairs with a **stop sequence**. The caller wraps
  the wanted content in ``<tag>…</tag>`` and sets the closing tag as the model's
  stop sequence, so generation halts the instant the payload is complete — no
  trailing prose to pay for. This helper recovers the content between the tags
  (tolerating a missing closing tag when the stop sequence ate it).

- :func:`parse_prefilled_json` pairs with a **prefill**. The caller seeds the
  assistant turn with ``{`` so the model must emit a bare JSON object and can't
  preface it with explanation. This helper finds the last ``{`` (the ``rfind``
  recipe) and parses to the matching close, tolerating a leading fragment or a
  reintroduced ``{``.

Both return a ``(value, error)`` tuple — the same convention as
:func:`little_loops.output_parsing.extract_tagged_json` (established by
BUG-2383): ``(value, None)`` on success, ``(None, error_msg)`` on failure.
Neither swallows: callers must surface ``error`` when ``value is None``.
"""

from __future__ import annotations

import json
from typing import Any


def extract_between_tags(
    start_tag: str, end_tag: str, raw: str
) -> tuple[str | None, str | None]:
    """Extract the text between ``start_tag`` and ``end_tag`` in ``raw``.

    Designed for the stop-sequence recipe: ``end_tag`` is typically set as the
    model's stop sequence, so it may be absent from ``raw`` (generation halted
    before emitting it). When ``end_tag`` is missing, everything after
    ``start_tag`` is returned. The first occurrence of each tag is used.

    Args:
        start_tag: Opening delimiter, e.g. ``"<json>"``.
        end_tag: Closing delimiter, e.g. ``"</json>"``.
        raw: Full model output to search.

    Returns:
        ``(content, None)`` with surrounding whitespace stripped on success, or
        ``(None, error_msg)`` when ``start_tag`` is not found.
    """
    start = raw.find(start_tag)
    if start == -1:
        return None, f"start tag {start_tag!r} not found in output"
    content_start = start + len(start_tag)

    end = raw.find(end_tag, content_start)
    if end == -1:
        # Stop sequence consumed the closing tag — take the remainder.
        return raw[content_start:].strip(), None
    return raw[content_start:end].strip(), None


def parse_prefilled_json(raw: str) -> tuple[Any | None, str | None]:
    """Parse a JSON object from prefilled model output.

    Handles the prefill recipe where the assistant turn was seeded with ``{``:
    the model emits a bare object, but ``raw`` may still carry a leading
    fragment (from the prefill echo) or trailing prose. Strategy:

    1. Try to parse ``raw`` verbatim (fast path — clean bare JSON).
    2. Otherwise locate the object with the ``rfind('{')`` recipe and parse from
       the last ``{`` to its matching ``}`` via a bracket-depth scan.

    Args:
        raw: Model output expected to contain a single JSON object.

    Returns:
        ``(obj, None)`` on success, or ``(None, error_msg)`` when no balanced
        object can be recovered.
    """
    stripped = raw.strip()
    if not stripped:
        return None, "empty output — no JSON object to parse"

    # Fast path: already a clean object/value.
    try:
        return json.loads(stripped), None
    except (json.JSONDecodeError, ValueError):
        pass

    # Recipe: scan back to the last '{' and forward to its matching '}'.
    open_idx = stripped.rfind("{")
    if open_idx == -1:
        return None, "no '{' found in output"

    depth = 0
    in_string = False
    escaped = False
    for i in range(open_idx, len(stripped)):
        ch = stripped[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[open_idx : i + 1]
                try:
                    return json.loads(candidate), None
                except (json.JSONDecodeError, ValueError) as exc:
                    tail = candidate[-200:] if len(candidate) > 200 else candidate
                    return None, f"malformed JSON object: {exc} — text: {tail!r}"

    return None, "unbalanced '{' — no matching '}' found in output"
