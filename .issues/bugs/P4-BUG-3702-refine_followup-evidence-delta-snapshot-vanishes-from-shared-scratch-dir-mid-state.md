---
id: BUG-3702
type: BUG
title: refine_followup evidence-delta snapshot vanishes from shared scratch dir mid-state
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T19:59:15Z'
parent: EPIC-3694
relates_to:
- BUG-3705
- BUG-3707
---

# BUG-3702: refine_followup evidence-delta snapshot vanishes from shared scratch dir mid-state

> **Re-scoped again 2026-10-03 (EPIC-3694 children review, Opus second opinion):** the "new test" is mostly already there. `test_scratch_cleanup_preserves_fresh_dead_pid_file` (generic fresh dead-pid file survives) and `test_scratch_cleanup_pid_parsing_matches_legacy_sed` (already has an `evidence-snapshot-<uuid>-<deadpid>.json` case, backdated 48h → swept) exist in `scripts/tests/test_hooks_integration.py`. Add a single `evidence-snapshot-…` fresh-survives case (or parametrize the existing fresh test) rather than a new test. ENH-3706 (`08c4dda9e`) also added a universal 7-day idle prune, so the `write_snapshot` docstring must state **both tiers** — dead-pid files after 24h idle, any file after 7 days idle — and that reading a snapshot does not refresh its mtime (a `--delta-from` run >24h after the save can lose it). Effort: ~10 minutes; do it with the next scratch-hook touch and close.

> **Re-scoped 2026-10-03 (pre-implementation review, Opus second opinion).** The original fix (move snapshots to an unswept `.loops/tmp/evidence-snapshots/` dir with its own 7-day GC) is **dropped**. BUG-3705 (commit `87d50cb02`) added a 24h mtime guard to `scratch-cleanup.sh`, so a fresh snapshot can no longer be swept during a refine pass, and that age sweep is already the GC this issue asked for. What remains is a regression test that pins the guard and a docstring fix; close once they land.

## Summary

During `refine-to-ready-issue` run `refine-to-ready-issue-20261002T111524`, `refine_followup`'s evidence delta check was incomplete because the snapshot `ll-verify-evidence --save-snapshot` wrote under `.loops/tmp/scratch/` vanished mid-state. Root cause (confirmed 2026-10-02): the snapshot's filename embeds the pid of the short-lived CLI process, making it eligible for the `SessionStart` scratch-cleanup prune the moment any other session started, and the sweep could reach it once BUG-3705's starvation allowed. **Status now:** fixed by BUG-3705's 24h age guard; remaining work is a pin test and a docstring correction.

## Current Behavior

`scripts/little_loops/cli/verify_evidence.py:write_snapshot` still allocates `root / SNAPSHOT_DIR / f"evidence-snapshot-{uuid.uuid4()}-{os.getpid()}.json"` (`SNAPSHOT_DIR = .loops/tmp/scratch`). `hooks/scripts/scratch-cleanup.sh` now only sweeps files untouched for `MIN_AGE_MINUTES=1440`, so a snapshot younger than 24h survives any number of session starts. The `write_snapshot` docstring still says the `-<pid>` suffix "makes an allocated file eligible for the `SessionStart` scratch-cleanup prune", which no longer describes the contract, and nothing pins that a snapshot younger than the guard survives, so lowering `MIN_AGE_MINUTES` would silently reintroduce the bug.

## Expected Behavior

An allocated evidence snapshot survives the whole refine pass regardless of other sessions starting, a test fails if the age guard is weakened enough to delete a recent snapshot, and the docstring states the real lifecycle (pruned once untouched for 24h).

## Root Cause

History (confirmed 2026-10-02): pid-suffixed name + `scratch-cleanup.sh` dead-pid sweep. The CLI's pid is always dead by the time any other session starts, and the sweep was starved by a 5s hook timeout over 5,143 files (BUG-3705), which made the loss intermittent. Resolved by `87d50cb02` (age guard + bounded sweep). Not a factor: `${context.run_dir}` isolation (`/ll:refine-issue` also runs outside loops, and the CLI allocates the path).

