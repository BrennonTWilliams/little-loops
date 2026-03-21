---
discovered_date: 2026-03-20
discovered_by: capture-issue
confidence_score: 90
outcome_confidence: 78
---

# FEAT-850: Add `--skill` filter and `--examples-format` flags to `ll-messages`

## Summary

Extend `ll-messages` with two new output-shaping flags: `--skill SKILL_NAME` filters extracted records to only those sessions where a given skill was invoked (e.g. `/ll:capture-issue`), and `--examples-format` reshapes the output into `(invocation_context, accepted_output)` pairs suitable for use as APO/prompt-optimization training examples.

## Current Behavior

`ll-messages` extracts all user messages and CLI commands in chronological order with no way to narrow the corpus to a specific skill's invocations. Downstream consumers (e.g. `ll-workflows`, apo-textgrad) must post-filter the JSONL themselves, and there is no structured output format for training-example extraction.

## Expected Behavior

```bash
# Extract only sessions where /ll:capture-issue was invoked
ll-messages --skill capture-issue

# Extract invocation/output pairs for prompt optimization
ll-messages --skill capture-issue --examples-format

# Composable with existing flags
ll-messages --skill refine-issue --since 2026-01-01 --examples-format --stdout
```

`--skill SKILL_NAME` filters the combined message+command stream to records from sessions where the skill appears — matching `/ll:SKILL_NAME` in user message content or a `Skill` tool_use block in the response context.

`--examples-format` changes the output schema from raw `UserMessage`/`CommandRecord` dicts to structured pairs:
```json
{
  "input": "<N preceding user messages as context>",
  "output": "{\"tools_used\": [...], \"files_modified\": [...], \"completion_status\": \"success\"}",
  "skill": "capture-issue",
  "session_id": "...",
  "timestamp": "..."
}
```

Note: `output` is a JSON-serialized `ResponseMetadata` summary (tools used, files modified, completion status). Free-text assistant response capture is deferred to a follow-on issue.

## Motivation

FEAT-849 (co-evolutionary examples mining meta-loop) needs a reliable way to harvest labeled `(context → accepted output)` pairs from historical session logs keyed by skill. Without `--skill` filtering, mining requires scanning every session and doing pattern matching outside the tool. Without `--examples-format`, consumers must reconstruct the pairing logic independently. These flags make `ll-messages` the canonical extraction layer rather than pushing parsing logic into each consumer.

## Proposed Solution

