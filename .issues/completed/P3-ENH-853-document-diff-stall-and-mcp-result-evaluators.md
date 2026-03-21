---
id: ENH-853
type: ENH
priority: P3
status: open
title: "Document diff_stall and mcp_result evaluators in generalized-fsm-loop.md"
created: 2026-03-21
confidence_score: 100
outcome_confidence: 93
testable: false
---

## Summary

Two FSM evaluator types are implemented but undocumented in `docs/generalized-fsm-loop.md`.

## Current Behavior

`diff_stall` and `mcp_result` are fully implemented in `scripts/little_loops/fsm/evaluators.py` and registered in `scripts/little_loops/fsm/schema.py:56-65`, but `docs/generalized-fsm-loop.md` contains no documentation blocks for either. Their type names appear in a schema comment at line 248 only. Users who want to configure these evaluators must read the source code directly.

## Expected Behavior

`docs/generalized-fsm-loop.md` includes a `#### \`diff_stall\`` subsection under Tier 1 Deterministic Evaluators (after the `convergence` block) and a `### Tier 3: MCP Evaluator` section with a `#### \`mcp_result\`` block (after Tier 2). Both blocks follow the patterns established by `convergence` and `exit_code` respectively, and include YAML config examples, verdict tables, and result detail descriptions.

## Missing Documentation

### `diff_stall` evaluator
- **File**: `scripts/little_loops/fsm/evaluators.py:373`
- **Verdicts**: `yes` (progress — diff changed), `no` (stalled — diff unchanged for `max_stall` iterations), `error`
- **Config fields**: `scope` (list of paths), `max_stall` (int, default 1)
- **Use case**: Detect when a fix loop is spinning without making filesystem changes

### `mcp_result` evaluator
- **File**: `scripts/little_loops/fsm/evaluators.py:468-525`
- **No user-configurable YAML fields** — `type: mcp_result` is the entire config; `output` and `exit_code` are injected by the executor, not set in YAML
- **Verdicts**: `success` (isError: false), `tool_error` (isError: true), `not_found` (exit 127), `timeout` (exit 124)
- **Use case**: Evaluate results from `action_type: mcp_tool` states
- **Note**: This is the only built-in evaluator that returns `success` as a verdict (not `yes`). A full `route:` table is required — `on_yes`/`on_no` shorthand will not match any of its verdicts.
- **Tier classification**: Does not fit Tier 1 (invokes external MCP process + parses protocol envelope) or Tier 2 (no LLM call). Needs its own `### Tier 3: MCP Evaluator` section (or equivalent), added after the `llm_structured` block ends at `generalized-fsm-loop.md:819`.

## Fix

Add a new subsection under "Tier 1: Deterministic Evaluators" for `diff_stall`, and a new `### Tier 3: MCP Evaluator` section (after Tier 2) for `mcp_result`. The schema type comment at `generalized-fsm-loop.md:360-363` already lists both names — no change needed there.

### Documentation Pattern (from existing evaluators)

Follow the exact pattern used by `convergence` (`generalized-fsm-loop.md:614-633`) for `diff_stall` (both are stateful Tier 1 evaluators with non-yes/no verdicts and optional fields):

```markdown
#### `diff_stall`

<one-sentence description>

```yaml
evaluate:
  type: diff_stall
  scope: ["src/", "tests/"]    # Optional: paths to pass to git diff --stat (default: entire repo)
  max_stall: 1                  # Optional: consecutive no-change iterations before `no` verdict
```

| Scenario | Verdict |
|----------|---------|
| First call (no prior snapshot) | `yes` |
| Diff changed since last iteration | `yes` |
| Diff unchanged, stall count < max_stall | `yes` |
| Diff unchanged, stall count >= max_stall | `no` |
| git unavailable or command failed | `error` |

Result details: `{ stall_count: <int>, max_stall: <int>, diff_changed: <bool> }`
```

For `mcp_result`, follow the minimal `exit_code` pattern (`generalized-fsm-loop.md:546-559`) since it has no YAML config fields. Add a note that a full `route:` table is required.

### Exact Insertion Points

