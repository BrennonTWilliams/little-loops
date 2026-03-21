---
discovered_date: 2026-03-20
discovered_by: capture-issue
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
  "output": "<assistant response text or accepted tool output>",
  "skill": "capture-issue",
  "session_id": "...",
  "timestamp": "..."
}
```

## Motivation

FEAT-849 (co-evolutionary examples mining meta-loop) needs a reliable way to harvest labeled `(context → accepted output)` pairs from historical session logs keyed by skill. Without `--skill` filtering, mining requires scanning every session and doing pattern matching outside the tool. Without `--examples-format`, consumers must reconstruct the pairing logic independently. These flags make `ll-messages` the canonical extraction layer rather than pushing parsing logic into each consumer.

## Proposed Solution

1. Add `--skill` argument to `main_messages()` in `scripts/little_loops/cli/messages.py`. After extracting messages, filter to sessions where the skill appears in any `UserMessage.content` (regex `r'/ll:?{skill}|/{skill}'`) or in `response_metadata.tools_used` (tool name `Skill`).
2. Add `--examples-format` flag. When set, pair each matching `UserMessage` with its `response_metadata` (requires `--include-response-context`); auto-enable `--include-response-context` when `--examples-format` is passed. Emit `ExampleRecord` dicts instead of raw records.
3. Add `ExampleRecord` dataclass to `user_messages.py` mirroring the output schema above.
4. Wire up context window: include the N preceding user messages as `input` (default N=3, configurable via `--context-window`).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/messages.py` — add `--skill`, `--examples-format`, `--context-window` args; filter and reshape output
- `scripts/little_loops/user_messages.py` — add `ExampleRecord` dataclass; add `build_examples()` helper

### Dependent Files (Callers/Importers)
- `scripts/tests/test_cli.py` — `TestMainMessages` class (~line 594)
- `scripts/tests/test_user_messages.py` — `TestMainMessagesArgParsing` class (~line 394)

### Similar Patterns
- `--commands-only` / `--skip-cli` toggle pattern in `main_messages()` — same argparse flag approach
- `--include-response-context` auto-activation precedent: can set a flag as a side-effect of another

### Tests
- `scripts/tests/test_cli.py` — add cases: skill filter matches/non-matches, examples-format output shape
- `scripts/tests/test_user_messages.py` — unit test `build_examples()` with fixture JSONL

### Documentation
- `docs/reference/API.md` — add `ExampleRecord` to public API surface
- `scripts/little_loops/cli/messages.py` epilog — add usage examples

### Configuration
No config key needed; all behavior is flag-driven.

## Implementation Steps
1. Add `ExampleRecord` dataclass and `build_examples()` to `user_messages.py`
2. Add `--skill`, `--examples-format`, `--context-window` args in `main_messages()`
3. Implement session-level skill detection (content regex + response_metadata tool check)
4. Wire `--examples-format` → `build_examples()` → emit `ExampleRecord` dicts
5. Auto-enable `--include-response-context` when `--examples-format` is set
6. Update tests and epilog

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
    output: str         # accepted assistant response
    session_id: str
    timestamp: datetime
    context_window: int

    def to_dict(self) -> dict[str, object]: ...
```

## Blocks

- FEAT-849

## Labels
`feat`, `ll-messages`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0633f118-65ef-4b3d-9507-feb81b97f8cd.jsonl`

---
## Status
**Open** | Created: 2026-03-20 | Priority: P3
