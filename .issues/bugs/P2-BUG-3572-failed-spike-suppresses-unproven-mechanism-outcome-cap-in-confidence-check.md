---
id: BUG-3572
type: BUG
title: Failed spike suppresses unproven-mechanism outcome cap in confidence-check
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:13Z'
parent: EPIC-3565
blocks:
- ENH-3577
---

# BUG-3572: Failed spike suppresses unproven-mechanism outcome cap in confidence-check

## Summary

On failure, `/ll:spike` sets only `spike_attempted: true` (not `spike_completed`) and says a
failed spike means the approach is wrong. But confidence-check Phase 1.9 (ENH-3350) sets
`SPIKE_SUPPRESSED` when **either** `spike_attempted` or `spike_completed` is set. `rubric.md`
then applies no unproven-mechanism cap, and `outcome_confidence` becomes the raw Criteria A–D
sum. A spike that *disproved* the mechanism therefore removes the very cap that demanded
proof. Whether the issue stays blocked depends on the scorer noticing `## Spike Findings`,
which is discretionary, not an FSM guarantee.

## Current Behavior

A failed spike → `spike_attempted: true` → cap suppressed → the issue can pass the outcome
threshold on an approach its own spike refuted.

## Expected Behavior

Only a proven spike retires the proof requirement. A refuted spike routes to a decision,
design change or decomposition. An inconclusive or errored spike keeps the cap.

## Steps to Reproduce

1. Take an issue with `unproven_mechanism: true` whose mechanism is wrong
2. Run `/ll:spike --auto`; verification fails, and only `spike_attempted: true` is written
3. Run `/ll:confidence-check`: Phase 1.9 sets `SPIKE_SUPPRESSED`, and the outcome is scored with no unproven-mechanism cap

## Motivation

Spikes exist to prove a mechanism before implementation. Treating a disproof as permission to proceed defeats the purpose.

## Proposed Solution

Separate evidence truth from attempt bounding:

- Keep `spike_attempted` purely as a retry/attempt bound (autodev's remedy dispatcher and
  `check_spike_needed` rely on it).
- Suppress the cap only on `spike_completed: true`.
- Add a refuted outcome (e.g. `spike_refuted: true`, or a `spike_verdict: proven|refuted|inconclusive`
  field). Parent and child spike returns route a refuted result to `resolve_decision` or
  size-review instead of straight back to confidence scoring.

Check first: whether anything relies on attempted-only suppression to avoid a
spike → score → spike loop. The attempt bound should already prevent that.

## Program Design

### Types

- `spike_verdict: str` — frontmatter field, one of `proven`, `refuted`, `inconclusive`; `spike_attempted` stays an attempt bound only.

### Signatures

- `check_spike_needed(spike_needed: bool, spike_attempted: bool) -> bool` — existing autodev guard; unchanged.
- `route_spike_result(spike_verdict: str) -> str` — new routing rule: `refuted` goes to `resolve_decision` or size review, anything else to rescoring.

### Call Path

`run_spike` -> `route_spike_result` -> `rerun_confidence_after_spike`

## Integration Map

