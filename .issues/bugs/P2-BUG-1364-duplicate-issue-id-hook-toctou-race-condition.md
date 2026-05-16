---
captured_at: '2026-05-04T21:18:58Z'
completed_at: '2026-05-05T02:04:07Z'
discovered_date: '2026-05-04'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
missing_artifacts: true
status: done
---

# BUG-1364: check-duplicate-issue-id Hook TOCTOU Race Allows Parallel Writes of Same ID

## Summary

The `check-duplicate-issue-id.sh` PreToolUse hook has a time-of-check/time-of-use (TOCTOU) race condition. The advisory lock only guards concurrent executions of the `find` check itself — it cannot guard the window between the hook returning "allow" and the file actually being written by Claude Code. Two parallel `Write` calls for different filenames containing the same integer ID can both pass the duplicate check before either file lands on disk, resulting in silent duplicate issue IDs.

## Current Behavior

When two `capture-issue` calls execute in the same response turn (parallel tool calls or parallel agent spawns), both calls to `ll-issues next-id` return the same integer (e.g., 1362) because neither file has been written yet. Both Write hooks then run: each acquires the lock, runs `find`, finds no existing file with that integer, releases the lock, and returns "allow". Both files are then written with the same ID. The hook never fires a denial because neither file exists on disk during either hook execution.

## Expected Behavior

No two active issue files should ever have the same integer ID. A second Write for an ID that has already been allocated — whether the file is on disk or merely reserved — should be denied.

## Motivation

Silent ID collisions corrupt issue tracking: `ll-issues path`, `ll-issues show`, and any tool that resolves IDs by number will behave non-deterministically when two files match the same ID. The user has no indication anything went wrong until they notice the duplicate manually (as happened with ENH-1362). The hook exists specifically to prevent this, so the failure mode being silent is worse than no guard at all.

## Steps to Reproduce

1. Run two `/ll:capture-issue` commands in a single response turn (e.g., as parallel Agent calls or multi-tool calls)
2. Both calls execute `ll-issues next-id` before either Write fires — both receive the same integer
3. Both Write tools execute; both PreToolUse hooks pass (no file exists yet for either check)
4. Both issue files are written with identical ID integers but different type/name prefixes

## Root Cause

