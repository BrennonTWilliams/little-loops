---
discovered_date: 2026-04-16
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-1118: ll-loop run --verbose truncates LLM responses

## Summary

When `ll-loop run ... --verbose` is used, prompts (inputs to the LLM) display in full, but the model's responses appear heavily truncated to a single row ending in `...`. Two independent truncations on the prompt-action path compound: assistant text is delivered as one giant "line" with no newlines, and the verbose `action_output` handler hard-clips every line to terminal width.

## Current Behavior

Running a prompt-state loop with `--verbose` on a loop whose state produces a long multi-paragraph reply renders the entire response as a single truncated row ending in `...`. Prompts display correctly because they are authored with real newlines; responses do not because they arrive as one logical "line" from the stream-json assistant events.

## Steps to Reproduce

1. Pick (or author) a loop whose first state is a Claude prompt expected to produce a long multi-paragraph reply.
2. Run `ll-loop run <fsm> --verbose`.
3. Observe: the assistant response renders as a single row ending in `...` instead of a multi-paragraph block.

## Expected Behavior

With `--verbose`, the full LLM response should be displayed with paragraph breaks preserved. The persisted `action_output` event stream should also contain one entry per real line (not one giant entry), so `ll-loop history` and `ll-loop show` render captured output with preserved structure.

## Motivation

`--verbose` is an inspection/debugging flag. Users invoking it explicitly want to see full content. Silent truncation of LLM responses defeats the purpose and forces users to dig into raw event logs to recover content the UI failed to show.

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current source:_

- **Both file:line anchors confirmed** against current `main` — `subprocess_utils.py:205` is `"".join(text_parts)`, `_helpers.py:419-424` matches the quoted clip, `max_line = tw - 8 - len(indent)` at `_helpers.py:325`.
- **Embedded newlines inside a single text block also matter**: a Claude assistant event can ship a multi-paragraph response in one text block whose `"text"` value already contains `\n`. `subprocess_utils.py:187` only rstrips the trailing `\n` of the raw JSON wire line — embedded newlines inside the extracted text survive into `line`. Fix A's `text.splitlines()` handles both block boundaries and intra-block newlines in one pass, so the join separator ("" vs "\n\n") is less load-bearing than the split-and-dispatch-per-line loop.
- **`stdout_lines` reconstruction is preserved by Fix A**: `subprocess_utils.py:243` joins with `"\n".join(stdout_lines)` to build `CompletedProcess.stdout`. Appending each sub-line individually (per Fix A sketch) reconstructs the full text with `\n` separators — the evaluator path (`evaluators.py` reads `result.output`) and the 2000-char preview at `executor.py:609` both continue to see the full response content.
- **`ll-loop history --verbose` has a related but separate rendering issue**: `info.py:249-252` does NOT clip — it prints the full `event["line"]` via `colorize`. Before Fix A, that means history-verbose prints one massive unwrapped row (terminal must wrap). After Fix A, it will render N nicely-separated rows — a bonus improvement, not regression.
- **`issue_manager.py` is a second consumer** of `run_claude_command`'s `stream_callback`. Its callback at `issue_manager.py:133-138` prints per call. Fix A changes call frequency (1 → N per assistant event) but visual output is unchanged (N `print(line)` vs 1 `print(multi-line-text)`). No behavioral regression for `ll-auto` / `ll-sprint`.

Two compounding defects on the prompt-action path:

1. **`scripts/little_loops/subprocess_utils.py:198-207`** — When the Claude CLI subprocess emits a `stream-json` event of `type: "assistant"`, text blocks are concatenated with an empty string:
   ```python
   text_parts = [block["text"] for block in msg.get("content", []) if block.get("type") == "text"]
   line = "".join(text_parts)
   ```
   `stream_callback(line, is_stderr)` is then called exactly once with this single megastring. A multi-paragraph response that would span dozens of terminal rows is delivered to downstream consumers as one logical "line."

2. **`scripts/little_loops/cli/loop/_helpers.py:419-424`** — The verbose `action_output` handler hard-clips every "line" to terminal width:
   ```python
   elif event_type == "action_output":
       if not quiet and verbose:
           line = event.get("line", "")
           if line.strip():
               display = line[:max_line] + "..." if len(line) > max_line else line
               print(f"{indent}       {display}", flush=True)
   ```
   `max_line = terminal_width() - 8 - len(indent)` (line 325). Because the entire assistant response is a single "line" from defect 1, `line[:max_line] + "..."` lops off everything past ~terminal-width characters.

Why prompts look fine: `action_start` (lines 395–414) receives `action` already split into real lines and iterates `lines[:show_count]`. Per-line width truncation still applies, but authored newlines keep each printed row short enough to survive.

