"""In-house, zero-dependency heuristic prompt compressor (FEAT-2675).

Three extractive passes over a live message list, plus a ``compress()`` entry
point that gates them on a window-relative trigger. No ML dependency: the
LLMLingua-gated benchmark comparator that decides whether the heuristic
underperforms lives in FEAT-2676 and is out of scope here.

The passes adapt the eviction/boundary logic proven in
``compaction/instant.py`` (FEAT-2598) — ``evict_sink_and_window`` (system-block
preservation) and ``is_valid_cutoff`` (user-turn boundary snapping) — but
operate on the same ``list[dict]`` (``role``/``content``) message rows rather
than importing them wholesale.

Token estimates use the project-wide ``len(text) // 4`` convention
(``session_store._estimate_tokens``, ``session_store.py``). No BPE tokenizer
exists anywhere in the codebase; ``instant.py`` inlines the same ``len // 4``.
It is redefined locally here to avoid importing the heavy ``session_store``
module into the FSM prompt-assembly hot path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

# Sentinel roles the passes key off. Anything not in these buckets is treated as
# an ordinary (kept) message.
_SYSTEM = "system"
_USER = "user"
_ASSISTANT = "assistant"
_TOOL = "tool"


def _estimate_tokens(text: str) -> int:
    """Rough token estimate using the project convention: 4 characters per token.

    Mirrors ``session_store._estimate_tokens`` (and the inline ``len // 4`` in
    ``compaction/instant.py``) rather than adding a BPE tokenizer.
    """
    return len(text) // 4


def _content_str(message: dict) -> str:
    """Best-effort string form of a message's content for token estimation."""
    content = message.get("content", "")
    return content if isinstance(content, str) else str(content)


def _total_tokens(messages: list[dict]) -> int:
    return sum(_estimate_tokens(_content_str(m)) for m in messages)


@dataclass
class CompressedResult:
    """Outcome of a ``compress()`` call.

    Attributes:
        messages: The (possibly) trimmed message list. Identical object contents
            to the input when ``triggered`` is False.
        original_tokens: ``len // 4`` token estimate of the input messages.
        compressed_tokens: ``len // 4`` token estimate of ``messages``.
        cache_control_candidates: Output-list indices of surviving stable system
            blocks that appeared more than once in the input. Flagged for the
            separate F1 ``cache_control`` child to consume later — no
            ``cache_control`` marking happens in this module.
        triggered: True when the effective trigger was met and the passes ran.
    """

    messages: list[dict]
    original_tokens: int
    compressed_tokens: int
    cache_control_candidates: list[int] = field(default_factory=list)
    triggered: bool = False

    @property
    def reduction_ratio(self) -> float:
        """``original_tokens / compressed_tokens`` (1.0 when nothing was removed)."""
        if self.compressed_tokens <= 0:
            return 1.0
        return self.original_tokens / self.compressed_tokens


def _user_turn_indices(messages: list[dict]) -> list[int]:
    """Per-message user-turn number.

    A new turn starts at each ``role == "user"`` message. Messages before the
    first user turn are turn 0. Returns a list parallel to ``messages``.
    """
    turns: list[int] = []
    current = 0
    for m in messages:
        if m.get("role") == _USER:
            current += 1
        turns.append(current)
    return turns


def drop_stale_tool_results(messages: list[dict], max_age_turns: int = 5) -> list[dict]:
    """Drop ``role == "tool"`` messages older than ``max_age_turns`` user turns.

    Age is measured in user-turn boundaries from the most recent user turn.
    ``system`` messages are preserved unconditionally; non-tool messages are
    never dropped. Returns the original list unchanged when nothing qualifies.
    """
    if max_age_turns < 0:
        return list(messages)

    turns = _user_turn_indices(messages)
    max_turn = max(turns, default=0)
    cutoff = max_turn - max_age_turns  # tool results at turn <= cutoff are stale

    kept: list[dict] = []
    for m, turn in zip(messages, turns, strict=True):
        if m.get("role") == _TOOL and turn <= cutoff:
            continue
        kept.append(m)
    return kept


def dedupe_stable_system_blocks(
    messages: list[dict],
) -> tuple[list[dict], list[int]]:
    """Dedupe exact-duplicate ``system`` blocks, keeping the first occurrence.

    Returns ``(deduped_messages, cache_control_candidates)`` where the second
    element lists the output-list indices of surviving system blocks whose
    content was repeated in the input (i.e. stable across turns — the signal the
    downstream F1 ``cache_control`` child keys off). No marking is performed
    here.
    """
    seen_counts: dict[str, int] = {}
    for m in messages:
        if m.get("role") == _SYSTEM:
            key = _content_str(m)
            seen_counts[key] = seen_counts.get(key, 0) + 1

    emitted: set[str] = set()
    deduped: list[dict] = []
    candidates: list[int] = []
    for m in messages:
        if m.get("role") == _SYSTEM:
            key = _content_str(m)
            if key in emitted:
                continue  # exact-duplicate stable block — drop
            emitted.add(key)
            if seen_counts.get(key, 0) > 1:
                candidates.append(len(deduped))
        deduped.append(m)
    return deduped, candidates