- `skills/spike/SKILL.md` (failure contract)
- `skills/confidence-check/SKILL.md` Phase 1.9; `skills/confidence-check/rubric.md` cap row
- `scripts/little_loops/loops/autodev.yaml` `run_spike` / `rerun_confidence_after_spike`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` spike return path
- Skill edits trip the mirror gates (`ll-adapt --apply` for gemini/kimi-code/qwen)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Every reader of the spike flags** (the full set any new marker must be reconciled with): `cli/issues/set_flags.py` (`_spike_not_already_flagged()` returns `not (spike_attempted or spike_completed)` and gates `spike_needed` re-flagging via `_spike_precondition_factory()`; `_unproven_mechanism_trigger()`); `cli/issues/show.py` (`show --json` surfaces `spike_needed`/`spike_attempted`/`spike_completed`/`unproven_mechanism` as lowercased strings — a new field would need surfacing here for FSM predicates to read it); `issue_parser.py` `IssueInfo` (carries `unproven_mechanism` only); `loops/autodev.yaml`; `loops/refine-to-ready-issue.yaml`; `loops/spike-gate.yaml`.
- **autodev spike-related states**: `check_spike_needed` and `check_spike_needed_before_skip` (predicate `spike_needed == 'true' and spike_attempted != 'true'`, string compare over `ll-issues show --json`); `recheck_after_size_review` (remedy selector: `spike_attempted == 'true'` yields no remedy; writes the once-per-run `autodev-pre-deferral-remedy-fired` marker); `dispatch_pre_deferral_remedy`; `run_spike`; `count_repair_cycle_spike` (FEAT-2751 backstop counter); `rerun_confidence_after_spike`. No autodev state reads `spike_completed` (comments only).
- **refine-to-ready spike states**: `check_spike_needed` (same predicate plus the run-dir marker `refine-to-ready-spike-ran`, BUG-3553) and `run_spike`; there is no `rerun_confidence_after_spike` state in this loop — the return goes straight to `confidence_check`.
- **`spike-gate.yaml`** already treats a failed spike as blocking: `check_spike_completed` (`check-flag spike_completed`) → `gate` (`/ll:spike --check`) → `run_spike_auto` → `recheck` → `blocked`. It is the only consumer keyed on completion rather than attempt, and is evidence for the intended semantics.
- **Termination does not depend on attempted-only cap suppression.** Loop bounds are the `spike_attempted != 'true'` predicates, the pre-deferral once-per-run marker, the `refine-to-ready-spike-ran` marker, and the FEAT-2751 stagnation counter; all are independent of the confidence-check cap, and `_spike_not_already_flagged` is a separate suppressor on `spike_needed` re-flagging. Not verifiable by static reading: absence of oscillation between `enqueue_or_skip` and the size-review/reconcile paths once the cap stays on — that rests on the stagnation backstop.
- **Correction — Program Design symbols are not Python**: `check_spike_needed` is an FSM state name (it reads strings `'true'` via `ll-issues show --json`, takes no arguments), not `check_spike_needed(spike_needed: bool, spike_attempted: bool) -> bool`; the nearest Python function is `set_flags._spike_not_already_flagged(issue: IssueInfo) -> bool`, a different guard. `route_spike_result` and `spike_verdict` / `spike_refuted` exist nowhere (proposals). The stated Call Path omits `count_repair_cycle_spike` in autodev, and refine-to-ready has no `rerun_confidence_after_spike`.
- **Correction — `resolve_decision` is not a state name**: the real routing targets are `resolve_decision_direct` and `run_decide` in autodev, `resolve_decision_pre_breakdown` (sub-loop `oracles/resolve-decision`) in refine-to-ready, and `snap_and_size_review` / `run_size_review` for size review. Not verified beyond the states quoted.
- **Tests that pin current behavior and will need to change together with the semantics**: `scripts/tests/test_confidence_check_skill.py` (asserts Phase 1.9 names `SPIKE_SUPPRESSED`, `spike_attempted`, `spike_completed`; `test_spike_attempted_guard_enforced`), `test_spike_skill.py` (asserts the `spike_completed: true` / `spike_attempted: true` strings in the skill), `test_set_flags_cli.py`, `test_builtin_loops.py` (many `check_spike_needed` / `spike-gate` assertions), `test_autodev_decision_gate.py`, `test_autodev_loop.py` (`_run_pre_deferral_remedy_selector`), `test_show.py`. None asserts that attempted-only suppresses the cap, so no existing test locks in the bug.
- **Docs and mirrors**: `docs/reference/ISSUE_TEMPLATE.md` (`spike_attempted` "whether or not it proved the mechanism"), `docs/reference/COMMANDS.md` (`/ll:spike`), `docs/reference/CLI.md` (~2273), `docs/guides/LOOPS_REFERENCE.md`, `docs/reference/API.md`; generated skill copies under `.gemini/`, `.kimi-code/`, `.qwen/` (`spike`, `confidence-check`) trip the mirror gates.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/spike-gate.yaml` — `check_spike_completed` → `recheck` → `blocked`; only completion-keyed consumer, confirm a refuted marker keeps it blocked
- `scripts/little_loops/cli/issues/set_flags.py` — `_spike_not_already_flagged()` suppresses `spike_needed` re-flagging on attempted-or-completed; must stay attempt-bound
- `scripts/little_loops/cli/issues/show.py` — `show --json` spike_* emission block; add the new verdict/refuted field here or FSM predicates cannot route on it
- `commands/refine-issue.md` (~L1083) — earlier spike-detection point reads `spike_attempted`/`spike_completed`; confirm unchanged semantics
- `commands/reconcile-issue.md` (~L144) — mirrors `/ll:spike`'s `spike_attempted` convention; update if the failure contract gains a marker