The 2000-char preview at `executor.py:609` is a red herring in verbose mode — `_helpers.py:448` only displays that preview when not verbose.

## Proposed Solution

Two small, targeted changes. Both are needed: Fix A alone leaves lines terminal-width-clipped in verbose. Fix B alone leaves a single mega-line in the persisted event log that tools like `ll-loop history`/`ll-loop show` consume.

### Fix A — preserve structure at the source (primary)

**File:** `scripts/little_loops/subprocess_utils.py:198-207`

Join text blocks with `"\n\n"` so paragraph boundaries survive, split the joined content into real lines, and invoke `stream_callback` once per line. Restructure the assistant branch with its own append+callback loop, then `continue` past the generic tail at lines 218-219.

Sketch:
```python
elif etype == "assistant":
    msg = event.get("message", {})
    text_parts = [block["text"] for block in msg.get("content", []) if block.get("type") == "text"]
    text = "\n\n".join(text_parts)
    if not text:
        continue
    for sub_line in text.splitlines() or [""]:
        stdout_lines.append(sub_line)
        if stream_callback:
            stream_callback(sub_line, is_stderr)
    continue
```

### Fix B — stop hard-clipping live output in verbose mode

**File:** `scripts/little_loops/cli/loop/_helpers.py:419-424`

Drop the `line[:max_line] + "..."` clip for `action_output` in verbose mode and let the terminal wrap. Keep the clip for `action_start` prompt echoes (line 409) and the action-summary echo (line 416) — those are intentional previews.

Sketch:
```python
elif event_type == "action_output":
    if not quiet and verbose:
        line = event.get("line", "")
        if line.strip():
            print(f"{indent}       {line}", flush=True)
```

## API/Interface

No public API changes. Event shape for `action_output` changes: a multi-line assistant response now produces N events (one per line) instead of one event with one giant `line` field. Downstream consumers (`ll-loop history`, `ll-loop show`) already iterate per-event and will render correctly.

## Implementation Steps

