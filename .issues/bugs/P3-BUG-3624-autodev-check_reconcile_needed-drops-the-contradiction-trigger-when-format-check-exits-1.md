---
id: BUG-3624
type: BUG
title: Autodev check_reconcile_needed drops the contradiction trigger when format-check
  exits 1
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T01:48:54Z'
parent: EPIC-3565
relates_to:
- ENH-3623
- ENH-3621
---

# BUG-3624: Autodev check_reconcile_needed drops the contradiction trigger when format-check exits 1

## Summary

The contradiction-reconcile trigger (ENH-2992) in autodev's `check_reconcile_needed` never
fires for an issue that has any blocking format gap. The state captures the format-check
payload with an `|| echo '{}'` fallback, but `ll-issues format-check --format json`
prints its JSON payload *and* exits 1 when the issue has blocking gaps. The fallback
therefore appends a second JSON object, `json.loads` fails, and the state reads
`markers = 0`. Found by the ENH-3621 spike as quirk Q1 (report
`thoughts/spikes/preparation-policy-spike.md`, § Quirks and bugs found).

## Current Behavior

`scripts/little_loops/loops/autodev.yaml:2112` (state `check_reconcile_needed`, at
`2058`):

```bash
FMT_JSON=$(ll-issues format-check "$ID" --format json 2>/dev/null || echo '{}')
```

`little_loops.cli.issues.format_check` ends its single-issue JSON branch with
`print_json(payload)` followed by `return 1 if gaps.has_blocking_gaps else 0`. For an
issue with a blocking gap, such as a missing `## Impact` or `## Status`, the command
substitution therefore captures `"<payload>\n{}"`. The embedded Python runs
`json.loads(os.environ.get('LL_FORMAT_CHECK_JSON') or '{}')` inside a `try`, gets an
exception, and sets `markers = 0`. The ENH-2995 `⚠ Superseded` marker is ignored, and
`contradiction` is always false for such an issue.

The ENH-3618 characterization harness reproduces it. The spike's differential scenario
`contradiction_masked_by_format_gaps` puts a `⚠ Superseded` marker on an issue with
blocking gaps, and today's ladder never reconciles it.

## Expected Behavior

`check_reconcile_needed` reads `superseded_marker_count` from the format-check payload
whatever the command's exit code is. An issue with a standing contradiction marker arms
the contradiction-only reconcile (within the per-pass cap of 2), whether or not it also
has blocking format gaps. Only an empty capture (the command failed before printing)
falls back to `{}`.

## Proposed Solution

Capture stdout whatever the exit code is, and fall back only on empty output:

```bash
FMT_JSON=$(ll-issues format-check "$ID" --format json 2>/dev/null); [ -n "$FMT_JSON" ] || FMT_JSON='{}'
```

Add a test that runs the `check_reconcile_needed` predicate with a stub or real
`format-check` that prints a payload with `superseded_marker_count: 1` and exits 1. The
test asserts that the predicate exits 0 and arms `autodev-contradiction-reconcile-armed`.
Model it on the existing `check_reconcile_needed` tests in
`scripts/tests/test_autodev_loop.py`.

**Policy port (ENH-3623)**: the spike keeps parity (`markers = 0 if has_blocking_gaps`)
in `snapshot_issue`. The production port must use the fixed semantics, meaning markers
are read from the payload whatever `has_blocking_gaps` is. The spike's parity scenario
`contradiction_masked_by_format_gaps` flips to "reconcile runs". If this bug lands
before ENH-3623, the ENH-3618 characterization pin moves with it.

Check other `ll-issues … --format json … || echo` captures for the same pattern
(`grep -rn "format json.*|| echo" scripts/little_loops/loops/`).

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/autodev.yaml`: `check_reconcile_needed`

### Tests

- `scripts/tests/test_autodev_loop.py`: `check_reconcile_needed` predicate tests
- `scripts/tests/test_autodev_characterization.py`: re-pin any scenario whose reconcile
  sequence changes

### Documentation

- N/A

## Impact

- **Priority**: P3. A silent routing gap: ENH-2992's contradiction reconcile is dead for
  exactly the malformed issues most likely to carry stale directives.
- **Effort**: Small. A one-line shell change plus one test.
- **Risk**: Low. It can only add contradiction-only reconciles, which are capped at 2
  per pass.
- **Breaking Change**: No

## Steps to Reproduce

1. Create an active issue that has a `⚠ Superseded` directive marker and no `## Impact`
   section, so format-check reports a blocking gap.
2. Run `ll-issues format-check <ID> --format json; echo "rc=$?"`. It prints the payload
   (with `superseded_marker_count` ≥ 1) and `rc=1`.
3. Run `FMT_JSON=$(ll-issues format-check <ID> --format json 2>/dev/null || echo '{}')`.
   `$FMT_JSON` now holds two JSON objects, and `json.loads` rejects it.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: state `check_reconcile_needed`, the `FMT_JSON=` line (`:2112` at the time
  of capture)
- **Cause**: `|| echo '{}'` treats "exit non-zero" as "no output". `format-check`'s exit
  code signals blocking gaps and is independent of whether it printed the payload.

## Acceptance Criteria

- [ ] `check_reconcile_needed` reads `superseded_marker_count` when format-check exits 1
  with a payload
- [ ] An empty capture still falls back to `{}` (markers = 0)
- [ ] A regression test covers "marker present + blocking format gap → contradiction
  reconcile armed"
- [ ] ENH-3623's policy uses the same semantics

## Status

**Open** | Created: 2026-09-27 | Priority: P3