### Files to Modify
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/show.py` — surface new `spike_verdict`/`spike_refuted` as lowercased string [Agent finding]
- `scripts/little_loops/loops/README.md` (~L85) — `spike-gate` row describes spike flags; update if semantics change

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/ISSUE_TEMPLATE.md` — `spike_attempted` row; add new field (pinned by `test_wiring_reference_docs.py` entry `("docs/reference/ISSUE_TEMPLATE.md", "spike_attempted", "ENH-2640")`)
- `docs/reference/COMMANDS.md`, `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/guides/LOOPS_REFERENCE.md` — describe spike flags / "cleared by /ll:spike"; correct the overstated claim
- `scripts/little_loops/loops/README.md` — `spike-gate` row

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_confidence_check_skill.py` — update Phase 1.9 / `test_spike_attempted_guard_enforced`; add test that attempted-only keeps cap
- `scripts/tests/test_spike_skill.py` — add literal-string assertion for refuted marker on failure
- `scripts/tests/test_show.py` — add `show --json` surfacing test for new field (pattern at `test_show.py:373-438`)
- `scripts/tests/test_builtin_loops.py`, `test_autodev_loop.py`, `test_autodev_decision_gate.py` — new refuted-routing state assertions and stub-`ll-issues` action execution
- `scripts/tests/test_set_flags_cli.py` — confirm `_spike_not_already_flagged` behavior unchanged
- `scripts/tests/test_wiring_skills_and_commands.py` — `test_host_artifacts_are_not_stale` mirror gate (all five `GATED_HOSTS`, incl. `rubric.md` companion drift)

## Implementation Steps

1. Confirm no loop depends on attempted-only suppression for termination
2. Change Phase 1.9 suppression to `spike_completed` only
3. Add a refuted marker to the spike failure contract
4. Route refuted results to decision/size-review in autodev and refine-to-ready-issue
5. Regression test: failed spike keeps the cap; refuted spike never reaches implementation

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/issues/show.py` — emit the new spike verdict/refuted field so predicates can read it
- Update `scripts/little_loops/loops/spike-gate.yaml` — verify refuted stays blocked
- Update `docs/reference/ISSUE_TEMPLATE.md`, `COMMANDS.md`, `CLI.md`, `API.md`, `docs/guides/LOOPS_REFERENCE.md`, `scripts/little_loops/loops/README.md` — reflect new field and corrected suppression semantics
- Update tests: `test_confidence_check_skill.py`, `test_spike_skill.py`, `test_show.py`, `test_builtin_loops.py`, `test_autodev_loop.py`, `test_autodev_decision_gate.py`
- Regenerate mirrors: `ll-adapt --host <gemini|kimi-code|qwen|codex|omp> --apply`

## Impact

- **Priority**: P2. A refuted approach can reach implementation.
- **Effort**: Medium
- **Risk**: Medium. Changes the spike/scoring contract used by several loops.

## Acceptance Criteria

