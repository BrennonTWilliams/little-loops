---
captured_at: '2026-05-17T02:15:49Z'
completed_at: '2026-05-17T22:54:30Z'
discovered_date: 2026-05-17
discovered_by: capture-issue
status: done
priority: P2
type: BUG
relates_to:
- BUG-280
- BUG-1537
- ENH-1533
confidence_score: 96
outcome_confidence: 77
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 25
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

## Integration Map

### Files to Modify
- `scripts/little_loops/work_verification.py` — add `baseline_sha: str | None = None` parameter + commit-range check to `verify_work_was_done()` (Fix A)
- `scripts/little_loops/issue_manager.py` — (Fix A) capture HEAD before Phase 2 at line 742 and pass into call at line 890; (Fix B) update `already_done` guard at line 790 (`_fm.get("status") in ("done", "cancelled")`) to also accept `"completed"`
- `scripts/little_loops/issue_lifecycle.py` — widen `verify_issue_completed` acceptance set at line 400 (Fix B)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/git_operations.py` — re-exports `verify_work_was_done` and `filter_excluded_files` via `# noqa: F401`; callers importing from here will pick up the new signature automatically without additional changes
- `scripts/little_loops/parallel/worker_pool.py` — calls `verify_work_was_done(self.logger, changed_files)` at line 966 (Path A); already commit-aware via `_get_changed_files()` — no change needed

### Similar Patterns
- `scripts/little_loops/parallel/worker_pool.py:1207` — `_get_main_head_sha()` uses `["rev-parse", "HEAD"]` via `_git_lock.run()`; analogous bare `subprocess.run` pattern used in `issue_manager.py`
- `scripts/little_loops/parallel/worker_pool.py:1222` — `_detect_committed_leaks(baseline_head_sha)` captures HEAD before Phase 2 equivalent and diffs against it afterwards — direct parallel to the Fix A approach

