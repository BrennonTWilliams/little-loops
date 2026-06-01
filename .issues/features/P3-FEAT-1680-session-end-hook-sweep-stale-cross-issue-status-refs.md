---
id: FEAT-1680
title: Session-end hook to sweep stale cross-issue status references
type: FEAT
priority: P3
status: open
discovered_date: 2026-05-24
captured_at: "2026-05-24T17:21:20Z"
discovered_by: capture-issue
labels:
  - hooks
  - automation
  - issue-management
parent: EPIC-1707
---

# FEAT-1680: Session-end hook to sweep stale cross-issue status references

## Summary

Add a `Stop` hook that fires at the end of every Claude Code session. It collects
all issue IDs currently marked `status: done`, greps open issue files for prose
that still asserts those IDs are `open` or `in_progress`, and reports (or
auto-fixes) the stale references in one batched pass — after editing is complete,
so it doesn't interrupt mid-session work.

## Current Behavior

When an issue is marked `done`, prose in other open issue files (blocker notes,
concerns sections, session logs) may still reference that ID as `open`,
`in_progress`, or describe it as an active blocker. There is no automated
mechanism to detect or clean up these stale references. Engineers must manually
audit issue files after marking work done, which is easy to forget and causes
Claude Code to treat completed work as active in subsequent sessions.

## Expected Behavior

A `Stop` hook fires at the end of every Claude Code session. It collects all
issue IDs with `status: done`, greps open issue files for patterns like
`"<ID> is (still )?(open|in_progress|active)"` and `"blocked by .*<ID>"`
(where the blocker is already done), and prints a concise report (file path,
line number, matched phrase) for each stale reference found. If
`hooks.stale_ref_fix: auto` is set in `ll-config.json`, stale phrases are
rewritten automatically. The hook exits 0 in all cases and completes in under
2s on repos with ~400 issue files when no matches are found.

## Motivation

When an issue is marked `done`, prose in other issue files (blockers notes,
concerns sections, session logs) often still says "X is still open" or "blocked
by X". These stale phrases confuse Claude in future sessions, causing it to treat
done work as active. Manual cleanup is easy to forget. A session-end hook catches
the drift automatically without slowing down the session itself.

## Use Case

Engineer marks FEAT-1112 `done` mid-session. At session end the hook runs,
finds ENH-1114 saying "FEAT-1112 is still `open`", flags it in the terminal
summary. Engineer can approve an auto-fix or address it manually before the next
session starts.

## Implementation Steps

1. **Detect done issues**: Read all `.issues/**/*.md` frontmatter; collect IDs
   with `status: done`.
2. **Find stale prose**: For each done ID, grep open issue files for patterns
   like `"<ID> is (still |now )?(open|in_progress|active)"` or
   `"blocked by .*<ID>"` (where the blocker is done).
3. **Report findings**: Print a concise summary to stdout — file path, line
   number, matched phrase. Exit cleanly if nothing found.
4. **Optional auto-fix**: If `hooks.stale_ref_fix: auto` is set in
   `ll-config.json`, pass each hit file through a targeted LLM rewrite
   (or a deterministic sed pattern for the simple `is open/in_progress` case).
5. **Wire into hooks**: Register as a `Stop` event handler in `hooks/hooks.json`.
   Keep the script fast — if grep finds no matches it should complete in < 1s.

## Integration Map

### Files to Modify
- `hooks/hooks.json` — add `Stop` event handler entry

### New Files
- `scripts/little_loops/hooks/sweep_stale_refs.py` — new hook script
- `scripts/tests/test_sweep_stale_refs.py` — unit tests

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/main_hooks.py` — invokes hook scripts; verify `Stop` event routing

### Similar Patterns
- `scripts/little_loops/hooks/session_start.py` — reference for hook script structure and exit conventions
- Other `Stop`/`PostToolUse` handlers in `hooks/hooks.json` for timeout and error conventions

### Tests
- `scripts/tests/test_sweep_stale_refs.py` (new) — unit tests covering: no-match fast path, single stale ref detection, multiple files, auto-fix mode

### Documentation
- N/A — hook is self-documenting via `hooks/hooks.json` and the `--help` flag

### Configuration
- `ll-config.json` — optional `hooks.stale_ref_fix: "report" | "auto"` knob

## API / Interface

```json
// hooks/hooks.json addition
{
  "event": "Stop",
  "command": "python scripts/little_loops/hooks/sweep_stale_refs.py",
  "timeout": 30
}
```

```python
# scripts/little_loops/hooks/sweep_stale_refs.py
# Exits 0 always (findings are advisory, not blocking)
```

Optional config knob in `ll-config.json`:
```json
"hooks": {
  "stale_ref_fix": "report"   // "report" | "auto"
}
```

## Acceptance Criteria

- [ ] Hook script exists at `scripts/little_loops/hooks/sweep_stale_refs.py`
- [ ] Registered in `hooks/hooks.json` under `Stop` event
- [ ] Given a done issue ID, correctly identifies files with stale `is open` /
      `in_progress` prose referencing that ID
- [ ] Outputs file path + line number + matched text per finding
- [ ] Exits 0 in all cases (never blocks session end)
- [ ] Completes in < 2s on a repo with ~400 issue files when no matches found
- [ ] Unit tests in `scripts/tests/test_sweep_stale_refs.py`

## Impact

- **Priority**: P3 — improves issue hygiene and prevents context confusion in future sessions; non-blocking quality improvement
- **Effort**: Small — ~100-line Python script, `hooks/hooks.json` registration, unit tests; reuses existing frontmatter parsing utilities (`ll-issues`, `scripts/little_loops/`)
- **Risk**: Low — hook exits 0 always; auto-fix mode requires explicit opt-in via config; grep-only path is purely advisory
- **Breaking Change**: No

## Out of Scope

- Fixing `blocked_by:` frontmatter fields (separate concern; `ll-deps` handles
  dependency validation)
- Real-time (PostToolUse) triggering — deferred due to interleaving complexity
- Structured reference markers (Approach B from brainstorm) — separate ENH if
  convention is adopted later

---

**Open** | Created: 2026-05-24 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-24T17:28:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/20c144e8-2658-4919-b9a3-e1bfd4e0786b.jsonl`

- `/ll:capture-issue` - 2026-05-24T17:21:20Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a638383a-aa90-4ed6-80c0-1913cf58a71c.jsonl`
