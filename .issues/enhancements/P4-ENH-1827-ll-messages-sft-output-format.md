---
id: ENH-1827
title: Add --sft-format flag to ll-messages CLI
type: ENH
priority: P4
status: done
captured_at: '2026-05-31T22:00:59Z'
completed_at: '2026-06-02T23:41:29Z'
discovered_date: '2026-05-31'
discovered_by: capture-issue
parent: EPIC-1880
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
labels:
  - epic: EPIC-1880
  - sft
  - cli
---

# ENH-1827: Add --sft-format flag to ll-messages CLI

## Summary

Extend `ll-messages` with an `--sft-format` flag that emits conversation turns in standard SFT training formats (ChatML, Alpaca, ShareGPT) rather than the current `--examples-format` prompt-optimization output.

## Current Behavior

`ll-messages` supports `--examples-format`, which outputs `(input, expected)` pairs scoped to a specific skill's invocation pattern. There is no output format suitable for SLM fine-tuning workflows (ChatML, Alpaca, ShareGPT).

## Expected Behavior

`ll-messages` accepts `--sft-format {chatml,alpaca,sharegpt}`, emitting conversation turns in the specified SFT training format as JSON-lines. `--sft-format` and `--examples-format` are mutually exclusive. The flag composes with existing options (`--context-window`, `--since`, `--stdout`, `--output`).

## Motivation

`ll-messages` currently supports `--examples-format`, which outputs `(input, expected)` pairs scoped to a specific skill's invocation pattern — useful for apo-textgrad but not for SLM fine-tuning. An `--sft-format` flag would let the `sft-corpus` loop (FEAT-1826) use `ll-messages` as its ingest stage, or allow one-off corpus extraction without running the full loop.

## Implementation Steps

1. **Create `scripts/little_loops/sft_formatter.py`** — `SFTFormatter` class with three static methods, each accepting `list[tuple[str, str]]` (role, content) pairs:
   - `to_chatml(turns)` → `{"messages": [{"role": "...", "content": "..."}]}`
   - `to_alpaca(turns)` → `{"instruction": "...", "input": "", "output": "..."}` (maps first user turn to `instruction`, last assistant turn to `output`)
   - `to_sharegpt(turns)` → `{"conversations": [{"from": "human"|"gpt", "value": "..."}]}` (maps `"user"` role → `"human"`, `"assistant"` role → `"gpt"`)

2. **Add `extract_conversation_turns()` to `scripts/little_loops/user_messages.py`** — new function that extracts both user text and assistant text blocks (not just `ResponseMetadata`) from a JSONL file, returning `list[list[tuple[str, str]]]` (one list per session window). The existing `_extract_messages_with_context()` at line 679 reads all assistant records already; extend this pattern to also harvest `block["text"]` from `type == "text"` blocks in assistant `message.content`. This is needed because `UserMessage` only carries the user side of each turn — `ChatML` and `ShareGPT` require alternating `user`/`assistant` turns.

3. **Add `--sft-format` arg to `scripts/little_loops/cli/messages.py`** — use `add_mutually_exclusive_group()` (established pattern from `scripts/little_loops/cli/history.py`) to register both `--examples-format` and `--sft-format` in the same group so argparse auto-rejects both being passed together:
   ```python
   format_group = parser.add_mutually_exclusive_group()
   format_group.add_argument("--examples-format", action="store_true", ...)
   format_group.add_argument(
       "--sft-format",
       choices=["chatml", "alpaca", "sharegpt"],
       help="Output conversation turns in SFT training format (JSON-lines)",
   )
   ```
   This replaces the existing `--examples-format` standalone `add_argument` call at line 123.

4. **Add SFT output path in `main_messages()`** — insert a new early-return branch after the `--examples-format` block (after line 223), following the same `args.stdout` / `_save_combined()` pattern. Call `extract_conversation_turns()`, apply `--context-window` windowing, emit one `json.dumps(SFTFormatter.to_<format>(window))` per window.

