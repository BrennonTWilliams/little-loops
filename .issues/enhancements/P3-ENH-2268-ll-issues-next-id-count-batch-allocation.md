---
id: ENH-2268
title: ll-issues next-id --count N for collision-free batch ID allocation
type: enhancement
status: open
priority: P3
discovered_date: 2026-06-24
discovered_by: planning-assessment
labels:
- enhancement
- ll-issues
- next-id
- data-safety
confidence_score: 100
outcome_confidence: 87
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 22
---

# ENH-2268: `ll-issues next-id --count N` batch allocation

## Summary

Add a `--count N` flag to `ll-issues next-id` that prints `N` consecutive,
globally-unique issue numbers (`max+1 .. max+N`) in one call. This hardens
the **batch issue-creation** workflow, which is the actual failure mode behind
the 2026-06-24 near-collision — not a bug in `next-id`'s scanner.

## Current Behavior

`ll-issues next-id` returns a single ID (`max+1`) derived from one filesystem
scan. Batch workflows that need N IDs must either:

1. Call `ll-issues next-id` N times (N filesystem scans; still racy between
   writes), or
2. Manually increment from a single call (collision-prone if pre-existing IDs
   fill the range).

Neither approach is safe under concurrent session writes.

## Motivation

`get_next_issue_number()` (`scripts/little_loops/issue_parser.py:113`) is
correct: it globs the live filesystem across all category dirs + legacy dirs
and returns `max+1`, independent of git staging state (verified by
reproduction — an on-disk `BUG-2264` correctly yields `2265`).

The near-collision occurred because a multi-issue session allocated IDs by
**manually incrementing from a single `next-id` call** (e.g. 2257, 2258, …,
2264) rather than re-querying per file. A pre-existing on-disk `BUG-2264`
then collided with the manually-chosen `2264`. The PreToolUse/PostToolUse
duplicate-ID hooks caught it, but the workflow shouldn't generate the
collision in the first place.

`next-id` returns only one ID, so a batch creator either calls it N times
(N filesystem scans, and still racy between writes) or hand-increments
(collision-prone). A batch primitive removes the foot-gun.

## Expected Behavior

```bash
ll-issues next-id              # 2268        (unchanged, single ID)
ll-issues next-id --count 3    # 2268\n2269\n2270   (newline-separated)
```

- `--count` defaults to 1 (current behavior; backward compatible).
- Output is `N` lines, each zero-padded to 3 digits like today's single output.
- Numbers are `max+1 .. max+N` from a single filesystem scan.
- `--count` must be a positive integer; reject `0`/negatives with exit 2.

## API/Interface

```
ll-issues next-id [--count N]
```

- `--count N` (int, default=`1`): Number of consecutive IDs to allocate.
  Must be a positive integer; exit 2 for `0` or negative values.
- Output: `N` newline-separated zero-padded IDs (e.g. `2268\n2269\n2270`).
- Backward compatible: omitting `--count` (or `--count 1`) is byte-for-byte
  identical to the current single-ID output.

## Acceptance Criteria

1. `ll-issues next-id` with no flag is byte-for-byte unchanged.
2. `ll-issues next-id --count 3` prints 3 consecutive zero-padded IDs starting
   at `max+1`, one per line.
3. `--count 0` and negative values are rejected (argparse exit 2).
4. Unit test: with max ID = N on disk, `--count 3` yields `[N+1, N+2, N+3]`.
5. (Optional) `skills/capture-issue` and any batch creators documented to use
   `--count` when creating multiple issues in one pass.

## Scope Boundaries

- **In scope**: `--count N` flag on `ll-issues next-id`; single-scan batch
  allocation returning `max+1 .. max+N`; rejection of invalid `--count` values.
- **Out of scope**: True atomic reservation / advisory file locking; changes to
  the ID zero-padding width or format; modifying other `ll-issues` subcommands;
  auto-retry on race conditions (callers should re-query if needed).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — `cmd_next_id`: add
  `--count` argparse arg; loop to emit N IDs from a single scan.