- [ ] A failed spike does not suppress the unproven-mechanism cap
- [ ] A refuted spike routes to decision/design/decomposition, not straight to rescoring
- [ ] Attempt limits still bound spike re-runs

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-25T01:11:18 - `283a56a1-35bd-43bb-b2f7-64d9f104c2c4.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:06:50 - `42a934e3-5df9-4ac6-9296-d0ced0bc2261.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:19 - `4b76ee9e-e590-41ab-940d-a6df6f1554bd.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:31 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **File**: `skills/confidence-check/SKILL.md`, Phase 1.9 (ENH-3350) — `SPIKE_SUPPRESSED="yes"` is set when `spike_attempted || spike_completed` succeeds (one `{ …||… }` group). `skills/confidence-check/rubric.md` § "Outcome Confidence Cap (ENH-3350)" applies `min(raw_sum, outcome_threshold − 1)` only when `UNPROVEN_MECHANISM == "true"` and `SPIKE_SUPPRESSED` is empty.
- **Write side**: `skills/spike/SKILL.md` Phase 6 "On failure" sets only `spike_attempted: true` and appends `## Spike Findings`; on success it sets both `spike_completed` and `spike_attempted`. No `spike_refuted` / `spike_verdict` exists anywhere, and nothing in the cap path reads `## Spike Findings`. The spike skill never clears `unproven_mechanism`; suppression is purely the Phase 1.9 read (`docs/reference/API.md`'s "cleared by /ll:spike (spike_completed)" comment overstates this).
- **Loop consequence**: `refine-to-ready-issue.yaml` `run_spike` returns `next`/`on_error: confidence_check` with no verdict routing, and autodev `run_spike` → `count_repair_cycle_spike` → `rerun_confidence_after_spike` → `enqueue_or_skip`, so a refuted spike is rescored uncapped in both.

## Conventions in Force

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Routing rule**: a skill writes the outcome into issue frontmatter and the FSM gates on a deterministic shell probe over that file (`fragment: shell_exit`) — never on a slash command's exit code or on prose (`cli/issues/check_verify_verdict.py:1-10`; `refine-to-ready-issue.yaml:397-401` "write-verdict/read-verdict shape"). Two probe shapes exist: a dedicated `ll-issues check-*` command (enum verdicts, one query-mode flag each, exit 0 match / 1 no match / 2 unresolved ID; precedence set by `on_no` chain order, e.g. "evidence outranks proposal" at `refine-to-ready-issue.yaml:409-413`) and inline python over `ll-issues show --json` when two fields are needed (`autodev.yaml:1416-1446`, `refine-to-ready-issue.yaml:722-748`).
- **A new field must be surfaced in `show --json` to be routable**: `show.py:134-148` emits lowercased strings (`'true'` or `None`) for `spike_*`, `reconcile_attempted`, `outcome_gate_waived`; BUG-3390 records that a flag not emitted there was "dead end-to-end". Predicates compare strings, not bools.
- **No key allowlist exists** for issue frontmatter — `spike_*`, `verify_verdict`, `reconcile_attempted` are written and read by name; the only registry is `DEPRECATED_FRONTMATTER_KEYS` (`frontmatter.py:54`), and only `decision_needed` / `unproven_mechanism` / `missing_artifacts` are typed `IssueInfo` fields (`issue_parser.py:4031-4033`, `_coerce_tristate_bool`).
- **Contested points**: value casing (`verify_verdict` UPPER-case enum compared via `.upper()`; spike flags lowercase `true`); read path (`verify_verdict` has a dedicated command and is not in `show --json`; spike flags use `check-flag` or `show --json`); absent-field default (`check-verify-verdict` default mode fail-open, its query flags and `check-flag` fail-closed); writer (`spike_*` and `verify_verdict` are written by the model via Edit — "there is no `set-flag` CLI verb", `skills/spike/SKILL.md:248-251` — while `spike_needed`/`decision_needed` go through `set-flags`).
- **Test shapes for routing changes**: subprocess-in-temp-`.issues/` command tests (`test_ll_issues_check_verify_verdict.py`), YAML structure assertions (`test_builtin_loops.py:3163-3240`), executing the real state `action` against a stub `ll-issues` on `PATH` (`test_builtin_loops.py:1989-2008`, `test_autodev_loop.py:633-688` `_run_pre_deferral_remedy_selector`, `:53-73` `_run_reconcile_predicate`), skill-contract literal-string tests (`test_spike_skill.py:100-107`), and `show --json` surfacing (`test_show.py:373-438`).
- **Mirror gate**: `test_wiring_skills_and_commands.py:463` `GATED_HOSTS = ["gemini","kimi-code","qwen","codex","omp"]`; `test_host_artifacts_are_not_stale` fails on any un-regenerated mirror (`ll-adapt --host <h> --apply`, per host; `codex` is gated too), with a separate companion-file drift check (`:602-638`) covering `rubric.md`.
