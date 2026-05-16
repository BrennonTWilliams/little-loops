---
status: done
completed_at: 2026-04-21T00:00:00Z
---
> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1082
testable: false
confidence_score: 95
outcome_confidence: 85
---

# FEAT-1084: Parallel State Loop Usage Documentation

## Ship Companion

This issue ships in the **same release** as FEAT-1076. Docs MUST land in the same tag as the `parallel:` state dispatch — shipping code without these docs leaves users without a usage reference, and shipping docs without code references a feature that does not yet exist. If FEAT-1076 slips, this issue slips with it; do not merge docs ahead of code.

## Summary

Update `docs/guides/LOOPS_GUIDE.md`, `scripts/little_loops/loops/README.md`, and `docs/generalized-fsm-loop.md` to document the `parallel:` state type with YAML examples, table rows, and a dedicated fan-out section.

## Parent Issue

Decomposed from FEAT-1082: Parallel State Documentation

## Current Behavior

- `docs/guides/LOOPS_GUIDE.md:1653` "Composable Sub-Loops" section and comparison table (lines 1695–1700) describe only `loop:` and inline states; no `parallel:` row or YAML example
- `scripts/little_loops/loops/README.md:148` "Composing Loops" section references only the `loop:` field; no `parallel:` fan-out pattern
- `docs/generalized-fsm-loop.md` "Common Loop Patterns" table (lines 37-43) and Sub-Loop Composition section (~line 218) have no `parallel:` entry; Universal FSM Schema state definition block (~line 261) does not list a `parallel` field

## Expected Behavior

- `LOOPS_GUIDE.md` comparison table includes a `parallel:` row; a new "Parallel Fan-Out" YAML example section follows the Composable Sub-Loops section
- `loops/README.md` "Composing Loops" section describes `parallel:` fan-out pattern alongside `loop:`, with a minimal YAML snippet
- `docs/generalized-fsm-loop.md` has `parallel:` in the "Common Loop Patterns" table, a new "Parallel Fan-Out" section after Sub-Loop Composition, and `parallel` field in the Universal FSM Schema state definition

## Proposed Solution

### `docs/guides/LOOPS_GUIDE.md`

1. Add `parallel:` row to the "When to Use Sub-Loops vs. Inline States" comparison table at lines 1695–1700 (between `Sub-loop (loop:)` and `Inline states` rows)
2. Add a new `## Parallel Fan-Out (parallel:)` section after line 1689 (after the context-passthrough section), with:
   - Description of fan-out behavior
   - YAML example demonstrating a `parallel:` state with `items`, `loop`, `max_workers`, `isolation`, `fail_mode`
   - Routing conventions (`on_yes` / `on_partial` / `on_no`)

### `scripts/little_loops/loops/README.md`

Extend the "Composing Loops" section at line 161 (end of section) to describe `parallel:` fan-out alongside `loop:`:
- One paragraph explaining `parallel:` as concurrent fan-out over a list of items
- A minimal YAML snippet showing `parallel:` usage with required fields (`items`, `loop`)

### `docs/generalized-fsm-loop.md`

Three insertions:
1. **Lines 37-43** — Add `parallel:` row to the "Common Loop Patterns" table
2. **After ~line 218** (section 6 end / Sub-Loop Composition section end) — Add a new `## Parallel Fan-Out` section presenting `parallel:` as a peer concurrent mechanism alongside `loop:` (sequential single-loop invocation)
3. **~Line 261** (Universal FSM Schema state definition block) — Add `parallel` field alongside existing state fields

## Implementation Steps

1. Update `docs/guides/LOOPS_GUIDE.md` — add `parallel:` table row and new fan-out section with YAML example
2. Update `scripts/little_loops/loops/README.md` — extend Composing Loops section with `parallel:` description and YAML snippet
3. Update `docs/generalized-fsm-loop.md` — add to pattern table, add new section, add field to schema definition

## Integration Map

### Files to Modify

| File | Insertion Point | What to Add |
|------|----------------|-------------|
| `docs/guides/LOOPS_GUIDE.md` | Lines 1695–1700 (table), after line 1689 (new section) | `parallel:` table row; new `## Parallel Fan-Out (parallel:)` section with YAML |
| `scripts/little_loops/loops/README.md` | Line 161 (end of Composing Loops) | `parallel:` fan-out paragraph + YAML snippet |
| `docs/generalized-fsm-loop.md` | Lines 37-43 (table), ~line 218 (section), ~line 261 (schema) | Table row; new section; schema field |

### Similar Patterns

- `docs/guides/LOOPS_GUIDE.md:1653–1689` — Composable Sub-Loops section: format for YAML examples and section intro
- `docs/generalized-fsm-loop.md` existing sections for format reference

### YAML Example Pattern

```yaml
- name: process_items
  parallel:
    items: "${captured.fetch.output}"
    loop: process-single-item
    max_workers: 4
    # isolation defaults to "thread" — omit unless sub-loops write files concurrently
    fail_mode: collect
  on_yes: done
  on_partial: handle_partial
  on_no: handle_failure
```

And a second example showing when to opt into worktree isolation:

```yaml
- name: refine_issues_concurrently
  parallel:
    items: "${captured.issue_list.output}"
    loop: refine-to-ready-issue
    max_workers: 4
    isolation: worktree   # sub-loops write issue files; worktree prevents contention
    fail_mode: collect
    timeout_seconds: 600   # optional per-worker cap (None = no timeout)
  on_yes: done
```

