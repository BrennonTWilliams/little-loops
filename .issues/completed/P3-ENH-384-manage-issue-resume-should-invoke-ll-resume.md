---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-384: manage_issue --resume should programmatically invoke /ll:resume

## Summary

When `manage_issue` is invoked with `--resume`, it only reads plan file checkboxes (`thoughts/shared/plans/`) to determine where to continue. It does not read `.claude/ll-continue-prompt.md` via `/ll:resume`, meaning the detailed handoff context (what was in progress, what failed, what's next) is lost. The two resume mechanisms are connected only by an implicit hope that the LLM reads the prose suggestion in the continuation prompt.

## Current Behavior

1. `manage_issue` exhausts context, writes `.claude/ll-continue-prompt.md` with detailed handoff state
2. User starts new session, runs `/ll:manage_issue [type] [action] [ID] --resume`
3. `--resume` logic (manage_issue.md:324-345) only scans the plan file for `[x]` checkboxes
4. The continuation prompt in `.claude/ll-continue-prompt.md` is never read
5. Detailed context about in-flight work, errors encountered, and next steps is lost

In the automated path (`ll-auto`), `run_with_continuation()` appends `--resume` to the command but also passes the continuation prompt via `-p`. In the manual path, there's no such bridge — the user runs the skill and the continuation prompt sits unread.

## Expected Behavior

When `--resume` is specified, `manage_issue` should:

1. Check if `.claude/ll-continue-prompt.md` exists
2. If it does, read and incorporate its context (equivalent to what `/ll:resume` does)
3. Then proceed with plan-checkpoint resume as it does today (scanning for `[x]` items)

This ensures the continuation prompt's detailed handoff context is used alongside the plan checkpoint state, giving the fresh session full awareness of what happened before context exhaustion.

## Motivation

Without this, manual session continuations lose significant context. The continuation prompt template includes specific details about what was being worked on, what errors occurred, and what should happen next. Discarding this forces the new session to re-discover context from scratch, wasting tokens and potentially repeating failed approaches.

## Proposed Solution

Add a step to `manage_issue.md`'s `--resume` handling (around line 324) that reads the continuation prompt before scanning plan checkboxes:

```markdown
### If --resume flag is set:

1. **Read continuation prompt** (if it exists):
   - Check for `.claude/ll-continue-prompt.md`
   - If found, read and display its content for context
   - Note: this provides handoff details from the previous session

2. **Resume from plan checkpoint** (existing behavior):
   - Locate existing plan matching issue ID in `thoughts/shared/plans/`
   - Scan for `[x]` checkmarks in success criteria
   - Continue from first unchecked item
```

This is a prompt-only change to `commands/manage_issue.md` — no Python code changes needed.

### Alternative: Invoke `/ll:resume` directly

Instead of duplicating the file-read logic, `manage_issue --resume` could invoke `/ll:resume` as a sub-step. However, `/ll:resume` has its own control flow (staleness checks, fallback to state file) that may conflict with `manage_issue`'s lifecycle. The simpler approach is to just read the file inline.

## Integration Map

### Files to Modify
- `commands/manage_issue.md` — Add continuation prompt reading to `--resume` handling (~line 324)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` — `run_with_continuation()` already appends `--resume`; this change makes that path more effective
- `scripts/little_loops/parallel/worker_pool.py` — Same continuation pattern

### Similar Patterns
- `commands/resume.md` — Reads the same `.claude/ll-continue-prompt.md` file with staleness checks

### Tests
- N/A — command markdown prompt change; verified by triggering context handoff and running `/ll:manage_issue ... --resume` in a new session

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Edit `commands/manage_issue.md` Phase 3 resume handling to read `.claude/ll-continue-prompt.md`
2. Ensure the continuation prompt context is presented before plan checkpoint scanning
3. Test manual resume flow end-to-end

## Impact

- **Priority**: P3 - Improves manual workflow reliability; automated path already works via `ll-auto`
- **Effort**: Small - Single prompt file edit
- **Risk**: Low - Additive behavior, no existing logic changes
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Adding continuation prompt reading to `--resume` handling in `manage_issue.md`
- **Out of scope**: Changing `/ll:resume` behavior or `ll-auto`'s continuation mechanism

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Resume/handoff lifecycle |
| guidelines | CONTRIBUTING.md | Skill development conventions |

## Blocks

- ENH-388: standardize issue priority range to P0-P8 (shared CONTRIBUTING.md, docs/ARCHITECTURE.md)

## Labels

`enhancement`, `commands`, `resume`, `captured`

## Session Log
- /ll:format_issue --all --auto - 2026-02-13
- /ll:manage_issue - 2026-02-13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38af4882-f822-4384-8eb2-3dfe1274a0a7.jsonl`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `commands/manage_issue.md`: Added step 1 to `--resume` handling that reads `.claude/ll-continue-prompt.md` continuation prompt before scanning plan checkboxes, incorporating handoff context from previous sessions

### Verification Results
- Tests: PASS (2733 passed)
- Lint: PASS

---

## Status

**Completed** | Created: 2026-02-12 | Priority: P3