- `scripts/little_loops/issue_parser.py` — `get_next_issue_number()` may
  be extended with a `count` param, or a thin wrapper added.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**File correction**: `cmd_next_id` is NOT in `__init__.py` — it lives in `scripts/little_loops/cli/issues/next_id.py`. Two files require changes:
- `scripts/little_loops/cli/issues/next_id.py` — `cmd_next_id(config: BRConfig) -> int`: update signature to accept `count`; call `get_next_issue_number(config)` once to get `base`; loop `for i in range(count): print(f"{base + i:03d}")`.
- `scripts/little_loops/cli/issues/__init__.py:135-139` — `nid` subparser registration block: add `nid.add_argument("--count", "-n", type=int, default=1, metavar="N", ...)`.
- `scripts/little_loops/cli/issues/__init__.py:706-707` — dispatch currently calls `cmd_next_id(config)` with no `args` forwarded; must be updated to pass `args.count` (or pass `args` directly).
- `scripts/little_loops/issue_parser.py:113` — `get_next_issue_number(config, category=None) -> int` — no change required; call once and compute the range in the handler.

### Tests
- `scripts/tests/test_issues_cli.py` (or nearest sibling) — add: with max
  ID = N on disk, `--count 3` yields `[N+1, N+2, N+3]`; `--count 0` exits 2.

_Research confirmed_: Existing class `TestIssuesCLINextId` at lines 14–57 is the right target. For the `--count 0` / negative tests, use `pytest.raises(SystemExit) as exc_info; assert exc_info.value.code == 2` — argparse type validators raise `SystemExit(2)`, not a handler return-value. (Contrast: `test_limit_zero_raises_error` at line 466 checks `result == 1` because `--limit` does runtime validation in the handler; `--count` should use argparse-level validation for the exit-2 guarantee.)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py` — `TestGetNextIssueNumber` class (lines 860–982): tests `get_next_issue_number()` directly with six test methods. If a `get_next_issue_numbers(config, count)` helper is added, new companion tests for `count=3` in empty and populated dirs belong here. If the range computation stays entirely in `cmd_next_id` with no change to `get_next_issue_number`, this file needs no changes. [Agent 3 finding]

### Documentation
- `skills/capture-issue/SKILL.md` — note `--count` usage for batch creation.
- `CLAUDE.md` `ll-issues` entry — mention `--count` flag.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — section `#### ll-issues next-id / ll-issues ni` currently only says "Print the next globally unique issue number" with no flags listed; add a `--count N` / `-n N` row in the same table style used by adjacent subcommands [Agent 2 finding]
- `docs/reference/API.md` — `next-id` row in the sub-commands table (~line 3280) reads "Print next globally unique issue number" — update to mention batch mode [Agent 2 finding]

### Dependent Files (Callers/Importers)
- Any skill or loop that calls `ll-issues next-id` multiple times in a session
  is a candidate for migration to `--count`.

_Research confirmed specific callers:_

Skills with explicit "do NOT batch-allocate IDs upfront" warnings — highest-priority migration candidates:
- `skills/scope-epic/SKILL.md:279` — "Call `ll-issues next-id` **immediately before each Write** — do NOT batch-allocate IDs upfront."
- `skills/debug-loop-run/SKILL.md:351` — same anti-batch-allocate note
- `skills/capture-issue/SKILL.md:245,326` — calls `next-id` once per issue; also references duplicate-ID recovery
- `skills/issue-size-review/SKILL.md:274`, `skills/audit-loop-run/SKILL.md:309` — single-call patterns

Commands with manual sequential allocation (exact foot-gun this feature addresses):
- `commands/scan-codebase.md:228,230` — "If `ll-issues next-id` prints `011`, assign 011, 012, 013, etc."
- `commands/scan-product.md:221,223` — same manual sequential pattern

