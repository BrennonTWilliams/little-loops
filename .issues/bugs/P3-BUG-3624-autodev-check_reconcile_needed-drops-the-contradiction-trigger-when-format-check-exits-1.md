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
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `test_check_reconcile_needed_fires_on_contradiction` (optional: pin the fixed capture text; existing substring asserts on `ll-issues format-check` / `superseded_marker_count` stay satisfied) [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — `TestInterpSweepBaseline.test_completeness_guard` vs `scripts/tests/data/loop_interpolation_baseline.json` (`check_reconcile_needed`, `context.run_dir`, `line: 10`): must not break — the fix adds no `${...}` token and must stay on the same physical line via `;` [Agent 2/3 finding]
- `scripts/tests/test_spike_verdict_routing.py` — `_stub_path` / `_dispatch_env` / `_run`: closest pattern for a full-action test (stub `ll-issues` on `PATH`, run the state action via `bash`); no existing stub exits non-zero with stdout, so the new stub is `format-check` → print payload + `exit 1`. `_run` rewrites `${context.readiness_threshold:shell}` to an unresolvable form, so the new test needs its own replace step supplying a threshold [Agent 3 finding]
- `scripts/tests/test_ll_issues_format_check.py` — `TestSupersededMarkerCountKey` (`_json_for`, `_write_bug_with_steps`): add a case with `superseded_marker_count >= 1` **and** a structural gap asserting `exit == 1` with the count still emitted; existing `test_marker_count_counts_marked_directive_line` only covers exit 0 [Agent 3 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/format_check.py` — `cmd_format_check`: the exit-1-after-print contract producer; no change, but the fix depends on it [Agent 2 finding]
- `scripts/little_loops/fsm/runners.py` — runs the interpolated action as `bash <tmpfile>` with no `-e`/`pipefail`, so a non-zero `$(...)` assignment does not abort before the `[ -n ]` fallback; the state exit code comes from the trailing `python3 << 'PYEOF'` [Agent 2 finding]
- `scripts/little_loops/loops/autodev.yaml:2417` — `ISSUE_JSON=$(ll-issues show "$ID" --json 2>/dev/null || echo '{}')`: sibling capture with the same shape; unverified whether `show --json` exits non-zero after printing (see Wiring Phase) [Agent 1 finding]
- `skills/confidence-check/SKILL.md:138` — `FC_JSON=$(ll-issues format-check ... --format json 2>/dev/null || true)`: `|| true` yields a single object, so not affected [Agent 1/2 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — reads `format-check --format json` stdout via `subprocess.run(...).stdout` regardless of exit code; not affected [Agent 2 finding]
- `scripts/little_loops/loops/rn-remediate.yaml` (state `ensure_formatted`) — uses the format-check exit code as the gate, not the JSON; not affected [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (~2709-2715), `docs/reference/API.md` (~964-984, `#### superseded_marker_count`), `docs/reference/COMMANDS.md` (~301-311), `docs/guides/LOOPS_REFERENCE.md` (autodev diagram) — describe the contradiction predicate reading `superseded_marker_count`; none quote the capture line, so no edit required [Agent 1/2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Edit `scripts/little_loops/loops/autodev.yaml` `check_reconcile_needed` — replace the `FMT_JSON=` line with the fixed capture on one physical line (`;`-joined) to preserve baseline `line: 10`; add no `${...}` tokens
- Add a full-action regression test (stub `ll-issues format-check` printing `{"superseded_marker_count": 1}` and exiting 1, modelled on `test_spike_verdict_routing.py` helpers) asserting exit 0 and `autodev-contradiction-reconcile-armed` created; keep `test_missing_format_check_payload_is_inert` passing
- Add the exit-1 + marker-count case to `TestSupersededMarkerCountKey` in `scripts/tests/test_ll_issues_format_check.py`
- Verify `scripts/tests/data/loop_interpolation_baseline.json` / `TestInterpSweepBaseline.test_completeness_guard` still pass
- Check `autodev.yaml:2417` (`ll-issues show --json ... || echo '{}'`): confirm whether `show --json` exits non-zero after printing; fix the same way if so, else leave (documented fail-closed)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **Existing test seam does not exercise the bug.** `_run_reconcile_predicate` (`scripts/tests/test_autodev_loop.py`) extracts only the `<< 'PYEOF'` body and injects `LL_FORMAT_CHECK_JSON=json.dumps({"superseded_marker_count": N})` — always one clean object. The shell line (`FMT_JSON=$(...)`) is never run, so a regression test must execute the shell portion (stub `ll-issues` on `PATH` printing a payload and exiting 1) or feed the concatenated `"<payload>\n{}"` string. `TestCheckReconcileNeededContradiction` is the existing class; `test_missing_format_check_payload_is_inert` pins the empty-capture → exit 1 contract that must keep passing.
- **Static checks on the action text** in `scripts/tests/test_builtin_loops.py` (`test_check_reconcile_needed_fires_on_contradiction`, `..._predicate_reads_snapshot_and_guard`, `..._routing`) assert on the action string; the fix must keep `superseded_marker_count` in it and leave routing unchanged.
- **Characterization test has no such scenario today.** `scripts/tests/test_autodev_characterization.py` has no `contradiction_masked_by_format_gaps` scenario and no `format-check` stub; that name exists only in `thoughts/spikes/preparation-policy-spike.md:224` and this issue. "Re-pin" applies only if a scenario is added before this lands.
- **`snapshot_issue` parity is prose only.** `markers = 0 if has_blocking_gaps` appears solely in the spike report; no `snapshot_issue` code exists under `scripts/` (ENH-3623's port is not yet written), so this fix has no code to keep in parity.
- **Exit-code contract**: `cmd_format_check` exit 1 means "blocking gaps", independent of whether the payload printed; `print_json` writes multi-line JSON to stdout, stderr is discarded by the capture. Any capture of this command must treat stdout as authoritative and non-empty stdout as valid.
- **Sibling captures with the same shape** (`|| echo '{}'` on an `ll-issues` JSON call): `scripts/little_loops/loops/autodev.yaml:2417` (`ll-issues show "$ID" --json`, go-no-go eligibility, documented as fail-closed; whether `show --json` exits non-zero after printing is unverified). `autodev.yaml:2112` is this bug. `auto-refine-and-implement.yaml:1156` is a `python3 -c` read, not an `ll-issues` call. `refine-to-ready-issue.yaml` (~421, 470) calls `format-check --format json` from Python via subprocess; its exit-code handling was not checked. `autodev.yaml` 768/852/936/2923 use `... | python3 -c ... || echo 0`, a different pattern.

## Program Design

### Types

- `LL_FORMAT_CHECK_JSON: str` (env) — the raw `FMT_JSON` shell capture handed to the embedded Python; must be exactly one JSON object or empty.
- `superseded_marker_count: int` — payload key added in `cmd_format_check`, deliberately outside `FormatGaps` so it does not affect the exit code.

### Signatures

- `cmd_format_check(...)` in `scripts/little_loops/cli/issues/format_check.py` — single-issue `--format json` branch calls `print_json(payload)` then `return 1 if gaps.has_blocking_gaps else 0`.
- `FormatGaps.has_blocking_gaps` (property, `scripts/little_loops/issue_parser.py`) — true when any non-advisory gap field is non-empty; drives the exit 1.
- State `check_reconcile_needed` (`scripts/little_loops/loops/autodev.yaml:2058`, `fragment: shell_exit`) — exit 0 routes `on_yes: reconcile_current`, exit 1 `on_no: check_size_review_ran_this_pass`, `on_error: recheck_after_size_review`.

### Call Path

`check_reconcile_needed` shell (`FMT_JSON=$(ll-issues format-check "$ID" --format json ...)`) -> `cmd_format_check` -> `print_json` + exit 1 -> `|| echo '{}'` appends second object -> inline Python `json.loads(os.environ.get('LL_FORMAT_CHECK_JSON') or '{}')` raises -> `markers = 0` -> `contradiction = (markers > 0 and fires < 2)` false -> no `autodev-contradiction-reconcile-armed` file.

### Decision Rules

N/A — no new decision logic (the fix restores the existing `contradiction` predicate's input; the cap of 2 fires and `reconcile_attempted`-independence are unchanged).

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


## Session Log
- `/ll:confidence-check` - 2026-09-27T02:15:49 - `5c8dc844-d82e-462d-9610-24d025987ba4.jsonl`
- `/ll:verify-issues` - 2026-09-27T02:14:53 - `3143f6e8-9395-4f72-8d86-84d59317dfae.jsonl`
- `/ll:wire-issue` - 2026-09-27T02:13:46 - `07fe43aa-098a-4840-b17f-974727d41820.jsonl`
- `/ll:refine-issue` - 2026-09-27T02:11:06 - `db47d979-a700-4e7c-899a-d81e2c52e3fe.jsonl`