## Proposed Solution

- Add a hook-level test next to the BUG-3705 tests in `scripts/tests/test_hooks_integration.py` (helpers `_backdate`, `run_scratch_cleanup`, `_SCRATCH_DEAD_PID` already exist): an `evidence-snapshot-<uuid>-<deadpid>.json` younger than 24h survives `scratch-cleanup.sh`. Add the contrast case, the same file backdated past the guard (`_backdate`) is pruned, so the test is not vacuous.
- Fix the `write_snapshot` docstring: "eligible for prune" becomes a two-tier statement: pruned after 24h idle when the pid suffix is dead, and after 7 days idle regardless (ENH-3706); reading does not refresh mtime.
- Leave `scripts/tests/test_verify_evidence.py:1147-1149` as is: the pid suffix and scratch location are now intended.
- Rejected: moving to a dedicated unswept dir with a 7-day GC. It adds a second cleanup mechanism for a risk the age sweep already covers. Revisit only if `MIN_AGE_MINUTES` is expected to shrink below a refine pass's lifetime.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/verify_evidence.py` — `write_snapshot` docstring only
- `scripts/tests/test_hooks_integration.py` — new fresh-snapshot-survives / old-snapshot-pruned test (near the BUG-3705 scratch-cleanup tests)

### Tests
- `scripts/tests/test_verify_evidence.py:1147-1149` — currently pins `p.parent == .loops/tmp/scratch` and `p.name.endswith(f"-{os.getpid()}.json")`; unchanged

## Program Design

### Types

- `EvidenceSnapshot` — existing dataclass in `little_loops.cli.verify_evidence`; unchanged

### Signatures

- `write_snapshot(base_dir: Path, snapshot: EvidenceSnapshot, dest: Path | None) -> Path` — unchanged behavior; only the docstring changes

### Call Path

`main_verify_evidence` -> `write_snapshot` -> `atomic_write_json`; the returned `snapshot_path` is read back by the `--delta-from` run via `load_snapshot`

## Implementation Steps

1. Add the hook-level test (fresh snapshot survives, backdated one is pruned) using the existing `_backdate` / `run_scratch_cleanup` helpers.
2. Correct the `write_snapshot` docstring.
3. Run `python -m pytest scripts/tests/test_hooks_integration.py scripts/tests/test_verify_evidence.py`, then the full suite; close the issue.

## Impact

- **Priority**: P4 - the defect is fixed by BUG-3705; this is a pin test and doc fix
- **Effort**: Small - one test, one docstring
- **Risk**: Low - no behavior change
- **Breaking Change**: No

## Steps to Reproduce

1. (Pre-BUG-3705) Run `ll-verify-evidence <issue> --json --save-snapshot` and note `snapshot_path` (`evidence-snapshot-<uuid>-<pid>.json`, pid already dead).
2. Start any new Claude session in the same checkout, or run `bash hooks/scripts/scratch-cleanup.sh`.
3. The snapshot was deleted, so a later `--delta-from <snapshot_path>` failed. Post-BUG-3705 the file survives for 24h; the new test pins this.

## Acceptance Criteria

- [ ] A hook-level test shows `scratch-cleanup.sh` leaves a recent (<24h) `evidence-snapshot-<uuid>-<deadpid>.json` in place and prunes the same file once backdated past the guard
- [ ] The `write_snapshot` docstring describes the two-tier lifecycle (24h dead-pid guard, 7-day universal idle prune), not immediate prune eligibility
- [ ] `python -m pytest scripts/tests/` exits 0

## Related

- BUG-3705 (landed, `87d50cb02`): bounded sweep + 24h age guard; the actual fix.
- BUG-3707: runtime-pid naming for `scratch-pad-redirect.sh`; closed won't-fix after the same review.

## Status

**Open** | Created: 2026-10-02 | Priority: P4 | Re-scoped: 2026-10-03