5. **Add tests** across two files:
   - `scripts/tests/test_user_messages.py:1412` — add `TestSFTFormatter` class following `TestBuildExamples` pattern; cover each format method and windowing
   - `scripts/tests/test_cli.py` — add mutual-exclusion test following `test_examples_format_produces_example_records`; assert `SystemExit` with non-zero code when both flags are passed (see `scripts/tests/test_issue_history_cli.py:test_main_history_analyze_compare_and_since_mutually_exclusive` for the `pytest.raises(SystemExit)` pattern)

6. **Update `docs/reference/CLI.md:1565-1601`** — add `--sft-format` to the flag table and append usage examples matching the API / Interface section above.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Add `extract_conversation_turns` to `__all__`** in `scripts/little_loops/user_messages.py` — current `__all__` exports `CommandRecord`, `ExampleRecord`, `get_project_folder`, `extract_user_messages`, `extract_commands`, `build_examples`; the new function must be listed to remain on the declared public surface [Agent 2]
8. **Update `TestMessagesArgumentParsingWithCommands._parse_messages_args()`** (~line 1332 in `scripts/tests/test_user_messages.py`) — this fixture maintains a local duplicate of the real argparse parser; when `--examples-format` is moved into `add_mutually_exclusive_group()`, add `--sft-format` to the same group in this fixture [Agents 2 + 3]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The codebase convention for multi-format output is **module-level functions** (`format_<entity>_<format>` in e.g. `scripts/little_loops/issue_history/formatting.py`, `scripts/little_loops/doc_counts.py`), not a class. The issue says "class (or module-level functions)" — prefer module-level functions in `sft_formatter.py` to match existing conventions.
- **Mutual exclusion**: use `parser.add_mutually_exclusive_group()` from `scripts/little_loops/cli/history.py`; argparse auto-rejects both being passed, test with `pytest.raises(SystemExit)` from `scripts/tests/test_issue_history_cli.py:test_main_history_analyze_compare_and_since_mutually_exclusive`.
- **`--sft-format` output path**: reuse `_save_combined()` at `scripts/little_loops/cli/messages.py:250`; it accepts any list of objects with `to_dict()`, making it a drop-in for a new `SFTRecord` dataclass.
- **Assistant text gap**: `UserMessage` only captures the user side of each turn. A new `extract_conversation_turns()` in `scripts/little_loops/user_messages.py` must harvest `block["text"]` from `type == "text"` assistant content blocks — the scaffolding already exists in `_extract_messages_with_context()` at line 679, which reads all assistant records; extend it to also collect assistant text.

## API / Interface

```bash
# Emit all conversations in ChatML format
ll-messages --sft-format chatml --stdout

# Emit windowed (3-turn) conversations in ShareGPT format since last harvest
ll-messages --sft-format sharegpt --context-window 3 --since 2026-05-01 --stdout

# Write to file
ll-messages --sft-format alpaca --output data/sft/raw.jsonl
```

## Scope Boundaries

- **In scope**: `--sft-format` flag, `SFTFormatter` class, windowed JSON-lines output, mutual-exclusion with `--examples-format`
- **Out of scope**: model training pipelines, corpus deduplication or quality filtering (owned by FEAT-1826 `sft-corpus` loop), format inference from file extension, output schema validation beyond JSON serialization

## Impact

- **Priority**: P4 - Enables non-critical fine-tuning workflow; unblocks FEAT-1826 ingest stage but FEAT-1826 itself is low priority
- **Effort**: Small - Adds `SFTFormatter` class and one new CLI arg; reuses existing windowing and extract output path
- **Risk**: Low - Purely additive; no changes to existing `--examples-format` or other output paths
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/messages.py` — add `--sft-format {chatml,alpaca,sharegpt}` arg to the `argparse` block (around line 120 alongside `--examples-format`); add mutual-exclusion validation; add SFT output code path after the `--examples-format` early-return block (line 223)
- `scripts/little_loops/user_messages.py` — add `extract_conversation_turns()` function returning `list[tuple[str, str]]` (role, content) pairs, including assistant text blocks (not just metadata); this is needed because `UserMessage` captures only user-side content and ChatML/ShareGPT require alternating user/assistant turns

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/lib/cli.yaml` — `ll_messages` fragment description comment at line ~83 lists `--examples-format` as an example flag override; add `--sft-format` to keep the fragment discoverable for loop authors targeting SFT extraction [Agents 1 + 2]