- **`diff_stall`**: Insert after `convergence` block ends at `generalized-fsm-loop.md:519`, before the `---` separator at line 521.
- **`mcp_result`**: Insert after the Tier 2 `---` separator at `generalized-fsm-loop.md:705`, before `## Evaluation Source` at line 707, as a new `### Tier 3: MCP Evaluator` section.

### Supplementary Sources (already document these evaluators — use for consistency)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:528-542` — `diff_stall` field reference table
- `docs/guides/LOOPS_GUIDE.md:421-428` — `mcp_result` verdict table with exit-code analogues

## Integration Map

### Files to Modify
- `docs/generalized-fsm-loop.md` — primary target; add `diff_stall` at line 634 and `mcp_result` after line 819

### Implementation Files (read-only reference)
- `scripts/little_loops/fsm/evaluators.py:373-465` — `diff_stall` full implementation
- `scripts/little_loops/fsm/evaluators.py:468-525` — `mcp_result` full implementation
- `scripts/little_loops/fsm/schema.py:56-65` — `EvaluateConfig.type` Literal (both already registered)

### Existing Partial Documentation (for consistency)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:528-542` — `diff_stall` field table pattern
- `docs/guides/LOOPS_GUIDE.md:421-428` — `mcp_result` verdict table pattern
- `skills/create-loop/reference.md` — skill reference (may need parallel update)

### YAML Examples to Reference or Link
- `loops/harness-single-shot.yaml:37-49` — production `diff_stall` usage
- `loops/harness-multi-item.yaml:66-78` — production `diff_stall` usage
- `loops/harness-multi-item.yaml:101-116` — production `mcp_result` full `route:` table

### Tests
- `scripts/tests/test_fsm_evaluators.py` — covers both evaluators

## Implementation Steps

1. Read `docs/generalized-fsm-loop.md:500-521` to confirm `convergence` block and `---` separator location
2. Insert `#### \`diff_stall\`` subsection after line 519 (before `---` at line 521), following the `convergence` pattern
3. Read `docs/generalized-fsm-loop.md:700-707` to confirm Tier 2 ends at line 705
4. Insert `### Tier 3: MCP Evaluator` + `#### \`mcp_result\`` after line 705 (before `## Evaluation Source` at line 707)
5. Add a note in the `mcp_result` block that `on_yes`/`on_no` shorthand is incompatible — a full `route:` table is required
6. Cross-check field names and defaults against `evaluators.py:373-465` and `evaluators.py:468-525`
7. Optionally: update `skills/create-loop/reference.md` to match if it has a stale evaluator list


## Scope Boundaries

- No changes to evaluator implementations (`evaluators.py`)
- No changes to schema or config parsing (`schema.py`)
- No changes to `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` or `docs/guides/LOOPS_GUIDE.md` (already have partial docs; may add cross-links but not required)
- No new evaluator types introduced
- No changes to `skills/create-loop/reference.md` unless the evaluator list there is demonstrably stale (optional)

## Impact

- **Priority**: P3 — Documentation gap; evaluators work correctly but users can't discover config options without reading source
- **Effort**: Small — Documentation-only additions; all content is derivable from existing implementation and partial guide docs
- **Risk**: Low — No code changes; markdown-only edit to a reference doc
- **Breaking Change**: No

## Labels

`documentation`, `fsm`, `evaluators`, `enhancement`

## Resolution

Added `#### \`diff_stall\`` subsection under Tier 1 Deterministic Evaluators (after the `convergence` block) and `### Tier 3: MCP Evaluator` section with `#### \`mcp_result\`` block (after Tier 2) in `docs/generalized-fsm-loop.md`. Both blocks follow existing patterns with YAML config examples, verdict tables, and result detail descriptions. The `mcp_result` block includes a note that `on_yes`/`on_no` shorthand is incompatible and a full `route:` table is required.

## Status

**Completed** | Created: 2026-03-21 | Resolved: 2026-03-21 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-03-21T21:03:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d24ac2aa-b0a6-4dcf-ad84-5a82e6b41943.jsonl`
- `/ll:refine-issue` - 2026-03-21T20:56:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/046e2874-b7e6-4fdc-be3e-2cb5d08bf936.jsonl`
- `/ll:confidence-check` - 2026-03-21T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6954f438-c674-4534-8882-64f2cd0164a2.jsonl`
- `/ll:manage-issue enh implement ENH-853` - 2026-03-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