Python callers of `get_next_issue_number()` (not affected by CLI flag; listed for completeness):
- `scripts/little_loops/sync.py:676`
- `scripts/little_loops/issue_lifecycle.py:445`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/writers.py:82` — static string in `ll-init`'s generated `CLAUDE.md` template lists `ll-issues` with `(next-id, ...)` in the help block; if the `CLAUDE.md` entry for `next-id` is updated to mention `--count`, this writer template should receive the same update [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/cli/loop/__init__.py:615-622` — `next-loop` subparser uses the exact `--count`/`-n` argparse pattern (`type=int, default=1, metavar="N"`); follow this for the `next-id` subparser.

### Configuration
- N/A

## Implementation Steps

1. Add `--count N` argparse arg (type=int, default=1) to `cmd_next_id`; validate
   > 0, else `parser.error()` (exits 2).
2. Extend `get_next_issue_number()` or add a `get_next_issue_numbers(count)`
   helper that performs one glob scan and returns `[max+1, ..., max+count]`.
3. Emit each ID on its own line (same zero-padding as current single output).
4. Write unit test covering: default behavior unchanged; `--count 3`; `--count 0`
   → exit 2.
5. (Optional) Update `skills/capture-issue` and relevant docs to recommend
   `--count` for batch creation workflows.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/CLI.md` — add `--count N` / `-n N` flag row under the `ll-issues next-id / ll-issues ni` section, matching the table style used by adjacent subcommands
7. Update `docs/reference/API.md` — revise the `next-id` row in the sub-commands table to reflect batch mode capability
8. (If CLAUDE.md `ll-issues` entry is updated) Mirror the same update in `scripts/little_loops/init/writers.py:82` so `ll-init`-generated CLAUDE.md files stay in sync

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 (argparse)**: Add to `nid` subparser block in `__init__.py:135-139`, following the pattern in `scripts/little_loops/cli/loop/__init__.py:615-622`. Use a `positive_int` type validator function (raises `argparse.ArgumentTypeError` for ≤0) so argparse exits with code 2 at parse time — satisfies acceptance criterion 3 without a `sys.exit()` in the handler.
- **Step 1b (dispatch)**: Update `__init__.py:706-707` from `cmd_next_id(config)` to pass `args.count` (e.g. `cmd_next_id(config, count=args.count)`).
- **Step 2 (handler)**: In `next_id.py:cmd_next_id()`, call `get_next_issue_number(config)` once to get `base`, then `for i in range(count): print(f"{base + i:03d}")`. No changes to `get_next_issue_number` itself are needed.
- **Step 4 (tests)**: Add to `TestIssuesCLINextId` in `scripts/tests/test_issues_cli.py:14-57`. Use `pytest.raises(SystemExit) as exc_info; assert exc_info.value.code == 2` for the `--count 0` test (argparse-level validation raises `SystemExit`, not a handler return value).

## Impact

- **Effort**: S — one argparse flag + a loop in `cmd_next_id`, plus a test.
- **Risk**: Low — additive, default preserves current behavior.
- **Breaking Change**: No.

## Related

- BUG-2265 (set-status cascade) — sibling data-safety fix from the same session.
- BUG-1364 (duplicate-ID hook TOCTOU race) — done; the safety net this
  complements.
- ENH-986 (enforce unique integer IDs across types).

## Status

**Open** | Created: 2026-06-24 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-06-24T21:00:00 - `fffe04a2-92e2-4f19-bafe-0d8c500f9b47.jsonl`
- `/ll:wire-issue` - 2026-06-24T20:41:43 - `ff0c7bdb-b5b2-42d5-a9a1-7e8abfc9a0ed.jsonl`
- `/ll:refine-issue` - 2026-06-24T20:28:05 - `de730a3f-9cf8-4a76-8678-a41c35dafd15.jsonl`
- `/ll:format-issue` - 2026-06-24T19:54:46 - `671613d2-868e-4451-bec7-a270a767c5ac.jsonl`
