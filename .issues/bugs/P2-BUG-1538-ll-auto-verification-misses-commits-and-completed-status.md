---
captured_at: "2026-05-17T02:15:49Z"
discovered_date: 2026-05-17
discovered_by: capture-issue
status: open
priority: P2
type: BUG
relates_to:
  - BUG-280
  - BUG-1537
  - ENH-1533
---

# BUG-1538: ll-auto Phase 3 verification misses mid-phase commits and rejects `status: completed`

## Summary

`ll-auto --only ENH-1533 -v` logged "verification failed" and printed
`REFUSING to mark ENH-1533 as completed: no code changes detected despite returncode 0`,
yet the agent had actually completed the work successfully (commit `5b272e75`
landed on `main` with +488/-40 across 8 files). Two distinct bugs in Phase 3
verification combined to produce this false negative.

## Current Behavior

After Phase 2 succeeds:

1. `complete_issue_lifecycle` rejects the issue's frontmatter because the
   agent wrote `status: completed` instead of the canonical `status: done`
   (`Warning: ENH-1533 status=completed (expected done/cancelled)`).
2. The fallback `verify_work_was_done()` check returns False because the
   agent committed its work mid-Phase-2 — the working tree and index are
   both clean, so `git diff --name-only` and `git diff --cached --name-only`
   are empty.
3. Phase 3 logs "REFUSING to mark…" and leaves the issue in `open` despite
   the work being on `main`.

## Expected Behavior

Phase 3 should treat new commits made since Phase 2 began as evidence of
work, and should accept `status: completed` as an alias for `status: done`
when reading frontmatter. The agent's actual mid-phase commit (which
`manage-issue` SKILL.md explicitly tells the agent to make) should satisfy
verification.

## Root Cause

### Cause #1 — `verify_work_was_done()` ignores committed changes

- **File**: `scripts/little_loops/work_verification.py`
- **Anchor**: `def verify_work_was_done(logger, changed_files=None)` at line 44
- **Cause**: When `changed_files` is not supplied (the `ll-auto` path), the
  function only runs `git diff --name-only` (uncommitted) and
  `git diff --cached --name-only` (staged). It never inspects `git log` for
  commits created during Phase 2. Because `manage-issue` instructs the agent
  to commit before finishing, the expected end state is a clean tree — which
  the verifier reads as "no work done".

- **Caller**: `scripts/little_loops/issue_manager.py:890` —
  `work_done = verify_work_was_done(logger)` (no `changed_files` passed)

### Cause #2 — Status vocabulary mismatch

- **File**: `scripts/little_loops/issue_lifecycle.py`
- **Anchor**: `is_issue_completed_via_frontmatter` at line 400 —
  `if status in ("done", "cancelled"):`
- **Cause**: Only `done` and `cancelled` are accepted as completed-status
  values, but `completed` is plausible drift: the word "completed" appears
  throughout user-facing copy, in other schemas (`generate_schemas.py:400`),
  and is a natural mistake for the agent to make. ENH-1533's frontmatter as
  written by the agent had `status: completed`, triggering the first warning
  and forcing the fallback path into bug #1 above.

## Steps to Reproduce

1. Pick an issue where `/ll:manage-issue` will commit mid-Phase-2 (the
   default behaviour per `skills/manage-issue/SKILL.md`).
2. Optionally arrange for the agent to write `status: completed` in the
   issue frontmatter (drift from canonical `done`).
3. Run `ll-auto --only <ISSUE-ID> -v`.
4. Observe Phase 3 logs:
   - `Warning: <ID> status=completed (expected done/cancelled)`
   - `REFUSING to mark <ID> as completed: no code changes detected despite returncode 0`
5. Confirm the agent's commit is present on the branch and contains real
   code changes — the verification was a false negative.

## Proposed Solution

Two narrow, surgical changes in existing files — no new abstractions.

### Fix A — Teach `verify_work_was_done` about commits

In `scripts/little_loops/work_verification.py`:

- Add a `baseline_sha: str | None = None` parameter to
  `verify_work_was_done()`.
