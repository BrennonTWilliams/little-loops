---
id: BUG-3702
type: BUG
title: refine_followup evidence-delta snapshot vanishes from shared scratch dir mid-state
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T19:59:15Z'
parent: EPIC-3694
---

# BUG-3702: refine_followup evidence-delta snapshot vanishes from shared scratch dir mid-state

## Summary

During `refine-to-ready-issue` run `refine-to-ready-issue-20261002T111524`, `refine_followup`'s evidence delta check was incomplete because the snapshot `ll-verify-evidence --save-snapshot` wrote under `.loops/tmp/scratch/` vanished mid-state. Root cause is confirmed: the snapshot's filename embeds the pid of the short-lived CLI process, which makes it eligible for the `SessionStart` scratch-cleanup prune the moment any other session starts.

## Current Behavior

The delta check (`commands/refine-issue.md` Step 3.9 `--save-snapshot`, later `--delta-from "$SNAPSHOT_PATH"`) compares a pre-edit snapshot to post-edit evidence. The snapshot file disappeared while the refine pass was still running, so the comparison could not complete and the check degraded to "incomplete verification".

## Root Cause

Confirmed 2026-10-02 (code read plus on-disk check):

- `scripts/little_loops/cli/verify_evidence.py:write_snapshot` allocates `root / SNAPSHOT_DIR / f"evidence-snapshot-{uuid.uuid4()}-{os.getpid()}.json"` where `SNAPSHOT_DIR = .loops/tmp/scratch`. The pid is the `ll-verify-evidence` process, which exits immediately after writing. The docstring states the `-<pid>` suffix "makes an allocated file eligible for the `SessionStart` scratch-cleanup prune".
- `hooks/scripts/scratch-cleanup.sh` (SessionStart, BUG-2420/BUG-2525/BUG-3363) extracts a trailing `-<digits>.<ext>` as a pid, skips files whose pid is alive (`kill -0`), and `rm -f`s the rest. The CLI's pid is always dead by then, so **any** session start in the same checkout deletes a snapshot that a long refine pass still needs.
- Aggravating factor: the sweep is bounded by a 5s hook timeout (`hooks/hooks.json`) and `.loops/tmp/scratch` held 5,143 files at review time, so the sweep is often killed part-way through the directory. That makes the loss intermittent (it depends on where the name sorts) and hid the cause. The starvation itself is tracked as BUG-3705.
- Not a factor: `${context.run_dir}` isolation. `/ll:refine-issue` is a command that also runs outside loops, and the CLI (not the loop) allocates the path, so `run_dir` is unreachable at allocation time.

## Expected Behavior

An allocated evidence snapshot survives for the whole refine pass regardless of other sessions starting or concurrent runs, and old snapshots are still garbage-collected so the directory does not grow unbounded.

## Motivation

A snapshot used by a correctness check must not be deletable by unrelated hooks or concurrent runs. Without it, `refine-issue` reports verification as incomplete, which can mask newly introduced unverified quotes.

## Proposed Solution

- Default allocation moves to a dedicated, unswept directory: `.loops/tmp/evidence-snapshots/evidence-snapshot-<uuid4>.json` (no `-<pid>` suffix, outside `scratch-cleanup.sh`'s remit). Keep the atomic write and the explicit `--save-snapshot PATH` form unchanged.
- Add age-based GC (about 7 days) of that directory on allocation so it stays bounded; failures in GC must not fail the snapshot write.
- Rejected: keeping the file in `scratch/` with an unmatchable name. It would escape the pid sweep but then leak forever under the BUG-2525 contract (the hook preserves files without a `-<pid>` suffix), and a uuid4 whose last 12-hex group is all digits (~0.4%) would still match the hook's regex.
- Rejected: exporting an `LL_RUN_DIR` for loop runs to place snapshots in `run_dir`. Extra plumbing for a path the unswept dir plus GC already protects.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/verify_evidence.py` — `SNAPSHOT_DIR`, `write_snapshot` (allocation name/dir, docstring, GC)
- `commands/refine-issue.md` — Step 3.9 wording only if it names the scratch location (it currently says "do not build a path")
- `docs/reference/CLI.md` — `ll-verify-evidence` `--save-snapshot` section if it states where the snapshot lands

### Tests
- `scripts/tests/test_verify_evidence.py:1147-1149` — currently pins `p.parent == .loops/tmp/scratch` and `p.name.endswith(f"-{os.getpid()}.json")`, i.e. it pins the bug; flip it to assert the new dir and no `-<pid>` suffix
- New hook-level survival test: run `hooks/scripts/scratch-cleanup.sh` against a project containing an allocated snapshot and assert it survives; also assert the allocated name never matches the hook's `-([0-9]+)\.[^.]+$` extraction
- New GC test: snapshot older than the cutoff is pruned on the next allocation; a younger one and an explicit-`PATH` snapshot are not

## Implementation Steps

1. Change `SNAPSHOT_DIR` and the allocated name in `write_snapshot`; fix the docstring.
2. Add bounded age-based GC on allocation (never raises).
3. Update `test_verify_evidence.py:1147-1149`; add the hook-survival and GC tests.
4. Check `docs/reference/CLI.md` and `commands/refine-issue.md` for the old location; run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P3 - degrades a correctness check to "incomplete verification"; refine still completes
- **Effort**: Small - one constant/name change, a bounded GC, three tests
- **Risk**: Low - snapshot path is returned by the CLI and consumed opaquely; explicit `PATH` form unchanged
- **Breaking Change**: No

## Steps to Reproduce

1. Run `ll-verify-evidence <issue> --json --save-snapshot` and note the returned `snapshot_path` (`evidence-snapshot-<uuid>-<pid>.json`, pid already dead).
2. Start any new Claude session in the same checkout (runs `scratch-cleanup.sh`) — or run `bash hooks/scripts/scratch-cleanup.sh` directly.
3. Observe the snapshot is deleted, so a later `--delta-from <snapshot_path>` fails.

## Acceptance Criteria

- [ ] The root cause (pid-suffixed name + `scratch-cleanup.sh` dead-pid sweep) is recorded in the issue with the evidence above
- [ ] Allocated snapshots are written outside `.loops/tmp/scratch/` and carry no `-<pid>` suffix (asserted by the flipped `test_verify_evidence.py` test)
- [ ] A hook-level test shows `scratch-cleanup.sh` leaves an allocated snapshot in place
- [ ] Snapshots older than the GC cutoff are pruned on allocation without failing the write
- [ ] `python -m pytest scripts/tests/` exits 0

## Related

- Scratch-sweep starvation (5s hook timeout vs. thousands of dead-pid files) is a distinct defect: tracked as BUG-3705.
- Memory note: a fixed scratch name can also be clobbered by a concurrent run (not the cause here: names are uuid-unique).

## Status

**Open** | Created: 2026-10-02 | Priority: P3