### Tests
- `scripts/tests/test_work_verification.py` — existing comprehensive tests; multi-call `side_effect` mock at lines 256–263; command assertion pattern at lines 328–330 (`calls[N][0][0] == ["git", "diff", "--name-only"]`). New test adds a third entry: `calls[2][0][0] == ["git", "diff", "--name-only", f"{baseline_sha}..HEAD"]`
- `scripts/tests/test_issue_lifecycle.py:369` — `test_status_completed_synonym_verified` already written as a pending/failing test asserting `status: completed` returns `True`; Fix B should make it pass
- `scripts/tests/test_worker_pool.py:1395` — `test_get_main_head_sha_returns_sha` shows rev-parse HEAD mock pattern to follow

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_manager.py` — needs 2 new tests in existing test classes:
  - `test_early_completion_guard_accepts_completed_status` (in `TestEarlyCompletionGuard`): write `status: completed` to issue file, have Phase 2 exit non-zero, verify the `already_done` guard at line 790 fires and `result.success` is True — this is the Fix B second location and currently has zero test coverage
  - `test_baseline_sha_passed_to_verify_work_was_done` (in `TestFallbackVerification`): patch `subprocess.run` to return a SHA on `git rev-parse HEAD`, then use `assert_called_with` to verify `verify_work_was_done` was called with `baseline_sha=<that SHA>` — validates the Fix A plumbing end-to-end

### Configuration
- `scripts/little_loops/config/automation.py` — `require_code_changes` setting consumed by verification; no change needed but relevant to understanding the fallback logic

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Fix B may be simpler than described**: `scripts/little_loops/frontmatter.py` already contains `STATUS_SYNONYMS = {"completed": "done", ...}` applied at the end of every `parse_frontmatter()` call. If `verify_issue_completed` uses `parse_frontmatter()` (confirmed: lines 393–397), the coercion may already normalize `"completed"` → `"done"` before the acceptance check at line 400. The existing failing test `test_issue_lifecycle.py:369` will clarify whether the normalization path is actually reached. **Either way, the `already_done` guard at `issue_manager.py:790` is a second fix location** that reads frontmatter independently and must also be widened.
- **`already_done` guard (second Fix B location not in original issue)**: `issue_manager.py:790` — `already_done = _fm.get("status") in ("done", "cancelled")` — this guard runs when Phase 2 exits with non-zero returncode. If the agent wrote `status: completed` and exited non-zero, this guard also rejects the issue. The issue's "Critical Files to Modify" lists `issue_lifecycle.py:400` but omits this second location.
- **Phase 2 start anchor confirmed**: `issue_manager.py:742` — `timed_phase(logger, "Phase 2 (implement)")` — baseline SHA (`git rev-parse HEAD`) should be captured just before this line. Phase 3 starts at line 847 (`timed_phase(logger, "Phase 3 (verify)")`); `verify_work_was_done(logger)` call is at line 890.
- **Subprocess convention in `issue_manager.py`**: bare `subprocess.run(["git", ...], capture_output=True, text=True)` — consistent with existing calls in `cli/parallel.py` and `cli/sprint/run.py`. Do not use `_git_lock` (that is the `worker_pool.py`-only convention).

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

1. **`work_verification.py`**: Add `baseline_sha: str | None = None` parameter to `verify_work_was_done()`; after the existing uncommitted/staged checks, when `baseline_sha` is provided and differs from current HEAD, run `subprocess.run(["git", "diff", "--name-only", f"{baseline_sha}..HEAD"], capture_output=True, text=True)`, pass result through `filter_excluded_files`, return `True` if non-empty.
2. **`issue_manager.py`** (Fix A): Capture `baseline_sha` with `subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)` just before `timed_phase(logger, "Phase 2 (implement)")` at line 742; pass `baseline_sha=baseline_sha` to `verify_work_was_done(logger, ...)` at line 890.
3. **`issue_lifecycle.py`** (Fix B): Widen acceptance set at line 400; if `STATUS_SYNONYMS` normalization already covers it (confirmed by test at `test_issue_lifecycle.py:369`), the fix may be a no-op there — verify by running that test first.
4. **`issue_manager.py`** (Fix B): Widen `already_done` guard at line 790 from `("done", "cancelled")` to `("done", "completed", "cancelled")` — this is independent of `parse_frontmatter` normalization and must be updated regardless.
5. Add tests (see below).
6. Run full test suite + lint + mypy.
7. Manual smoke: `ll-auto --only <test-issue> -v` against an issue where the agent commits mid-Phase-2; confirm Phase 3 passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Add `test_early_completion_guard_accepts_completed_status` to `scripts/tests/test_issue_manager.py` (`TestEarlyCompletionGuard` class) — tests Fix B second location (`already_done` guard at line 790 accepting `status: completed`); no existing test covers this path
9. Add `test_baseline_sha_passed_to_verify_work_was_done` to `scripts/tests/test_issue_manager.py` (`TestFallbackVerification` class) — patches `subprocess.run` returning a SHA for `git rev-parse HEAD`, asserts `verify_work_was_done` is called with `baseline_sha=<sha>`; validates Fix A plumbing
10. Update `docs/reference/API.md` — add `baseline_sha: str | None = None` to the `### verify_work_was_done` signature block and update the description to mention the third detection mode (commit-range via `git diff --name-only <baseline_sha>..HEAD`)

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
- `scripts/little_loops/issue_manager.py:742` — capture HEAD just before Phase 2 start
- `scripts/little_loops/issue_manager.py:790` — widen `already_done` guard (Fix B, second location)
- `scripts/little_loops/issue_manager.py:890` — pass `baseline_sha` into `verify_work_was_done` call
- `scripts/little_loops/issue_lifecycle.py:400` — accept `completed` as alias (verify if `STATUS_SYNONYMS` normalization already handles it via `parse_frontmatter`)
- `scripts/tests/test_work_verification.py` — new tests (3-call side_effect mock pattern)
- `scripts/tests/test_issue_lifecycle.py:369` — `test_status_completed_synonym_verified` already exists; make it pass

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
- `/ll:ready-issue` - 2026-05-17T22:47:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7226416-47d7-4f0e-897f-438926cc588a.jsonl`
- `/ll:ready-issue` - 2026-05-17T22:46:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7226416-47d7-4f0e-897f-438926cc588a.jsonl`
- `/ll:confidence-check` - 2026-05-17T23:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef5a5d99-4dff-4fea-b505-2affae0a38ac.jsonl`
- `/ll:wire-issue` - 2026-05-17T22:42:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/957b050b-c6dc-4a57-81e5-28e4f20608d2.jsonl`
- `/ll:refine-issue` - 2026-05-17T22:36:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/741b329e-fbc3-4589-a153-a74b0ac2847a.jsonl`
- `/ll:verify-issues` - 2026-05-17T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:capture-issue` - 2026-05-17T02:15:49Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`