def tail_truncate_assistant_turns(messages: list[dict], max_n: int = 8) -> list[dict]:
    """Keep only the most recent ``max_n`` ``assistant`` messages.

    Older assistant messages are dropped; ``system``/``user``/``tool`` messages
    are untouched, preserving turn ordering. Returns the original list unchanged
    when there are at most ``max_n`` assistant messages.
    """
    if max_n < 0:
        return list(messages)

    assistant_positions = [i for i, m in enumerate(messages) if m.get("role") == _ASSISTANT]
    if len(assistant_positions) <= max_n:
        return list(messages)

    # Drop all but the most recent max_n assistant messages (max_n == 0 drops all).
    keep = set(assistant_positions[len(assistant_positions) - max_n :]) if max_n > 0 else set()
    drop = set(assistant_positions) - keep
    return [m for i, m in enumerate(messages) if i not in drop]


def _resolve_trigger(
    context_window: int | None,
    trigger_pct: float,
    trigger_tokens: int | None,
) -> int | None:
    """Effective token trigger: the lower of ``trigger_pct * context_window``
    (when the window is known) and ``trigger_tokens`` (when set).

    Returns ``None`` when neither applies — meaning "no gate" (compress
    unconditionally), which the trace-set measurement relies on.
    """
    candidates: list[int] = []
    if context_window:
        candidates.append(int(trigger_pct * context_window))
    if trigger_tokens is not None:
        candidates.append(int(trigger_tokens))
    if not candidates:
        return None
    return min(candidates)


def compress(
    messages: list[dict],
    context_window: int | None = None,
    trigger_pct: float = 0.4,
    trigger_tokens: int | None = None,
    max_tool_result_age_turns: int = 5,
    max_assistant_tail_turns: int = 8,
) -> CompressedResult:
    """Run the heuristic compressor over ``messages``.

    Resolves the effective trigger (``trigger_pct * context_window`` vs
    ``trigger_tokens``, lower absolute value winning). When the input's token
    estimate is below the trigger, returns the messages unchanged
    (``triggered=False``). When no trigger applies (both ``context_window`` and
    ``trigger_tokens`` unset) the passes always run.

    Pass order: drop stale tool results → dedupe stable system blocks →
    tail-truncate assistant turns.
    """
    original_tokens = _total_tokens(messages)
    trigger = _resolve_trigger(context_window, trigger_pct, trigger_tokens)

    if trigger is not None and original_tokens < trigger:
        return CompressedResult(
            messages=list(messages),
            original_tokens=original_tokens,
            compressed_tokens=original_tokens,
            cache_control_candidates=[],
            triggered=False,
        )

    working = drop_stale_tool_results(messages, max_age_turns=max_tool_result_age_turns)
    working, candidates = dedupe_stable_system_blocks(working)
    working = tail_truncate_assistant_turns(working, max_n=max_assistant_tail_turns)

    return CompressedResult(
        messages=working,
        original_tokens=original_tokens,
        compressed_tokens=_total_tokens(working),
        cache_control_candidates=candidates,
        triggered=True,
    )


def _parse_message_list(text: str) -> list[dict] | None:
    """Return ``text`` parsed as a JSON list of ``{role, content}`` dicts, else None.

    Used by the executor string adapter to detect the motivating case — a loop
    re-embedding a captured message-list JSON blob — without lossily mangling
    arbitrary prose prompts.
    """
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, list) or not parsed:
        return None
    if not all(isinstance(m, dict) and "role" in m for m in parsed):
        return None
    return parsed


def compress_action_text(
    text: str,
    *,
    model: str | None = None,
    context_window: int | None = None,
    trigger_pct: float = 0.4,
    trigger_tokens: int | None = None,
    max_tool_result_age_turns: int = 5,
    max_assistant_tail_turns: int = 8,
) -> str:
    """Compress a single interpolated FSM action string, byte-safely.

    Below the resolved trigger the text is returned byte-identical. Above it,
    the text is compressed only when it parses as a JSON message list (the
    captured-message-list case); otherwise it is returned unchanged so arbitrary
    prose is never mangled. When ``context_window`` is None it is resolved from
    ``model`` via ``context_window_for``.
    """
    from little_loops.context_window import context_window_for

    if context_window is None:
        context_window = context_window_for(model)

    trigger = _resolve_trigger(context_window, trigger_pct, trigger_tokens)
    if trigger is not None and _estimate_tokens(text) < trigger:
        return text

    messages = _parse_message_list(text)
    if messages is None:
        return text  # not a structured message list — pass through unchanged

    result = compress(
        messages,
        context_window=context_window,
        trigger_pct=trigger_pct,
        trigger_tokens=trigger_tokens,
        max_tool_result_age_turns=max_tool_result_age_turns,
        max_assistant_tail_turns=max_assistant_tail_turns,
    )
    if not result.triggered or result.messages == messages:
        return text  # nothing removed — preserve original formatting byte-for-byte
    return json.dumps(result.messages)