### New Files
- `scripts/little_loops/sft_formatter.py` — `SFTFormatter` class with `to_chatml()`, `to_alpaca()`, `to_sharegpt()` static/class methods; each takes `list[tuple[str, str]]` (role, content) and returns a `dict` suitable for `json.dumps()`; add to `scripts/little_loops/__init__.py` exports if needed

### Dependent Files (Callers / Importers)
- `scripts/little_loops/cli/__init__.py` — entry-point docstring lists `ll-messages`; no code changes needed
- `scripts/pyproject.toml:54` — `ll-messages = "little_loops.cli:main_messages"` entry point; no changes needed

### Tests
- `scripts/tests/test_user_messages.py:1412` — `TestBuildExamples` class is the primary pattern to follow for SFT formatter tests; mirror its session/window construction for `SFTFormatter` unit tests
- `scripts/tests/test_cli_messages_save.py` — covers `_save_combined()` output helper; reference for `--stdout` / `--output` path tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli.py` — add mutual-exclusion test (`pytest.raises(SystemExit)` pattern from `test_issue_history_cli.py:test_main_history_analyze_compare_and_since_mutually_exclusive`); add `--sft-format --stdout` end-to-end test modeled on `test_examples_format_produces_example_records` at line 1905 in `TestMainMessagesAdditionalCoverage` [Agents 1 + 3]
- `scripts/tests/test_user_messages.py` (~line 1332, `TestMessagesArgumentParsingWithCommands._parse_messages_args`) — this method maintains a local duplicate of the real argparse parser; when `--examples-format` moves into `add_mutually_exclusive_group()`, add `--sft-format` to the same group in this fixture or new flag tests will diverge from real parser behavior [Agents 2 + 3]

### Documentation
- `docs/reference/CLI.md:1565-1601` — current `ll-messages` section; add `--sft-format` to the flag table and usage examples

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `### main_messages` section documents `main_messages()` flags; currently lists only 7 of the 11 flags; add `--sft-format` to avoid widening the existing documentation gap [Agent 2]

## Related

- FEAT-1826 — `sft-corpus` loop (primary consumer of this flag)
- `scripts/little_loops/` — `ll-messages` implementation lives here

## Labels

`enhancement`, `cli`, `sft`, `ll-messages`

## Session Log
- `/ll:manage-issue` - 2026-06-02T23:41:29 - `5f2bd088-984a-42ca-95bd-6003e7b6312c.jsonl`
- `/ll:ready-issue` - 2026-06-02T23:32:42 - `adaf9bf1-77d1-459c-b949-ba44567e0443.jsonl`
- `/ll:confidence-check` - 2026-06-02T23:45:00 - `6d2e5d05-1442-431e-a2c2-c3847d73a670.jsonl`
- `/ll:wire-issue` - 2026-06-02T23:23:21 - `16d2eea7-9cc0-4d21-9d84-d96036fdb70d.jsonl`
- `/ll:refine-issue` - 2026-06-02T23:17:02 - `d869663f-6cbd-441f-aa25-5bb3a2dafe09.jsonl`
- `/ll:format-issue` - 2026-06-02T23:12:32 - `6befaa25-7be4-48c5-9f39-8b253fd70493.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:34 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:capture-issue` - 2026-05-31T22:00:59Z - `109abe71-e47d-4222-b37d-c17fd7d98dee.jsonl`

---
## Resolution

Implemented `--sft-format {chatml,alpaca,sharegpt}` flag for `ll-messages`, mutually exclusive with `--examples-format`. Added:
- `scripts/little_loops/sft_formatter.py` — `to_chatml()`, `to_alpaca()`, `to_sharegpt()` functions
- `extract_conversation_turns()` + `_extract_turn_pairs()` in `user_messages.py` — extracts both sides of conversations with sliding context windows
- CLI wiring in `messages.py` with `add_mutually_exclusive_group()`, SFT output branch, `_SFTItem` wrapper
- 11 new tests across `TestSFTFormatter` and `TestMainMessagesAdditionalCoverage`
- Docs updated in `CLI.md`, `API.md`, and `loops/lib/cli.yaml`

## Status

`done`