1. Restructure the `etype == "assistant"` branch in `subprocess_utils.py:198-207` to split on newlines and dispatch `stream_callback` per line; add `continue` to skip the generic tail.
2. Remove the width-clip in the `action_output` verbose branch in `_helpers.py:419-424`; rely on terminal auto-wrap.
3. Verify `_stream_cb → on_output_line` passthrough in `fsm/runners.py:91-93` needs no change (it's transparent).

## Testable

Yes.

## Verification

1. Run `ll-loop run <fsm> --verbose` on a loop whose first state is a Claude prompt producing a long multi-paragraph reply. Before: one truncated row ending in `...`. After: full reply with paragraph breaks.
2. Run a loop whose action is `bash -c "seq 1 50"` with `--verbose`. Each numeric line prints on its own row unchanged.
3. Re-run a prompt loop without `--verbose` — the 8-line head preview from `_helpers.py:448-468` should still cap at 8 lines with `... (N more lines)` — behavior unchanged.
4. Inspect `ll-loop history <run-id>` or `events.jsonl` after a verbose run: `action_output` events for the prompt state should contain multiple entries (one per real line), not one giant entry. `ll-loop show` should render captured output with preserved structure.
5. Run `python -m pytest scripts/tests/` — especially the targets below — to confirm no regressions in event shape or captured-output fields.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete test targets and templates:_

**Existing test that locks in current single-call behavior (must be UPDATED or augmented):**
- `scripts/tests/test_subprocess_utils.py:1406-1430` — `test_assistant_event_text_passed_to_stream_callback` asserts `callback_calls == [("Stream me", False)]`. Single-line text still produces exactly one callback under Fix A, so the literal assertion continues to pass, but it doesn't cover the multi-line case. **Add a sibling test** `test_assistant_event_multiline_text_dispatched_per_line` using the `_make_single_line_selector` helper at `test_subprocess_utils.py:1336-1350` — inject an assistant event whose text contains `\n\n` and assert `len(callback_calls) == N`.

**Existing test that is the direct template for the Fix B regression test:**
- `scripts/tests/test_ll_loop_display.py:1566-1582` — `test_verbose_shell_output_printed_once` uses the `MockExecutor` (lines 34-52) and `_make_args(verbose=True)` helper (lines 1494-1503) with `capsys`. Clone this test for Fix B: inject an `action_output` event whose `line` field exceeds `terminal_width() - 8` characters (patch `terminal_width` to return 80), then assert the full text appears in `capsys.readouterr().out` AND `"..."` does not appear as a trailer.

**Prior-fix assertion pattern for "no truncation":**
- `scripts/tests/test_subprocess_mocks.py:265-304` (from ENH-979) shows the exact pattern: `assert "x" * 200 in out` paired with `assert "more lines" not in out`. The capsys equivalent for Fix B is `assert "x" * 200 in out` and `assert "x" * 200 + "..." not in out`.

**Unaffected tests (shape-level tests that construct events manually):**
- `scripts/tests/test_ll_loop_commands.py:721-836` construct `action_output` events manually in JSONL files — they test history/tail filtering, not emission. Fix A's 1→N change does not break them.
- `scripts/tests/test_generate_schemas.py:14-46` checks the schema catalog count (21) and `action_output` key presence — the per-event schema (one `line` field) is unchanged by Fix A.

**Targeted test run commands:**
```bash
python -m pytest scripts/tests/test_subprocess_utils.py::TestRunClaudeCommandStreaming -v
python -m pytest scripts/tests/test_ll_loop_display.py::TestDisplayProgressEvents -v
python -m pytest scripts/tests/ -k "verbose or stream or action_output" -v
```

## Related Key Documentation

| Category | File | Relevance |
|----------|------|-----------|
| Architecture | docs/ARCHITECTURE.md | FSM executor and event-stream design |
| Architecture | docs/reference/API.md | subprocess_utils and _helpers module reference |

## Critical Files

- `scripts/little_loops/subprocess_utils.py` — lines 198-219 (assistant-event text extraction and `stream_callback` dispatch)
- `scripts/little_loops/cli/loop/_helpers.py` — lines 419-424 (verbose `action_output` rendering); line 325 (`max_line` definition) for reference
- `scripts/little_loops/fsm/executor.py` — line 609 (2000-char preview; leave alone, non-causal in verbose)
- `scripts/little_loops/fsm/runners.py` — lines 91-93 (`_stream_cb` → `on_output_line` passthrough, no change needed)

## Integration Map

_Added by `/ll:refine-issue` — based on codebase research (locator + analyzer):_

### Files to Modify
- `scripts/little_loops/subprocess_utils.py:198-219` — restructure `etype == "assistant"` branch to split on newlines and dispatch `stream_callback` per sub-line; append each sub-line to `stdout_lines` individually; `continue` past the generic tail at 218-219.
- `scripts/little_loops/cli/loop/_helpers.py:419-424` — remove the `display = line[:max_line] + "..."` clip for `action_output` in verbose; print `line` verbatim so the terminal wraps.

### Upstream / Downstream Callers (verified no-change-needed)
- `scripts/little_loops/fsm/runners.py:91-93` — `_stream_cb` transparent passthrough to `on_output_line`.
- `scripts/little_loops/fsm/executor.py:574-577` — `_on_line` emits one `action_output` event per callback invocation; 1→N emit count is correct by construction.
- `scripts/little_loops/fsm/persistence.py:232-239` — `append_event` writes one JSONL line per event; N events = N JSONL lines (correct).
- `scripts/little_loops/cli/loop/info.py:249-252, 464-465, 500-503` — `cmd_history` iterates per-event; no consumer joins consecutive `action_output` events. `cmd_show` does not render `action_output` at all.
- `scripts/little_loops/fsm/evaluators.py` — consumes `result.output` (joined stdout string), not the event stream. Unchanged because `"\n".join(stdout_lines)` reconstructs full text.
- `scripts/little_loops/issue_manager.py:133-138` — second `stream_callback` consumer (ll-auto/ll-sprint path). 1→N callback count is benign (N `print(line)` vs 1 `print(multi-line)` render identically).

### Tests to Add or Update
- `scripts/tests/test_subprocess_utils.py:1406-1430` — existing `test_assistant_event_text_passed_to_stream_callback` still passes; **add** a sibling multi-line test using `_make_single_line_selector` at `test_subprocess_utils.py:1336-1350`.
- `scripts/tests/test_ll_loop_display.py:1566-1582` — clone `test_verbose_shell_output_printed_once` for Fix B: multi-paragraph `action_output` line must print in full with no `"..."` trailer. Use `MockExecutor` (lines 34-52) + `_make_args(verbose=True)` (lines 1494-1503).

### Tests Verified Unaffected
- `scripts/tests/test_ll_loop_commands.py:721-836` — construct events manually, don't exercise `subprocess_utils.py`.
- `scripts/tests/test_generate_schemas.py:14-46` — schema count/shape unchanged.
- `scripts/tests/test_fsm_executor.py`, `test_fsm_persistence.py`, `test_events.py` — event emission/persistence semantics unchanged per-event.

### Documentation to Re-check (no required update expected)
- `docs/reference/EVENT-SCHEMA.md:136` — `action_output` schema (one `line` field) still accurate.
- `docs/reference/schemas/action_output.json` — generated; run `ll-generate-schemas` if the schema code ever changes (not required for this fix).
- `docs/reference/OUTPUT_STYLING.md`, `docs/reference/CLI.md` — `--verbose` behavior description: verify no claim like "one row per action" exists that would be contradicted by the N-event change.

### Similar Pattern / Prior Fix to Model After
- **ENH-979** (`.issues/completed/P3-ENH-979-ll-auto-verbose-full-content-no-truncation.md`) — directly analogous verbose-truncation fix on a different pipeline (`issue_manager.py` path). Its test pattern at `test_subprocess_mocks.py:265-304` is the template for "full content, no `...` trailer" assertions.
- **BUG-566** (`.issues/completed/P3-BUG-566-ll-loop-run-output-truncated-for-shell-commands.md`) — established the "verbose path shows full; non-verbose path clips" convention in `_helpers.py` that Fix B extends to `action_output`.

## Related Issues

- Completed: ENH-1051 — Show prompt state response in **non-verbose** mode (opposite mode; different code path).
- Completed: ENH-979 — `ll-auto --verbose` truncation (different CLI, different file `issue_manager.py`).
- Completed: BUG-566 / BUG-564 — earlier `ll-loop run` output sparseness (different symptoms, addressed preview length not live streaming).

## Impact

- **Priority**: P3 — defect only surfaces under `--verbose` (opt-in inspection flag); no data loss (full output still persisted to events.jsonl and `result.stdout`).
- **Effort**: Small — ~10 lines changed across two files, plus one new and one cloned test.
- **Risk**: Low — directly analogous to completed fix ENH-979; callers verified unchanged (`issue_manager.py`, `fsm/executor.py`, `fsm/runners.py`, `fsm/persistence.py`, `info.py`).
- **Breaking Change**: No — event shape per-event is unchanged (one `line` field). The only observable change is 1→N `action_output` events per assistant response; no downstream consumer joins consecutive events.

## Labels

`bug`, `cli`, `ll-loop`, `verbose-output`, `refined`

## Resolution

Both fixes applied as planned:

- **Fix A** (`scripts/little_loops/subprocess_utils.py:198-222`) — restructured `etype == "assistant"` branch to join text blocks with `"\n\n"`, split into real lines via `splitlines()`, and dispatch `stream_callback` once per sub-line. Each sub-line is appended to `stdout_lines` individually so `"\n".join(stdout_lines)` reconstructs the full text for `result.stdout` and downstream evaluators.
- **Fix B** (`scripts/little_loops/cli/loop/_helpers.py:419-423`) — removed the `display = line[:max_line] + "..."` clip on the verbose `action_output` branch. The terminal now wraps long lines instead of being silently truncated.

Tests added:
- `test_subprocess_utils.py::TestRunClaudeCommandModelDetection::test_assistant_event_multiline_text_dispatched_per_line` — multi-paragraph assistant text dispatches stream_callback per real line; reconstructed `result.stdout` preserves the full text.
- `test_ll_loop_display.py::TestDisplayProgressEvents::test_verbose_action_output_not_clipped` — 200-char `action_output` line under 80-col terminal renders in full with no `"..."` trailer.

Verified: targeted suites (`TestRunClaudeCommandModelDetection`, `TestDisplayProgressEvents`, all `verbose|stream|action_output|assistant`-keyword tests) pass; full `pytest scripts/tests/` runs 4831 passed (1 unrelated pre-existing failure: `test_expected_loops_exist` missing `autodev` from expected set, present on main without these changes); `ruff check scripts/` clean; `mypy` clean on both modified modules.

## Session Log
- `/ll:manage-issue` - 2026-04-16T13:29:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e8088d28-1441-4c5b-b904-dd061399021d.jsonl`
- `/ll:ready-issue` - 2026-04-16T18:24:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2fb1a4ee-5512-43ed-b858-2a21a4738fb8.jsonl`
- `/ll:confidence-check` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5d0bd034-325a-41e5-8b99-228d276a913d.jsonl`
- `/ll:refine-issue` - 2026-04-16T18:18:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/57cdaad0-2b25-4d7b-bcd0-33867cfa3683.jsonl`
- `/ll:capture-issue` - 2026-04-16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5cbadf88-a8c9-4bb2-bbd8-6c53bfc5e75e.jsonl`

---

## Status
- **Priority**: P3
- **Type**: BUG
- **State**: completed
