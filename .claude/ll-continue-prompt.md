# Session Continuation: Refine BUG-616 Issue

## Conversation Summary

### Primary Intent
Refine issue BUG-616 (`ready-issue` returns `CORRECTED` instead of `BLOCKED` when open blockers exist) with codebase research to fill knowledge gaps needed for implementation.

### What Happened
1. **Invoked `/ll:refine-issue BUG-616`** — read the issue file and launched 3 parallel research agents (codebase-locator, codebase-analyzer, codebase-pattern-finder)
2. **Agent timeout issues** — background agents completed but task IDs expired before output could be captured; performed direct research manually to compensate
3. **Direct codebase research** — searched across `commands/ready-issue.md`, `scripts/little_loops/output_parsing.py`, `scripts/little_loops/issue_manager.py`, `scripts/little_loops/parallel/worker_pool.py`, `scripts/little_loops/dependency_graph.py`, and test files
4. **Key discovery** — Found that `commands/ready-issue.md:156` explicitly states "Open blockers are a WARNING, not a failure. The issue can still be marked READY" — this is the design decision that must change. Also found `output_parsing.py:23` `VALID_VERDICTS` tuple does not include `BLOCKED`.
5. **Updated issue file** — Enriched Root Cause (with precise file:line refs), Implementation Steps (4 concrete steps across 2 files), and Integration Map (2 files to modify, 3 dependent callers, 2 similar patterns, 2 test files)
6. **Appended session log** entry to the issue file

### User Feedback
No corrections or guidance provided during the session.

### Errors and Resolutions
| Error | How Fixed | User Feedback |
|-------|-----------|---------------|
| Background agents timed out / task IDs expired | Performed direct Grep/Read research on the same files | None |
| One agent ID not found (`a899819b98c373576`) | Skipped; covered by manual research | None |

### Code Changes
| File | Changes Made | Discussion Context |
|------|--------------|-------------------|
| `.issues/bugs/P2-BUG-616-ready-issue-returns-corrected-instead-of-blocked-when-open-blockers-exist.md` | Enriched Root Cause, Implementation Steps, Integration Map sections with codebase research findings; appended session log | Refine-issue research enrichment |

## Resume Point

### What Was Being Worked On
BUG-616 refinement completed. User then requested `/ll:handoff`.

### Direct Quote
> User invoked `/ll:handoff` after the refinement was complete.

### Next Step
The refined BUG-616 is ready for the next pipeline step:
- Run `/ll:ready-issue BUG-616` to validate the enriched issue
- Then `/ll:manage-issue` to implement (modify `commands/ready-issue.md` and `scripts/little_loops/output_parsing.py`)
- BUG-617 should be implemented after BUG-616 (companion fix for sprint runner to handle BLOCKED verdict)

## Important Context

### Decisions Made
- **Root cause is a design decision, not a bug in logic**: Line 156 of `ready-issue.md` explicitly says blockers are warnings only. The fix requires changing this policy.
- **Two files need modification**: `commands/ready-issue.md` (verdict taxonomy + blocker policy) and `scripts/little_loops/output_parsing.py` (VALID_VERDICTS + extraction logic)
- **Downstream callers already handle BLOCKED implicitly**: Both `issue_manager.py:474` and `worker_pool.py:321` check `not parsed["is_ready"]`, which will catch BLOCKED since `is_ready` stays False. Explicit BLOCKED handling (BUG-617) is still needed in sprint runner for `skipped_blocked` state.

### Gotchas Discovered
- **`output_parsing.py` must also be updated** — the issue originally only mentioned `commands/ready-issue.md`, but the Python parsing layer at `VALID_VERDICTS` and `_extract_verdict_from_text()` also needs BLOCKED added or it will never be parsed
- **Verdict priority order matters** — BLOCKED must be checked before READY/CORRECTED in the verdict taxonomy to ensure it overrides corrections

### User-Specified Constraints
None specified.

### Patterns Being Followed
- Following existing blocker check pattern at `commands/ready-issue.md:148-154` (already validates Blocked By entries, just needs to force verdict)
- Following `dependency_graph.py:112-134` `get_ready_issues()` / `get_blocking_issues()` pattern for blocker-aware logic
