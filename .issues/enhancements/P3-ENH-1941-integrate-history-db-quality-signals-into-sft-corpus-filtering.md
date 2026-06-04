---
id: ENH-1941
title: Integrate history.db session-quality signals into sft-corpus filtering
type: ENH
priority: P3
status: open
captured_at: '2026-06-04T15:57:41Z'
discovered_date: '2026-06-04'
discovered_by: capture-issue
parent: EPIC-1880
relates_to: [EPIC-1707, ENH-1710]
labels:
  - enhancement
  - sft
  - history-db
  - corpus-quality
  - captured
---

# ENH-1941: Integrate history.db session-quality signals into sft-corpus filtering

## Summary

Join `history.db` session metadata (EPIC-1707) against the `sft-corpus` pipeline at filter time via session ID, so the filter state can gate on structured quality signals — issue outcomes, user corrections, tool invocation counts, and file modifications — instead of only token length and PII regex matches.

## Context

Identified during EPIC-1880 status review. The `sft-corpus` pipeline currently drops all structured session metadata at extraction time: `extract_conversation_turns()` returns bare `list[tuple[str, str]]` (role, content) pairs. Meanwhile, `history.db` already captures per-session structured data across six event tables (`user_corrections`, `issue_events`, `tool_events`, `file_events`, `loop_events`, `message_events`) plus an FTS5 index — but none of it flows into corpus quality decisions.

ENH-1710 (session-ID → JSONL path mapping) provides the join key between the two data sources. The read API (`history_reader.py`) and `ll-history-context` CLI (ENH-1846) already exist and follow a graceful-degradation pattern when `history.db` is missing or empty — the pipeline can adopt the same pattern.

## Motivation

The difference between "all conversations" and "conversations that closed issues, used tools, and had no user corrections" is the difference between a corpus that trains a generic chatbot and one that trains a useful coding assistant. The data to make this distinction already exists — it's just not wired into the pipeline.

Without this integration, the corpus includes:
- Sessions where the assistant went in circles and the user gave up
- Sessions that were pure research/planning with no code changes
- Sessions where the user repeatedly corrected the assistant
- Sessions with no measurable outcome

These are low-quality training examples that dilute the signal in the final corpus.

## Current Behavior

The `sft-corpus` filter state can only gate on:
- Token length (`min_tokens`, `max_tokens`) — a word-count approximation
- PII presence (`pii_action: flag | redact | discard`) — regex-based email/phone/SSN matching via `little_loops.pii`

All other session metadata is discarded at extraction time.

## Expected Behavior

The filter state gains optional quality predicates backed by `history.db` lookups:

```yaml
context:
  # Existing
  min_tokens: 50
  max_tokens: 4096
  pii_action: redact
  # New (all optional; omit to skip the check)
  require_issue_outcome: true       # only sessions that closed an issue
  exclude_user_corrections: true    # skip sessions where user said "wrong"
  min_tool_invocations: 3           # require at least N tool calls
  require_file_modifications: true  # only sessions that actually changed code
```

When `history.db` is missing, empty, or lacks the relevant tables, these predicates degrade to no-ops (pass-through) — following the EPIC-1707 graceful-degradation pattern established in `history_reader.py`.

## Implementation Steps

1. **Add a `lookup_session_metadata()` helper** — new function (or inline shell) that takes a session ID and queries `history.db` via `ll-history-context` or direct SQLite, returning a JSON metadata dict: `{"has_corrections": bool, "issue_outcome": str|null, "tool_count": int, "files_modified": int, "loop_outcome": str|null}`. Degrades to empty dict when DB is absent.

2. **Add an `enrich` state before `filter`** in `sft-corpus.yaml` — batch-joins metadata from `history.db` onto each example in the staged `raw.jsonl` by extracting the session ID from the example's source path and calling `lookup_session_metadata()`. Writes enriched examples to a new staged file.

3. **Extend the `filter` state** — add shell predicates for each new context key:
   - `require_issue_outcome`: drop examples where `metadata.issue_outcome != "done"`
   - `exclude_user_corrections`: drop examples where `metadata.has_corrections == true`
   - `min_tool_invocations`: drop examples where `metadata.tool_count < context.min_tool_invocations`
   - `require_file_modifications`: drop examples where `metadata.files_modified == 0`

4. **Add filter rejection tracking** — extend the filter state to emit a rejection-reason annotation per dropped example (e.g., `"rejected_by": "require_issue_outcome"`) so the analytics report (future issue) can break down rejection rates by reason.

5. **Update `sft-corpus.yaml` context block** — add the four new optional keys with defaults that mean "skip this check" (`require_issue_outcome: false`, `exclude_user_corrections: false`, `min_tool_invocations: 0`, `require_file_modifications: false`).

6. **Add tests** in `scripts/tests/test_loops_sft_corpus.py` (created by FEAT-1826):
   - Test graceful degradation when `history.db` is missing
   - Test that each predicate drops the correct examples
   - Test that predicate=false means pass-through

## API / Interface

No public API changes. The integration is internal to the `sft-corpus` loop's `enrich` and `filter` states. The `history.db` read path uses the existing `history_reader.py` API or `ll-history-context` CLI — no new read API surface.

## Use Case

A practitioner wants to fine-tune an SLM that's good at implementing code changes. They run:

```bash
ll-loop run sft-corpus
```

With context configured as:
```yaml
require_issue_outcome: true
exclude_user_corrections: true
require_file_modifications: true
min_tool_invocations: 5
```

The resulting corpus contains only conversations where: an issue was closed, the user never corrected the assistant, files were actually modified, and at least 5 tool calls were made. This corpus trains a model that completes tasks, not one that chats about them.

## Scope Boundaries

- **In scope**: New `enrich` state in `sft-corpus.yaml`; four new optional filter predicates backed by `history.db` lookups; graceful degradation when DB is absent; filter rejection-reason annotations
- **Out of scope**: Changes to `history.db` schema or write paths (owned by EPIC-1707); changes to `extract_conversation_turns()` return type; new `ll-history-context` features; analytics/reporting on rejection rates (future issue); making `history.db` a required dependency

## Impact

- **Priority**: P3 — Quality lever for an already-P3 epic; not blocking
- **Effort**: Medium — New `enrich` state + extended `filter` predicates + tests; all dependencies (`history_reader.py`, `ll-history-context`, graceful-degradation pattern) already exist
- **Risk**: Low — Additive to `sft-corpus.yaml` only; all new predicates are opt-in and default to pass-through; degrades gracefully when DB is absent
- **Breaking Change**: No — FEAT-1826 is not yet implemented, so there's no existing behavior to break
- **Depends on**: ENH-1710 (session-ID → JSONL path mapping) for the join key; FEAT-1826 (sft-corpus loop) for the file to modify

## Related

- EPIC-1880 — parent epic (SLM fine-tuning from session logs)
- EPIC-1707 — history.db as agent context layer (provides the read API and degradation pattern)
- ENH-1710 — session-ID to JSONL path mapping (provides the join key)
- FEAT-1826 — sft-corpus FSM loop (the file this issue modifies)
- ENH-1846 — ll-history-context CLI (one possible lookup path)
- ENH-1904 — user_corrections mining from message_events (feeds the `exclude_user_corrections` predicate)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Producer→consumer flow for history.db |
| reference | docs/reference/API.md | history_reader.py read API surface |

## Labels

`enhancement`, `sft`, `history-db`, `corpus-quality`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-06-04T15:57:41Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`

---

**Open** | Created: 2026-06-04 | Priority: P3