- After the existing uncommitted/staged checks (and before the "no files
  modified" warning), when `baseline_sha` is provided and differs from
  `HEAD`, run `git diff --name-only <baseline_sha>..HEAD`, filter via
  `filter_excluded_files`, and treat a non-empty result as evidence of work.
- Keep existing checks first so behaviour is unchanged for callers that
  don't pass a baseline.

In `scripts/little_loops/issue_manager.py`:

- Capture `git rev-parse HEAD` before Phase 2 starts.
- Pass it to the `verify_work_was_done(logger, baseline_sha=...)` call at
  line 890.
- `worker_pool.py` (ll-parallel) already passes `changed_files` explicitly,
  so it needs no change.

### Fix B — Accept `completed` as an alias for `done`

In `scripts/little_loops/issue_lifecycle.py:400`:

- Change to `if status in ("done", "completed", "cancelled"):`.
- Optionally log an info note when `status == "completed"` is observed, so
  drift remains visible.
- Canonical value written by `complete_issue_lifecycle` stays `done`. Do
  **not** change what `skills/manage-issue/SKILL.md` tells the agent to
  write — `done` remains canonical; this is defence-in-depth.

## Implementation Steps

1. Add `baseline_sha` parameter + commit-range check to `verify_work_was_done`.
2. Capture HEAD before Phase 2 in `issue_manager.py`; pass into the call.
3. Widen the `is_issue_completed_via_frontmatter` status whitelist.
4. Add tests (see below).
5. Run full test suite + lint + mypy.
6. Manual smoke: `ll-auto --only <test-issue> -v` against an issue where
   the agent commits mid-Phase-2; confirm Phase 3 passes.

## Tests to Add

`scripts/tests/test_work_verification.py` (extend or create):

- Returns True when only committed changes exist between `baseline_sha`
  and HEAD.
- Returns False when the only commit since baseline touches only excluded
  paths (`.issues/`, `thoughts/`, etc.).
- Returns True (unchanged) for uncommitted/staged cases.

`scripts/tests/test_issue_lifecycle.py` (extend):

- `is_issue_completed_via_frontmatter` returns True for `status: completed`.
- Still returns True for `done`/`cancelled` and False for `open`/`in_progress`.

## Acceptance Criteria

- `ll-auto` correctly marks an issue as completed when the agent commits
  the work mid-Phase-2 and exits with code 0.
- An issue file with `status: completed` in frontmatter is accepted as
  completed by Phase 3.
- Existing behaviour for uncommitted/staged changes is unchanged.
- New unit tests cover both fixes.
- `python -m pytest scripts/tests/`, `ruff check scripts/`, and
  `python -m mypy scripts/little_loops/` all pass.

## Critical Files to Modify

- `scripts/little_loops/work_verification.py` — add `baseline_sha` param + commit-range check
- `scripts/little_loops/issue_manager.py:890` — capture HEAD before Phase 2; pass into call
- `scripts/little_loops/issue_lifecycle.py:400` — accept `completed` as alias
- `scripts/tests/test_work_verification.py` — new tests
- `scripts/tests/test_issue_lifecycle.py` — new test

## Impact

- **Severity**: Medium (P2) — silent false negatives leave completed issues
  in `open` state, causing re-processing churn and masking real successes.
- **Frequency**: Recurs any time the agent commits mid-Phase-2 (the default
  per `manage-issue` SKILL.md) AND/OR writes `status: completed`. Likely
  affects a meaningful fraction of `ll-auto` runs.
- **User Impact**: Wasted re-runs; loss of trust in `ll-auto` verification;
  manual cleanup to flip frontmatter back to `done`.
- **Workaround**: Manually update frontmatter to `status: done` and move
  the issue, or re-run with the work already committed (still fails on the
  same path).
- **Breaking Change**: No.

## Related Issues

- [BUG-280](../bugs/P2-BUG-280-ll-auto-false-verification-failure-plan-approval.md) —
  Sibling false-negative bug for the "plan created, awaiting approval" case.
  Same Phase 3 verification surface; complementary fix.
- [BUG-1537](../bugs/P1-BUG-1537-implementation-failure-in-enh-1533.md) —
  Auto-captured failure record for ENH-1533. Was closed with the assumption
  that the cause was a context-window interruption; this bug supersedes
  that diagnosis with the actual root cause.
- [ENH-1533](../enhancements/P3-ENH-1533-codex-agent-selection-ux-and-prompt-injection.md) —
  The triggering issue. Already shipped successfully on commit `5b272e75`;
  no retry needed.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.claude/CLAUDE.md` | Documents `ll-auto`/`ll-parallel` CLI surface and verification expectations |
| `docs/reference/API.md` | Module reference for `little_loops` package (verification surface) |
| `skills/manage-issue/SKILL.md` | Documents the mid-Phase-2 commit behaviour that triggers the bug |

## Out of Scope

- ENH-1533 itself is already implemented and committed; no retry needed.
- Tightening the agent-side instruction in `skills/manage-issue/SKILL.md`
  to be more emphatic about `done` vs `completed` is a worthwhile small
  follow-up but is optional once Fix B lands.

## Labels

`bug`, `ll-auto`, `verification`, `false-negative`, `phase-3`

---

## Verification Notes

**Verdict**: VALID — Verified 2026-05-17

- `scripts/little_loops/work_verification.py:44` — `def verify_work_was_done(logger, changed_files=None)` confirmed; no `baseline_sha` parameter ✓
- `scripts/little_loops/issue_manager.py:890` — `work_done = verify_work_was_done(logger)` with no `changed_files` passed ✓
- `scripts/little_loops/issue_lifecycle.py:400` — `if status in ("done", "cancelled"):` confirmed; `completed` not accepted ✓
- Bug not yet fixed.

## Status
**Open** | Created: 2026-05-17 | Priority: P2

## Session Log
- `/ll:verify-issues` - 2026-05-17T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:capture-issue` - 2026-05-17T02:15:49Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`