- **File**: `hooks/scripts/check-duplicate-issue-id.sh`
- **Anchor**: lock-acquire → find → lock-release → return-allow block (lines 98–129)
- **Cause**: The advisory lock (`acquire_lock` / `release_lock` in `lib/common.sh`) is held only during the `find` scan. Once the hook returns "allow", the lock is released and the file has not yet been written. A second concurrent hook can then acquire the lock, run `find` (finding nothing, because the first file isn't on disk yet), and also return "allow". The actual write happens after the hook process exits — outside the lock scope entirely.

## Proposed Solution

Three viable approaches, ordered by implementation simplicity:

**Option A — PostToolUse denial (simplest, reactive):** Add a PostToolUse Write hook that runs after the file is written. It checks if any other file in `.issues/` shares the same integer ID. If a duplicate is found, it deletes the just-written file and emits a clear error message. No cross-hook state needed; purely reactive.

> **Selected:** Option A — PostToolUse reactive deletion — cleanest codebase fit (11/12); one new script + one `hooks.json` entry, direct reuse of established PostToolUse patterns.

**Option B — Reservation sentinel (proactive, same hook):** Before returning "allow", the PreToolUse hook writes a zero-byte reservation file (e.g., `.issues/.reserve-1364`) under the same lock. The `find` scan is extended to also check for reservation sentinels. A cleanup step (PostToolUse or session cleanup) removes stale reservations after the write completes. More complex but prevents the duplicate from ever appearing on disk.

**Option C — Atomic ID allocation in `next-id` (most robust):** `ll-issues next-id` (`cmd_next_id` in `scripts/little_loops/cli/issues/next_id.py`) writes a reservation file (or atomically increments a counter) as a side effect of printing the next ID. No two calls to `next-id` can produce the same number regardless of hook timing. The hook becomes a secondary safety net. Requires changes to the Python CLI layer.

Option A is the lowest-risk change; Option C eliminates the root cause entirely.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-04.

**Selected**: Option A — PostToolUse reactive deletion

**Reasoning**: Option A maps directly onto two existing PostToolUse hook shapes — `context-monitor.sh` for the `exit 2`/stderr signaling convention and `issue-completion-log.sh` for the `matcher: "Bash"` → `matcher: "Write"` registration pattern — and reuses the already-written `tool_input.file_path` extraction from `check-duplicate-issue-id.sh` line 32. Option B inherits the fail-open lock-timeout bypass unchanged and introduces orphaned-reservation risk when a Write fails at the OS level (no `PostToolUseFailure` handler exists). Option C's `IssueParser._generate_id_from_filename()` fallback calls `get_next_issue_number()` during read-only parsing, which would spuriously create reservations on every `ll-issues list`, and the batch-increment pattern documented across five commands defeats atomicity regardless.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| Option C | 1/3 | 0/3 | 2/3 | 0/3 | 3/12 |

**Key evidence**:
- **Option A**: PostToolUse `matcher: "Write"` shape exists in `hooks.json` (parallel to `matcher: "Bash"` at lines 68–75); `tool_input.file_path` extraction already written at `check-duplicate-issue-id.sh:32`; `exit 2` + stderr convention confirmed in `context-monitor.sh:360–370`; `TestIssueCompletionLog` fixture pattern applies directly.
- **Option B**: All lock utilities reusable but `session-cleanup.sh` needs new `jq` call for `issues.base_dir`; fail-open bypass (lines 98–102) is inherited; `PostToolUseFailure` gap leaves orphaned reservations on failed Writes.
- **Option C**: `IssueParser._generate_id_from_filename()` calls `get_next_issue_number()` in read-only parsing (spurious reservation risk); `create_issue_from_failure()` and `GitHubSyncManager._create_local_issue()` bypass hooks entirely; batch-increment pattern in 5 commands/2 skills defeats atomicity guarantee.

## Integration Map

### Files to Modify
- `hooks/scripts/check-duplicate-issue-id-post.sh` — **NEW FILE (Option A)**: PostToolUse reactive deletion script; receives `tool_input.file_path` on stdin, finds same-integer duplicate already on disk in `.issues/`, deletes the just-written duplicate, emits `exit 2` + stderr feedback; source `hooks/scripts/lib/common.sh` for lock utilities [Wiring pass 2]
- `hooks/scripts/check-duplicate-issue-id.sh` — extend duplicate check or add reservation write (Options A/B)
- `scripts/little_loops/cli/issues/next_id.py` — atomic reservation logic (Option C only)
- `scripts/little_loops/cli/issues/` — `get_next_issue_number` in `issue_parser.py` (Option C only)

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — wires `check-duplicate-issue-id.sh` as PreToolUse on `Write|Edit`
- `hooks/scripts/lib/common.sh` — provides `acquire_lock` / `release_lock` used by the hook

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_lifecycle.py` — calls `get_next_issue_number()` in `create_failure_bug_issue()` — **bypasses all hooks** (writes files via `atomic_write` directly, no `Write` tool); Option C reservation side effects will leak here unless guarded [Agent 1 + 2 finding]
- `scripts/little_loops/sync.py` — calls `get_next_issue_number()` in `GitHubSync` (~line 638) — same bypass concern as `issue_lifecycle.py`; sync writes files directly through Python [Agent 1 + 2 finding]
- `scripts/little_loops/issue_parser.py` — `IssueParser._extract_issue_id()` calls `get_next_issue_number()` as a fallback during **read-only** parsing; if Option C adds a reservation side effect, `ll-issues list`, `ll-issues show`, and any command that constructs an `IssueParser` would spuriously create reservations [Agent 2 finding — critical for Option C]
- `scripts/little_loops/cli/issues/__init__.py` — dispatches to `cmd_next_id()` subcommand [Agent 1 finding]
- `skills/capture-issue/SKILL.md` — "Action: Create New Issue" section calls `ll-issues next-id` then Write; under Option A, Write returns success (from the skill's perspective) but the PostToolUse hook then deletes the file and emits `exit 2` feedback; the skill has **no retry logic** for this case and will hold a reference to a filename that no longer exists — review whether a fallback or note is needed [Wiring pass 2 — behavioral contract change]

### Similar Patterns
- `hooks/scripts/lib/common.sh` `acquire_lock` — same locking pattern used elsewhere; fix should stay consistent
- Completed `P4-BUG-423-lock-file-race-condition-in-fsm-concurrency.md` — similar TOCTOU fix in FSM layer (reference for how prior race was resolved)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/concurrency.py:LockManager.acquire()` (lines 114–142) — **exact pattern for Option C**: holds `.acquire.lock` sentinel via `fcntl.flock(LOCK_EX)` while computing max ID + writing reservation file; sentinel is a dotfile so `Path.glob("*.lock")` skips it during conflict scans
- `scripts/little_loops/file_utils.py:atomic_write()` (lines 10–26) — reusable atomic write utility (`tempfile.mkstemp + os.replace`) for writing reservation file in Option C
- `hooks/scripts/lib/common.sh:atomic_write_json()` (lines 59–85) — bash-side temp-file+mv pattern; reuse in Option B's reservation sentinel write
- `hooks/scripts/check-duplicate-issue-id.sh` (lines 95–117) — TOCTOU window confirmed: lock released at line 117, `allow_response` at line 129, file write happens after hook process exits; comment on line 96 acknowledges the limitation explicitly
- PostToolUse hook constraint: PostToolUse hooks **cannot deny** tool calls. Option A works as reactive cleanup — hook receives `tool_input.file_path` on stdin, runs `rm "$file_path"` on duplicate detected, emits feedback via `exit 2` + stderr. This is not a denial but a reactive deletion; Claude sees the feedback.
- `hooks/scripts/check-duplicate-issue-id.sh` has a **fail-open** on lock timeout (lines 99–102): if `acquire_lock` times out, it calls `allow_response` unconditionally — a secondary bypass vector unrelated to the TOCTOU window

### Tests
- `scripts/tests/test_issues_cli.py` — `TestIssuesCLINextId` class (lines 14–57); existing tests: `test_next_id_empty_project`, `test_next_id_with_existing_issues`; if Option C, add a concurrency test asserting two parallel `next-id` calls never return the same integer
- `scripts/tests/test_hooks_integration.py` — `TestDuplicateIssueId` class (lines 999–1100+); existing hook integration tests using `ThreadPoolExecutor`; add concurrent Write test for new PostToolUse or reservation-check behavior
- `scripts/tests/test_concurrency.py` — `TestLockManagerRaceConditions`; `threading.Barrier(2)` pattern for exactly-one-wins concurrency tests (model for Option C's concurrent `next-id` test)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py` — `TestGetNextIssueNumber` (lines 761–883); 6 serial unit tests for `get_next_issue_number()`; all will break if the function signature changes (Option C); **add a concurrent variant** using `threading.Barrier(2)` (mirror `TestLockManagerRaceConditions.test_concurrent_acquire_same_scope_only_one_wins` at line 333 in `test_concurrency.py`) asserting all N returned integers are distinct [Agent 3 finding — existing tests to update + new concurrent test]
- `scripts/tests/test_hooks_integration.py` — `TestDuplicateIssueId.test_concurrent_duplicate_detection` (line 1007): the `allowed_count >= 1` assertion on new-ID concurrent block has no upper bound; tighten to `allowed_count == 1` to actually catch the TOCTOU failure mode [Agent 3 finding — update]
- `scripts/tests/test_hooks_integration.py` — add new `TestDuplicateIssueIdPost` class for Option A's `check-duplicate-issue-id-post.sh`; follow the `TestIssueCompletionLog` pattern (hook_script fixture + `subprocess.run` + `"tool_name": "Write"` input JSON); assert duplicate file is removed and `exit 2` stderr feedback is emitted [Agent 3 finding — new test]
- Missing: **subprocess-level integration test** for `ll-issues next-id` CLI binary — zero such tests exist anywhere; add to `TestIssuesCLINextId` using `subprocess.run(["ll-issues", "next-id", ...])` to catch CLI entry-point regressions [Agent 3 finding — new test]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — update `hooks/scripts/` directory listing if Option A adds `check-duplicate-issue-id-post.sh` [Agent 2 finding]
- `docs/reference/API.md` — `get_next_issue_number` section documents return value; update if Option C adds reservation side effects (current documented signature already inaccurate: shows `category: str` but actual is `str | None = None`) [Agent 2 finding]
- `docs/reference/CLI.md` — `ll-issues next-id` / `ll-issues ni` description says "Print the next globally unique issue number"; update if Option C adds observable side effects [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — three areas need updating for Option A: (1) chmod list block (`chmod +x hooks/scripts/check-duplicate-issue-id.sh`) add new script name; (2) "Testing individual hooks" manual test invocations don't cover new PostToolUse hook; (3) lock timeout table listing `check-duplicate-issue-id.sh: 3s timeout` is incomplete if new PostToolUse script has a different timeout [Agent 2 finding]
- `commands/scan-codebase.md` — step 5 "Assign globally unique sequential numbers" instructs `ll-issues next-id` once then batch-increment manually (`If ll-issues next-id prints 011, assign 011, 012, 013`); **this pattern defeats Option C's atomicity guarantee** — must be updated to call `ll-issues next-id` once per issue [Agent 2 finding — command coupling]
- `commands/scan-product.md` — step 4: same batch-increment pattern; same conflict with Option C [Agent 2 finding — command coupling]
- `skills/configure/areas.md` — hook configuration table shows `[Plugin] PreToolUse Write|Edit check-duplicate-issue-id.sh 5s`; add PostToolUse row for Option A's new hook [Agent 2 finding]
- `skills/analyze-loop/SKILL.md` — section "6a. Allocate ID" note: *"Do not batch-allocate IDs upfront, as concurrent writes could produce collisions"* — only mention of collision risk in skills/commands; under Option C the causal mechanism changes from hook timing to reservation-file atomicity; update note [Agent 2 finding]
- `CHANGELOG.md` — add BUG-1364 entry in the active release section for the new `check-duplicate-issue-id-post.sh` script; template at line 831 (`check-duplicate-issue-id.sh config resolution — ENH-871`) in the `[1.61.2]` section [Wiring pass 2]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/hooks.json` — add `PostToolUse` array entry with `matcher: "Write"` for Option A's `check-duplicate-issue-id-post.sh`; timeout must satisfy the `test_lock_timeout_leaves_adequate_margin()` policy in `TestContextMonitorLockTimeout` (PostToolUse hooks use 5s overall timeout) [Agent 2 finding]
- `hooks/scripts/session-cleanup.sh` — `cleanup()` function currently sweeps `.ll/.ll-lock`, `ll-context-state.json`, `.loops/tmp/scratch/` but has no knowledge of `.issues/.reserve-*`; Options B/C require adding a `rm -f "${ISSUES_BASE_DIR}"/.reserve-* 2>/dev/null || true` sweep; `session-cleanup.sh` currently does not read `issues.base_dir` from config (only reads `parallel.worktree_base` via `jq`), so adding reservation cleanup requires a new `jq` call [Agent 2 finding]

## Implementation Steps

1. Choose fix approach (A, B, or C) based on risk tolerance and desired robustness
2. Implement the chosen approach in the identified files
3. Manually verify: run two parallel capture-issue calls and confirm the second is denied (or the duplicate is removed)
4. For Option C: add a concurrency test in `test_issues_cli.py` asserting unique IDs under parallel invocation

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete steps per option:_

**Option A (PostToolUse reactive deletion):**
1. Add new script `hooks/scripts/check-duplicate-issue-id-post.sh`; parse `tool_input.file_path` from stdin; run `find .issues -name "*.md"` for same integer; if duplicate found: `rm "$tool_input.file_path"` + `exit 2` with stderr feedback
2. Register in `hooks/hooks.json` under `PostToolUse` with `matcher: "Write"` (follow shape of existing PostToolUse hooks at lines 53–75)
3. Test: add case to `test_hooks_integration.py:TestDuplicateIssueId` asserting the duplicate file is removed and feedback is emitted

**Option B (Reservation sentinel in PreToolUse):**
1. Extend `check-duplicate-issue-id.sh` (lines 95–117): after `find` check, write `.reserve-{ISSUE_NUM}` under the same lock using `atomic_write_json` from `common.sh`; extend `find` pattern to also match `.reserve-*` files
2. Add cleanup in `session-cleanup.sh` (Stop hook) to remove stale `.reserve-*` files
3. Test: concurrent hook invocation via `ThreadPoolExecutor` in `test_hooks_integration.py`

**Option C (Atomic ID in `next_id.py`):**
1. In `scripts/little_loops/cli/issues/next_id.py:cmd_next_id()` (line 20): after `get_next_issue_number()`, acquire `fcntl.flock(LOCK_EX)` on `.issues/.id-reserve.lock` (mirror `fsm/concurrency.py:LockManager.acquire()` lines 114–142); write `.issues/.reserve-{num}` using `file_utils.atomic_write()`; print and exit
2. Extend `check-duplicate-issue-id.sh` `find` to also match `.reserve-*` files; add PostToolUse cleanup to remove `.reserve-{num}` after successful write
3. Test: `threading.Barrier(2)` pattern (from `test_concurrency.py:TestLockManagerRaceConditions`) in `TestIssuesCLINextId` asserting no two concurrent `next-id` calls return the same integer

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. **Guard `IssueParser._extract_issue_id()` fallback** (Option C critical) — `scripts/little_loops/issue_parser.py`: the `_extract_issue_id()` fallback calls `get_next_issue_number()` during read-only parsing operations; if Option C adds a reservation side effect, isolate the side effect so it only fires when called from `cmd_next_id()` — not from the parser fallback path
6. **Guard automation bypass callers** (Option C critical) — `scripts/little_loops/issue_lifecycle.py:create_failure_bug_issue()` and `scripts/little_loops/sync.py:GitHubSync` call `get_next_issue_number()` directly and write files via Python's `atomic_write`, bypassing all hooks; if Option C's reservation file is only cleaned up by a PostToolUse hook, these callers will leak reservations permanently; implement explicit cleanup in each caller or make reservation cleanup unconditional in the Python allocation path
7. **Add PostToolUse hook registration** (Option A) — `hooks/hooks.json`: add new `PostToolUse` entry with `matcher: "Write"` for `check-duplicate-issue-id-post.sh`; script must exist at `hooks/scripts/check-duplicate-issue-id-post.sh`
8. **Update session cleanup** (Options B/C) — `hooks/scripts/session-cleanup.sh:cleanup()`: add `rm -f "${ISSUES_BASE_DIR}"/.reserve-* 2>/dev/null || true`; add a `jq` call to read `issues.base_dir` from config (currently only `parallel.worktree_base` is read)
9. **Update commands to not batch-increment** (Option C) — `commands/scan-codebase.md` step 5 and `commands/scan-product.md` step 4: remove the "increment manually for subsequent issues" instruction; call `ll-issues next-id` once per issue instead
10. **Update docs** — `docs/development/TROUBLESHOOTING.md`: add new hook script to chmod list and timeout table; `docs/reference/API.md`: update `get_next_issue_number` description if Option C adds side effects; `docs/ARCHITECTURE.md`: add new script to file listing; `skills/configure/areas.md`: add PostToolUse row to hook table (Option A)
11. **Add and update tests** — `test_issue_parser.py:TestGetNextIssueNumber`: add concurrent `threading.Barrier(2)` variant; `test_hooks_integration.py:TestDuplicateIssueId.test_concurrent_duplicate_detection`: tighten `allowed_count >= 1` to `allowed_count == 1`; add `TestDuplicateIssueIdPost` class for Option A; add subprocess-level CLI integration test for `ll-issues next-id`
12. **Update CHANGELOG** — add BUG-1364 entry in active release section for the new `check-duplicate-issue-id-post.sh` hook; follow the `[1.61.2]` entry template at line 831 [Wiring pass 2]
13. **Review `skills/capture-issue/SKILL.md`** — the "Action: Create New Issue" section assumes Write denial = file never written; under Option A, Write returns success and the file is deleted reactively by the PostToolUse hook; consider adding a fallback note for the case where `ll-issues show <ID>` returns not-found after a successful Write [Wiring pass 2]

## Impact

- **Priority**: P2 - Silently corrupts issue tracking; user has no indication of failure
- **Effort**: Small — Option A (PostToolUse hook) is a single new hook script; Options B/C require moderate changes
- **Risk**: Low — additive change; existing single-capture flow is unaffected
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `captured`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-04_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- **Documentation breadth**: 5 separate markdown touchpoints across different directories (`docs/ARCHITECTURE.md`, `docs/development/TROUBLESHOOTING.md`, `skills/configure/areas.md`, `CHANGELOG.md`, `skills/capture-issue/SKILL.md`); easy to miss one — use the wiring step list in Implementation Steps as a checklist
- **Behavioral contract change in `capture-issue/SKILL.md`**: under Option A, Write returns success but the PostToolUse hook deletes the file reactively; the skill has no retry or verification step for this case — a judgment call is needed during implementation about whether to add a fallback note

## Resolution

**Fixed**: Added `hooks/scripts/check-duplicate-issue-id-post.sh` — a PostToolUse Write hook that closes the TOCTOU window. After each Write to `.issues/`, it checks whether the written file shares an integer ID with any other existing issue file. If a duplicate is found, it deletes the just-written file and emits `exit 2` + stderr feedback so Claude retries with a fresh `ll-issues next-id` call.

**Changes**:
- `hooks/scripts/check-duplicate-issue-id-post.sh` — new PostToolUse reactive deletion script
- `hooks/hooks.json` — registered new hook under PostToolUse with `matcher: "Write"`
- `scripts/tests/test_hooks_integration.py` — added `TestDuplicateIssueIdPost` class (5 tests)
- `docs/development/TROUBLESHOOTING.md` — added chmod entry, timeout note, manual test example
- `skills/configure/areas.md` — added PostToolUse row to hook table
- `docs/ARCHITECTURE.md` — added new script to file listing
- `CHANGELOG.md` — added BUG-1364 entry

## Session Log
- `/ll:ready-issue` - 2026-05-05T01:55:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3d013c1-645d-4dcb-b9b0-5effe57c6af1.jsonl`
- `/ll:confidence-check` - 2026-05-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/58200d4c-562e-45dd-8a37-1a29fb4ae944.jsonl`
- `/ll:wire-issue` - 2026-05-05T01:25:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7507e7a-bb19-409b-8997-56185af003f7.jsonl`
- `/ll:decide-issue` - 2026-05-04T22:31:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29bd4285-4b66-4516-9a50-d8c4c54bfccd.jsonl`
- `/ll:confidence-check` - 2026-05-04T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4377bf38-5e53-41bd-bae1-edc23c1b8522.jsonl`
- `/ll:wire-issue` - 2026-05-04T21:33:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2bc48b55-0540-478c-b109-29f7f7c933b0.jsonl`
- `/ll:refine-issue` - 2026-05-04T21:26:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/289fb78c-42f6-4df9-804f-3ef779fdb9e6.jsonl`
- `/ll:format-issue` - 2026-05-04T21:21:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d93e27d3-ea1a-4ac4-81bc-0e9f03d4c459.jsonl`

- `/ll:capture-issue` - 2026-05-04T21:18:58Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aab68ee6-680b-4a10-8059-543473bf25b4.jsonl`

---

**Open** | Created: 2026-05-04 | Priority: P2