1. Add `--skill` argument to `main_messages()` in `scripts/little_loops/cli/messages.py`. After extracting messages, filter to sessions where the skill appears in any `UserMessage.content` (regex `r'/ll:?{skill}|/{skill}'`) or in `response_metadata.tools_used` (tool name `Skill`).
2. Add `--examples-format` flag. When set, pair each matching `UserMessage` with its `response_metadata` (requires `--include-response-context`); auto-enable `--include-response-context` when `--examples-format` is passed. Emit `ExampleRecord` dicts instead of raw records.
3. Add `ExampleRecord` dataclass to `user_messages.py` mirroring the output schema above.
4. Wire up context window: include the N preceding user messages as `input` (default N=3, configurable via `--context-window`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**CRITICAL CORRECTION — Skill detection mechanism:**

The `response_metadata.tools_used` check in step 1 is incorrect. Confirmed by analyzing actual session JSONL files: **there are no `"name": "Skill"` tool_use blocks anywhere in assistant records.** Skills are invoked by the host injecting two consecutive user-side records, not via a `tool_use` block.

The only reliable machine-readable signal for a skill invocation is in the **user-side trigger record** (Record A below), whose string content contains:
```
<command-name>/ll:SKILL_NAME</command-name>
<command-message>ll:SKILL_NAME</command-message>
```

**Corrected regex**: `rf'<command-name>/ll:{re.escape(skill)}</command-name>'` against `UserMessage.content`. The existing `r'/ll:?{skill}|/{skill}'` pattern would also match, but the XML-tag form is more specific and reliable.

**Skill invocation record anatomy** — a skill invocation produces exactly two consecutive `type: "user"` records in the JSONL:

- **Record A** (trigger): `isMeta: false`, string `content` = `"<command-message>ll:SKILL_NAME</command-message>\n<command-name>/ll:SKILL_NAME</command-name>\n<command-args>...</command-args>"` → parsed into `UserMessage` by `_parse_user_record()` at `user_messages.py:594`
- **Record B** (body): `isMeta: true`, list `content` with one text block containing the full rendered skill markdown → also parsed into `UserMessage` (the `isMeta` field is NOT mapped to any `UserMessage` field; it exists only in the raw JSONL)

Implication: both records become `UserMessage` objects. The `--skill` filter should target Record A (string content with XML tags). The isMeta body records would also appear in the session and shouldn't be mistakenly used as "user input" in context windows.

**Session-level filter implementation** — The filter must be applied post-extraction at `messages.py:164` (after the `extract_user_messages()` call but before merge/sort). Pattern:
```python
if args.skill:
    import re
    skill_pattern = re.compile(rf'<command-name>/ll:{re.escape(args.skill)}</command-name>')
    matching_sessions = {msg.session_id for msg in messages if skill_pattern.search(msg.content)}
    messages = [msg for msg in messages if msg.session_id in matching_sessions]
```

**`ExampleRecord.output` field — resolved:** The current `ResponseMetadata` (assembled by `_aggregate_response_metadata()` at `user_messages.py:199-263`) captures only `tools_used`, `files_read`, `files_modified`, `completion_status`, `error_message`. It does **not** capture assistant response text (`text` content blocks are ignored). **Decision: define `output` as a JSON-serialized summary of `ResponseMetadata`** — tools used and files modified — rather than free text. Free-text capture is deferred to a follow-on issue. This keeps scope tight and avoids blocking on a `_aggregate_response_metadata()` rewrite.

Example serialized output value:
```json
{"tools_used": [{"tool": "Read", "count": 3}, {"tool": "Edit", "count": 1}], "files_modified": ["scripts/foo.py"], "completion_status": "success"}
```

**Auto-enable `--include-response-context`** — at `messages.py:152`, the flag is passed directly. Auto-enable by replacing with: `include_response_context=args.include_response_context or args.examples_format` (line 152). No other changes needed at the call site.

**`--context-window` and preceding messages** — building the `input` field from N preceding messages requires walking `messages` (sorted by timestamp) in session order. After session-level filtering, group by `session_id`, sort each group ascending by timestamp, then for each skill trigger record, slice the N records before it as context. The merged `combined` list (sorted descending at line 172) is not convenient for this; operate on the per-session groups before merging.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/messages.py` — add `--skill`, `--examples-format`, `--context-window` args; filter and reshape output
- `scripts/little_loops/user_messages.py` — add `ExampleRecord` dataclass; add `build_examples()` helper

### Dependent Files (Callers/Importers)
- `scripts/tests/test_cli.py` — `TestMainMessagesIntegration` class (line 572); `TestMainMessagesAdditionalCoverage` class (line 1644) — follow `test_include_response_context_flag` pattern at line 1712
- `scripts/tests/test_user_messages.py` — `TestMessagesArgumentParsing` class (line 393); `TestMessagesArgumentParsingWithCommands` class (line 1312) — extend `_parse_messages_args()` helper at line 1312 to add the 3 new flags; add `test_skill_default`, `test_skill_flag`, `test_examples_format_default`, `test_examples_format_flag`, `test_context_window_default`, `test_context_window_flag` methods following the existing `test_skip_cli_default`/`test_skip_cli_flag` pattern
- `scripts/tests/test_cli_messages_save.py` — `TestSaveCombined` class (line 12); **no changes needed** — `_save_combined` (messages.py:193-214) accepts any `list` with `.to_dict()` (duck-typed); existing tests use `MagicMock(to_dict=lambda: {...})`, so `ExampleRecord` passes through unchanged

### Similar Patterns
- `--commands-only` / `--skip-cli` toggle pattern in `main_messages()` — same argparse flag approach
- `--include-response-context` auto-activation precedent: can set a flag as a side-effect of another
- `workflow_sequence_analyzer.py:384-392` — `_group_by_session()` helper: groups `list[dict]` by `session_id` key; reuse this pattern for context-window windowing (operate on per-session groups before the final descending-sort merge at messages.py:168-172)

### Tests
- `scripts/tests/test_cli.py` — add cases: skill filter matches/non-matches, examples-format output shape
- `scripts/tests/test_user_messages.py` — unit test `build_examples()` with fixture JSONL

### Documentation
- `docs/reference/API.md` — add `ExampleRecord` to public API surface
- `docs/reference/CLI.md` — add `--skill`, `--examples-format`, `--context-window` to `ll-messages` reference
- `scripts/little_loops/cli/messages.py` epilog (lines 33-43) — add usage examples for new flags

### Configuration
No config key needed; all behavior is flag-driven.

## Implementation Steps
1. Add `ExampleRecord` dataclass and `build_examples()` to `user_messages.py` — model after `UserMessage` at line 38 (`to_dict()` returning `dict[str, object]`, datetime stored as `datetime`, serialized via `.isoformat()`)
2. Add `--skill` (str, optional), `--examples-format` (store_true), `--context-window` (int, default 3) args to the `argparse.ArgumentParser` block at `messages.py:84-104` — follow `action="store_true"` pattern for booleans, `type=str` for `--skill`
3. Implement session-level skill detection at `messages.py:164` (post-extraction, before merge): build `matching_sessions` set via `<command-name>/ll:{skill}</command-name>` regex on `UserMessage.content`, filter `messages` list — **do NOT use `response_metadata.tools_used` (no Skill tool entries exist there)**
4. Auto-enable `--include-response-context` when `--examples-format` is set: change `messages.py:152` from `args.include_response_context` to `args.include_response_context or getattr(args, 'examples_format', False)`
5. Define `ExampleRecord.output` as `json.dumps(response_metadata.to_dict())` (serialized `ResponseMetadata` — tools used, files modified, completion status); if `response_metadata` is None, emit `"{}"`
6. Wire `--examples-format` → `build_examples()` → emit `ExampleRecord` dicts instead of raw `UserMessage`/`CommandRecord` — slot in at `messages.py:169-176` (after merge, before limit)
7. Update test classes: `TestMessagesArgumentParsingWithCommands` in `test_user_messages.py:1312`; add integration tests in `test_cli.py:1644` following `test_include_response_context_flag` at line 1712
8. Update epilog at `messages.py:33-43` and `docs/reference/CLI.md`

## Impact
- **Priority**: P3 - Useful for APO training pipeline but not blocking
- **Effort**: Small - ~150 LOC; self-contained to `cli/messages.py` and `user_messages.py`
- **Risk**: Low - additive flags; no change to existing output paths
- **Breaking Change**: No

## Use Case

A prompt-optimization loop running apo-textgrad on the `capture-issue` skill needs 50 labeled examples. Today: manually grep session logs, extract pairs by hand. With this feature:

```bash
ll-messages --skill capture-issue --examples-format --since 2026-01-01 -o examples.jsonl
# → 50 structured (input, output) pairs ready for apo-textgrad
```

## API/Interface
```python
@dataclass
class ExampleRecord:
    skill: str
    input: str          # concatenated context messages
    output: str         # JSON-serialized ResponseMetadata (tools_used, files_modified, completion_status); free-text deferred
    session_id: str
    timestamp: datetime
    context_window: int

    def to_dict(self) -> dict[str, object]: ...
```

## Blocks

- FEAT-849

## Resolution

Implemented all three flags in `scripts/little_loops/cli/messages.py` and `scripts/little_loops/user_messages.py`:

- `--skill SKILL_NAME` — session-level filter using `<command-name>/ll:{skill}</command-name>` regex on `UserMessage.content` (as specified in codebase research)
- `--examples-format` — auto-enables `--include-response-context`, calls `build_examples()`, outputs `ExampleRecord` dicts; requires `--skill`
- `--context-window N` (default 3) — preceding message count for `input` context

Added `ExampleRecord` dataclass and `build_examples()` to `user_messages.py`. Updated `__all__`, CLI.md, and API.md.

Tests: 15 new tests across `TestBuildExamples`, `TestMessagesArgumentParsingWithCommands`, and `TestMainMessagesAdditionalCoverage`. All 3794 tests pass.

## Labels
`feat`, `ll-messages`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-03-21T02:35:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/081843aa-211e-4511-9ed7-f459a1863fa3.jsonl`
- `/ll:refine-issue` - 2026-03-21T02:33:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/77fad3d4-4cd4-49d2-8703-5d4df8de3550.jsonl`
- `/ll:refine-issue` - 2026-03-21T02:16:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2ef00304-0425-4493-86d1-986e0f3bbb29.jsonl`
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0633f118-65ef-4b3d-9507-feb81b97f8cd.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/514a367b-5049-4476-a069-2e6e1f01d027.jsonl`

---
## Status
**Completed** | Created: 2026-03-20 | Completed: 2026-03-20 | Priority: P3
