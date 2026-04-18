---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1082
testable: false
confidence_score: 95
outcome_confidence: 85
---

# FEAT-1085: Parallel State Create-Loop Skill Documentation

## Summary

Update `skills/create-loop/reference.md`, `skills/create-loop/loop-types.md`, `skills/create-loop/SKILL.md`, and `skills/create-loop/templates.md` to document the `parallel:` state type as a peer concurrent fan-out mechanism.

## Parent Issue

Decomposed from FEAT-1082: Parallel State Documentation

## Current Behavior

- `skills/create-loop/reference.md:686` `loop:` field section has no adjacent `parallel:` documentation
- `skills/create-loop/loop-types.md:978` sub-loop composition section describes `loop:` as the only child mechanism; `parallel:` is absent
- `skills/create-loop/SKILL.md:82-90` type mapping section has no mention of `parallel:` as a fan-out option
- `skills/create-loop/templates.md` has no `parallel:` YAML template (composition types may have templates; needs review)

## Expected Behavior

- `skills/create-loop/reference.md` documents `parallel:` field immediately after the `loop:` field block (same format)
- `skills/create-loop/loop-types.md` presents `parallel:` as a peer concurrent fan-out mechanism alongside `loop:` (sequential single-loop invocation)
- `skills/create-loop/SKILL.md` type mapping section notes `**Parallel fan-out** — not a wizard type; use \`parallel:\` field in YAML (see \`reference.md\`)`
- `skills/create-loop/templates.md` includes a `parallel:` fan-out YAML template (if composition type templates exist)

## Proposed Solution

### `skills/create-loop/reference.md`

After line 731 (end of `#### loop (Optional)` field block), add a new `#### parallel (Optional)` field block in the same format. Document all fields:
- `items` — required, interpolated expression
- `loop` — required, sub-loop name
- `max_workers` — optional, default 4
- `isolation` — optional, `"thread"` or `"worktree"`, **default `"thread"`** (opt into `"worktree"` only when sub-loops write files concurrently)
- `fail_mode` — optional, `"collect"` or `"fail_fast"`, default `"collect"`
- `context_passthrough` — optional, bool, default `false`
- `timeout_seconds` — optional, `int | None`, default `None` (no timeout); per-worker wall-clock cap; timed-out workers are aggregated under `fail_mode`

Include mutual exclusion note: `parallel` cannot be combined with `action`, `loop` (field), or `next`. The error message for `parallel` + `loop` directs authors to `parallel.loop` as the correct way to name the sub-loop to fan out.

### `skills/create-loop/loop-types.md`

After line 1014 (end of Sub-Loop Composition section), add a new `## Parallel Fan-Out` section as a peer mechanism:
- Describe concurrent fan-out over a list of items
- Compare with `loop:` (sequential, single invocation) vs `parallel:` (concurrent, N items)
- Include YAML example
- Document routing (`on_yes` / `on_partial` / `on_no`) and captures (`${captured.<state_name>.results}`)

### `skills/create-loop/SKILL.md`

At lines 82-90 (type mapping note section), add alongside the existing sub-loop composition note:
```
**Parallel fan-out** — not a wizard type; use `parallel:` field in YAML (see `reference.md`)
```

### `skills/create-loop/templates.md`

Review existing state-type templates. If templates exist for composition types (e.g., sub-loop invocation), add a `parallel:` fan-out YAML template in the same format. If no composition templates exist, no change needed.

## Implementation Steps

1. Update `skills/create-loop/reference.md` — add `#### parallel (Optional)` field block after `#### loop (Optional)`
2. Update `skills/create-loop/loop-types.md` — add `## Parallel Fan-Out` section after Sub-Loop Composition
3. Update `skills/create-loop/SKILL.md` — add parallel fan-out note to type mapping section
4. Review `skills/create-loop/templates.md` — add `parallel:` template if composition templates exist

## Integration Map

### Files to Modify

| File | Insertion Point | What to Add |
|------|----------------|-------------|
| `skills/create-loop/reference.md` | After line 731 (end of `#### loop (Optional)` block) | New `#### parallel (Optional)` field block |
| `skills/create-loop/loop-types.md` | After line 1014 (end of Sub-Loop Composition) | New `## Parallel Fan-Out` section |
| `skills/create-loop/SKILL.md` | Lines 82-90 (type mapping section) | Parallel fan-out note |
| `skills/create-loop/templates.md` | Conditional — after review | `parallel:` template if composition templates exist |

### Similar Patterns

- `skills/create-loop/reference.md:684–731` — `#### loop (Optional)` block: exact format to replicate for `parallel:`
- `skills/create-loop/loop-types.md:976–1014` — Sub-Loop Composition section: exact format to replicate for parallel fan-out

### `parallel:` Field Reference

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `items` | `str` | — | yes | Interpolated expression → newline-delimited item list |
| `loop` | `str` | — | yes | Sub-loop name (resolved via `.loops/<name>.yaml`) |
| `max_workers` | `int` | `4` | no | Maximum concurrent workers |
| `isolation` | `str` | `"thread"` | no | `"thread"` (shared dir, fast — default) or `"worktree"` (git-isolated; opt in when sub-loops write the same files concurrently) |
| `fail_mode` | `str` | `"collect"` | no | `"collect"` (all run) or `"fail_fast"` (cancel on first fail) |
| `context_passthrough` | `bool` | `false` | no | Pass a **shallow snapshot** (`dict(parent_captured)`) of parent context into each worker — never the live dict |
| `timeout_seconds` | `int \| None` | `null` | no | Per-worker wall-clock cap; `null` disables. Timed-out workers aggregate under `fail_mode`. |

Mutual exclusions: `parallel` + `action`, `parallel` + `loop` field, `parallel` + `next`.

### YAML Example

```yaml
# Thread-isolation example (the default — omit `isolation:` to get this)
- name: lint_files_concurrently
  parallel:
    items: "${captured.list_files.output}"
    loop: lint-single-file      # read-only sub-loop
    max_workers: 4
    fail_mode: collect
  on_yes: done
  on_partial: handle_partial
  on_no: handle_failure

# Worktree-isolation example (opt in only when sub-loops write files concurrently)
- name: refine_issues_concurrently
  parallel:
    items: "${captured.fetch.output}"
    loop: refine-to-ready-issue
    max_workers: 4
    isolation: worktree         # sub-loops edit issue files
    fail_mode: collect
    timeout_seconds: 600        # optional per-worker cap
  on_yes: done
```

## Dependencies

- No blocking dependencies — write against specified interface from FEAT-1074/FEAT-1075 issues

## Acceptance Criteria

- `skills/create-loop/reference.md` has `#### parallel (Optional)` block immediately after `#### loop (Optional)`, documenting all fields
- `skills/create-loop/loop-types.md` has a `## Parallel Fan-Out` section presenting `parallel:` as a peer to `loop:`
- `skills/create-loop/SKILL.md` type mapping section notes `parallel:` as a non-wizard fan-out type
- `skills/create-loop/templates.md` reviewed; `parallel:` template added if applicable

## Impact

- **Priority**: P2
- **Effort**: Small — 3-4 skill documentation files, targeted insertions
- **Risk**: Very Low — documentation-only
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `docs`, `skills`

---

## Session Log
- `/ll:issue-size-review` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/847acfcb-8aba-4124-8dc8-a98c7902e550.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