### Isolation Mode: `thread` vs `worktree`

| Mode | Default? | When to use |
|------|----------|-------------|
| `thread` | **yes** | Read-heavy sub-loops (lint, review, analysis, evaluation). No filesystem contention. Fast — no worktree setup cost per worker. |
| `worktree` | no (opt-in) | Sub-loops that **write the same files concurrently**, need an isolated working tree for tests/builds, or mutate branch/stage state. Pays `git worktree add` cost per worker. |

Default guidance: **start with `thread`; switch to `worktree` only when you observe (or expect) concurrent write contention.** The schema default is `thread`, so omitting `isolation:` gives you the fast path automatically.

### Routing and Captures Reference

- Routing: `on_yes` (all succeeded), `on_partial` (mixed), `on_no` (all failed)
- Captures: `${captured.<state_name>.results}` is a list of dicts in **original item order** (one entry per item; slot `i` is item `i` regardless of which worker finished first). Each entry has:
  - `item` — original item string from the `items:` list
  - `item_index` — stable slot index (0-based)
  - `verdict` — `"yes"` (worker succeeded) or `"no"` (worker failed/timed out/cancelled)
  - `terminated_by` — one of `"terminal"`, `"error"`, `"timeout"`, `"signal"`, `"max_iterations"`, `"handoff"`, `"cancelled"`
  - `captures` — the worker's own `FSMExecutor.captured` dict at exit (empty on early failure)
  - `error` — short single-line failure message when `verdict != "yes"`, else `null`
- Common downstream patterns:
  - Filter successes: `${captured.<state>.results[*].verdict}` to count "yes" entries
  - Pull a specific worker's output: `${captured.<state>.results[0].captures.my_field}`
  - Inspect failures: `${captured.<state>.results[*].error}` (entries with `verdict == "no"` have a non-null error)
- Timeouts: `timeout_seconds` caps each worker individually; timed-out workers are aggregated under the configured `fail_mode` (`collect` or `fail_fast`) and recorded with `terminated_by: "timeout"`

## v1 Limitations (must appear verbatim in LOOPS_GUIDE.md and generalized-fsm-loop.md)

Set user expectations explicitly. Add a `### v1 Limitations` subsection at the end of the new "Parallel Fan-Out" section in both `docs/guides/LOOPS_GUIDE.md` and `docs/generalized-fsm-loop.md`. Include each of these bullets verbatim:

- **Ctrl-C latency**: running workers finish their current state before the thread pool shuts down. For long states (minutes+), `Ctrl-C` is not immediate. Full per-worker cancellation is planned for a future release.
- **No per-worker retries in v1**: `fail_mode` supports `collect` (let all workers finish, aggregate results) and `fail_fast` (cancel remaining on first failure). Retry-transient and skip-permanent modes are not yet available. Author-level retry: route `on_partial`/`on_no` back to the parallel state for a full re-run.
- **No resource-limit enforcement in v1**: `max_workers` is honored, but there is no hard cap on the total number of `items` fanned out and no enforced cumulative-timeout budget. Accidental 10k-item fan-outs are your responsibility to prevent. Soft warnings only when running under `ll-parallel` or `ll-sprint --parallel`.
- **`context_passthrough: bool` is binary-only**: pass everything or nothing. Finer-grained include/exclude filtering and secret-masking are not available.
- **Worker events merge into the parent event stream with no worker tag**: callback consumers see all workers' events interleaved. Live CLI display carries a per-worker label (FEAT-1081); programmatic callback tagging is planned (ENH-1177).
- **Thread-mode is the default and does not validate sub-loop safety**: `isolation: thread` is fast but shares the process. Sub-loops that write the same files concurrently in thread mode can corrupt state. Validation of sub-loop safety is planned (ENH-1178); until then, set `isolation: worktree` when sub-loops write files.
- **Nested `parallel:` states are forbidden**: a sub-loop invoked by a `parallel:` state cannot itself contain a `parallel:` state. Decompose or flatten.
- **`ll-loop simulate` runs parallel states sequentially**: simulation does not spawn real threads or worktrees; it exercises the same code path serially so routing and captures are identical.

Cross-reference the consolidated v1 scope and follow-ups issue: **P3-ENH-1186** (parallel-state v1 scope & limitations) — that issue is the single source of truth for "what's out of scope in v1."

## Dependencies

- FEAT-1074 (schema) and FEAT-1076 (runner) should be complete for exact field semantics; write against specified interface if not yet merged
- **Hard ship-coupling to FEAT-1076** — see Ship Companion section above

## Acceptance Criteria

- `LOOPS_GUIDE.md` comparison table includes `parallel:` row and a new Parallel Fan-Out section with YAML example
- `loops/README.md` "Composing Loops" describes `parallel:` fan-out with YAML snippet
- `generalized-fsm-loop.md` pattern table, section, and schema definition all include `parallel:`
- All three documents state the `isolation` default as `"thread"` (not `"worktree"`) and explain when to opt into `"worktree"` (concurrent file writes, isolated working tree needed)
- `timeout_seconds` is documented as an optional per-worker cap with `None` default meaning no timeout

## Impact

- **Priority**: P2
- **Effort**: Small — 3 documentation files, targeted insertions
- **Risk**: Very Low — documentation-only
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `docs`

---

## Session Log
- `/ll:issue-size-review` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/847acfcb-8aba-4124-8dc8-a98c7902e550.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
