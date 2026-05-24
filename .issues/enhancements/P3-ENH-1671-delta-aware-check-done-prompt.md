---
id: ENH-1671
type: ENH
priority: P3
status: open
discovered_date: 2026-05-24
discovered_by: audit-loop-run
depends_on: ENH-1658
supersedes: ENH-1656
confidence_score: 70
outcome_confidence: 60
---

# ENH-1671: Delta-aware `check_done` prompt to scope re-verification to the most recent step

## Summary

The `general-task` loop's `check_done` *prompt action* re-reads both files and re-verifies every Definition-of-Done criterion from scratch on every iteration, regardless of what changed in the previous `execute` step. Scope the prompt to the step that just completed (plus a small sample of previously-`[x]` criteria) so per-iteration cost and API-failure exposure both drop. This is the prompt-action side of `check_done`; [[ENH-1658]] addresses the gate (the `evaluate:` block) and explicitly leaves the prompt action unchanged.

## Problem

In the audited `2026-05-23T224029` run of `general-task`, `check_done` prompt-action durations were:

| Iteration | Duration | Criteria |
|-----------|----------|----------|
| 4         | 163s     | 47 criteria verified |
| 6         | 151s     | 47 criteria re-verified |
| 8         | 161s     | 47 criteria re-verified |
| 10        | 158s     | 47 criteria re-verified |
| 12        | 152s     | 47 criteria re-verified |
| 14        | 510s     | 47 criteria re-verified → API error |

Only one plan step changed between each `check_done` call, yet all 47+ criteria were re-verified each time. The per-iteration delta is small (e.g., "composite-audio.ts now imports renderLogoSting"), but the verification cost is constant. The 510s session at iteration 14 is the one that hit a transient API failure — long sessions are the API-failure surface.

Cumulatively, this is ~12 minutes of LLM verification time across 6 cycles on a 34-minute run, dominated by repeated work the model has already done.

## Current Behavior

`scripts/little_loops/loops/general-task.yaml:74-122` defines `check_done` as a prompt action that, on every iteration, instructs the model to:

1. Re-read both `general-task-plan.md` and `general-task-dod.md`.
2. Reconcile every plan step against every DoD criterion.
3. **Verify EACH DoD criterion by evidence** (filesystem reads, command runs, file reads).
4. Sample-re-verify up to 3 already-`[x]` criteria.
5. Print the full DoD + plan to stdout.

Step 3 is the cost driver: 47 criteria × full filesystem/grep verification per iteration. There is no scoping signal — the prompt has no way to know which criteria are plausibly affected by the step that just ran.

## Expected Behavior

The `check_done` prompt action receives a **delta hint** identifying the step that just completed and the files it touched, then:

- **Newly relevant criteria** (covered by this step or touching the same files): fully verify by evidence.
- **Previously-`[x]` criteria not plausibly affected by this step**: keep `[x]` without re-running their commands.
- **Spot-check sample**: pick 3 previously-`[x]` criteria at random and re-verify (current behavior, preserved).
- **Previously-`[ ]` criteria not plausibly affected**: leave `[ ]` with their existing one-line note.

This preserves the Definition-of-Done bar — every criterion is still verified at least once and continually spot-checked — while bounding per-iteration cost to "verify the slice of criteria the latest step could have touched, plus a constant-size sample."

## Motivation

- **Per-iteration prompt cost drops ~3–10×.** From ~150–500s/full-verify to an estimated ~30–60s/scoped-verify, based on the criteria-per-step ratio in the audited run.
- **Reduced exposure to transient API failures.** The 510s session was the one that errored; shorter sessions ⇒ fewer retries even before cost matters.
- **Speeds up loop iteration time on long DoDs.** The cost gap widens as the DoD grows; 47 criteria today, more tomorrow.
- **Complements, does not overlap, [[ENH-1658]].** That issue replaces the gate's `llm_structured` evaluator with a shell counter (saves one cheap evaluator call). This issue scopes the prompt action's expensive verification work. Both ship cleanly on top of [[BUG-1628]]'s structural fix.

## Proposed Solution

Pass the delta into the `check_done` prompt via captured state from `execute`, and add scoping instructions to the prompt.

**Option 1 — Delta-aware prompt (preferred, smallest change):**

The `execute` state already completes one plan step. Have `execute` capture the step text and the touched files (e.g., via the model echoing them in a structured tail of its output, captured to `last_step` / `last_files`). Then `check_done`'s prompt reads:

```yaml
check_done:
  action: |
    Step ${captured.last_step} was just completed.
    Files touched in this step: ${captured.last_files}

    Read both files:
    - ${env.PWD}/.loops/tmp/general-task-dod.md
    - ${env.PWD}/.loops/tmp/general-task-plan.md

    Verification policy:
    - For DoD criteria that mention or depend on the touched files OR the just-completed
      step: VERIFY BY EVIDENCE now (filesystem read / command run / file read).
    - For previously-[x] criteria NOT plausibly affected by this step: KEEP [x], do not
      re-run their commands.
    - For previously-[ ] criteria NOT plausibly affected by this step: leave [ ] with
      their existing note.
    - Sample re-verification: pick 3 previously-[x] criteria at random and re-verify
      independently. Append a `## Sample Verification` section as today.

    Print the final DoD and plan to stdout.
  action_type: prompt
  next: count_done   # if ENH-1658 has landed; otherwise keep the existing evaluator
  on_error: diagnose
```

**Option 2 — Phased DoD (alternative if delta capture proves brittle):**

Structure the DoD file with phase headers (`## Phase 1: Asset Loading`, `## Phase 2: Audio Wiring`, …) and pass the current phase to `check_done`. The prompt verifies only criteria under the current phase, plus a sample from earlier phases. Coarser-grained than Option 1, but doesn't require capturing per-step file lists.

**Option 3 — mtime-based cached verification (heaviest):**

Track which criteria were verified in previous iterations and the mtime of every file they touched; only re-verify criteria whose underlying files have changed since their last `[x]`. Requires sidecar state and is probably overkill for the gain — listed for completeness, not recommended.

## Acceptance Criteria

- [ ] `execute` state in `general-task.yaml` captures the step text and touched files in a structured form readable by `check_done` (e.g., `captured.last_step`, `captured.last_files`).
- [ ] `check_done` prompt receives the delta and follows the scoped verification policy above.
- [ ] Sample re-verification (3 previously-`[x]` criteria) is preserved unchanged so the safety net still catches regressions in criteria outside the touched scope.
- [ ] On a fixture loop run where step N touches file F, `check_done`'s output shows: (a) criteria referencing F were re-verified by evidence; (b) criteria with no relation to F were not re-run (verifiable from the action's tool-use trace); (c) 3 previously-`[x]` criteria were independently sample-re-verified.
- [ ] Mean `check_done` action duration on a representative task drops ≥ 50% vs. the pre-change baseline (measured on the same DoD).
- [ ] No regression in the loop's terminal correctness: a deliberately-broken criterion outside the delta's scope is still caught by the sample re-verification within ⌈47/3⌉ ≈ 16 iterations.
- [ ] `ll-loop validate scripts/little_loops/loops/general-task.yaml` passes.
- [ ] `docs/guides/LOOPS_GUIDE.md` general-task section documents the delta-scoped verification policy.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — add delta capture in `execute`, rewrite `check_done` prompt to consume it, preserve sample re-verification.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/interpolation.py` — `InterpolationContext.resolve()` + `_get_nested()` handle `${captured.<varname>.<field>}` expansion. The `<field>` segment (`output`, `stderr`, `exit_code`, `duration_ms`) is **required** — `${captured.X}` without a field suffix returns the raw dict repr, not the string. Confirmed: no FSM changes needed to support this pattern.
- `scripts/little_loops/fsm/executor.py:985–992` — `FSMExecutor._run_action()` stores capture after action execution: `self.captured[state.capture] = {"output": result.output.rstrip(...), ...}`. The `capture:` YAML field is `str | None` (see `schema.py:374`) — **one capture slot per state only**.
- `/ll:audit-loop-run` — readers should still find the `## Sample Verification` section; format is preserved.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/schema.py:374` — `StateConfig.capture: str | None` — single string, one capture key per state. The two-key API (`captured.last_step` + `captured.last_files`) in the Proposed Solution requires either (a) a single unified capture key containing both values, or (b) a two-state split (not practical here). **Recommended**: one `capture: execute_result` on `execute`; `check_done` reads `${captured.execute_result.output}` which contains the full LLM output including the structured trailing lines.
- `scripts/little_loops/loops/general-task.yaml:64–75` — `execute` state currently has **no `capture:` field** — confirmed by reading the YAML. Adding `capture: execute_result` here is the only required schema change.
- `scripts/little_loops/loops/dead-code-cleanup.yaml:26,52` — canonical capture-then-consume pattern: `scan` uses `capture: scan_results`; `remove_code` reads `${captured.scan_results.output}`. Direct template for this issue.
- `scripts/tests/test_general_task_loop.py` — fixture test pattern: YAML loaded via `yaml.safe_load`, assertions on `raw_data["states"]["check_done"]["action"]` string content. New tests for delta behavior should follow this class-per-change structure (see `TestChange2CheckDoneReconcileAndSampleVerify` for the model).

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml:61-72` — the `execute` state already produces step-completion text; this issue formalizes the contract so `check_done` can consume it.
- `scripts/little_loops/loops/dead-code-cleanup.yaml` — precedent for shell-side capture (used by [[ENH-1658]]); not directly reusable here but confirms `captured.*` is part of the FSM's vocabulary.

### Tests
- Add a fixture under `scripts/tests/` exercising three cases on `check_done`:
  - Step touched files matching a subset of criteria → only those re-verified by evidence.
  - Step touched a file no criterion mentions → only sample-re-verification runs.
  - Sample re-verification fails on a criterion → that criterion flips back to `[ ]`.
- Smoke test: `ll-loop validate` on the modified YAML.

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — describe the delta input, the verification-scoping policy, and the preserved sample re-verification safety net.

### Configuration
- N/A.

## API/Interface

N/A — No public Python API changes.

**Internal FSM captured-state contract (new key emitted by `execute` and consumed by `check_done`):**

> **Implementation note** (from codebase research): `capture:` in `StateConfig` is `str | None` — one slot per state. Both `last_step` and `last_files` must travel in a single capture key. The correct interpolation path is always `${captured.<varname>.output}` (the `.output` field suffix is required; omitting it returns a raw dict repr). The `captured.last_step` / `captured.last_files` shorthand in the Proposed Solution YAML snippet is illustrative — the actual YAML and prompt must use the pattern below.

```yaml
# In general-task.yaml execute state:
capture: execute_result   # single key; stores full LLM output as .output
```

`execute`'s prompt must emit structured trailing lines (the FSM stores the entire stdout verbatim — no auto-extraction):

```
LAST_STEP: <step text>
LAST_FILES: <path1> <path2> ...
```

`check_done` consumes the full output via `${captured.execute_result.output}`, which inlines the complete `execute` LLM response (including those structured lines) into the prompt. The model is then instructed to parse `LAST_STEP:` / `LAST_FILES:` from that inlined context.

_Confirmed by:_ `scripts/little_loops/fsm/executor.py:985–992` (capture storage), `scripts/little_loops/fsm/interpolation.py:80–81` + `_get_nested()` (resolution), `scripts/little_loops/fsm/schema.py:374` (`capture: str | None`).

## Implementation Steps

1. Read the FSM's interpolation rules in `scripts/little_loops/fsm/` to confirm how `execute` can hand structured data to `check_done` (most likely a captured-state slot keyed by state name).
2. Update `execute`'s prompt to print a structured trailing line — e.g., `LAST_STEP: <text>` and `LAST_FILES: <space-separated paths>` — and capture both into the FSM state.
3. Rewrite `check_done`'s prompt per Option 1 above. Keep the sample-re-verification block byte-identical so [[ENH-1658]]'s shell counter still works.
4. If [[ENH-1658]] has landed, `next: count_done`; otherwise keep the current evaluator. Do not couple to 1658.
5. Add the three fixture tests under `scripts/tests/`.
6. Run a representative `general-task` loop end-to-end and compare mean `check_done` duration vs. the pre-change baseline. Record the numbers in the PR description.
7. Update `docs/guides/LOOPS_GUIDE.md`.

## Scope Boundaries

- **In scope**: Scoping the `check_done` *prompt action* to the most recent step's delta, with preserved sample re-verification.
- **In scope**: Capturing step + touched-files from `execute` into FSM state for `check_done` to consume.
- **Out of scope**: Replacing the LLM gate with a shell counter — that's [[ENH-1658]].
- **Out of scope**: Fixing plan-exhaustion oscillation — that's [[BUG-1628]].
- **Out of scope**: Generalizing delta-aware verification to other loops. Scoped to `general-task`.
- **Out of scope**: Persisting cached verification state across iterations (Option 3 above). Sample re-verification is the chosen safety net.

## Success Metrics

- Mean `check_done` prompt-action duration on a representative `general-task` run drops ≥ 50% vs. the pre-change baseline on the same DoD.
- Long-tail `check_done` sessions (the API-failure surface) drop sharply — no `check_done` calls > 300s on a DoD with ≤ 50 criteria.
- Zero observed cases of a regression in a previously-`[x]` criterion going undetected for more than `⌈total_criteria / 3⌉` iterations (the sample re-verification interval).

## Impact

- **Priority**: P3 — quality + reliability improvement; complements but does not block [[BUG-1628]] or [[ENH-1658]].
- **Effort**: Small-to-medium — one prompt rewrite, one FSM-capture wiring, three fixture tests, one doc update.
- **Risk**: Low-to-medium. Scoping risks leaving a regression undetected until the next sample-re-verification cycle. Mitigated by keeping sample re-verification on every iteration and by Acceptance Criterion #6.
- **Breaking Change**: No — the loop's external contract (DoD format, plan format, terminal states) is unchanged. The `## Sample Verification` section is preserved.

## Source

Promoted from [[ENH-1656]]'s problem statement and audit data on 2026-05-24. ENH-1656 was originally filed as a delta-aware-verification proposal, then deprecated after the gate-vs-prompt-action distinction surfaced: [[ENH-1658]] addresses the gate; this issue addresses the prompt action that 1658 explicitly preserves. The audit numbers, the delta-aware prompt mechanism, the phased-DoD alternative, and the API-failure-exposure framing all originate from ENH-1656 and are retained here so they survive 1656's closure.

## Related Key Documentation

- `docs/guides/LOOPS_GUIDE.md` — general-task loop documentation.
- `scripts/little_loops/loops/general-task.yaml` — the loop this issue modifies.

## Labels

`enhancement`, `loops`, `general-task`, `cost`, `reliability`

## Status

**Open** | Created: 2026-05-24 | Priority: P3


---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-24): ENH-1671 and ENH-1655 are complementary halves of the same root failure (the 510s `check_done` session at iteration 14 of the `2026-05-23T224029` run that terminated on an API error). ENH-1671 reduces session duration so the failure probability drops; ENH-1655 retries gracefully when failures still occur. Neither provides complete coverage alone. When planning sprint work, schedule both.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-24T13:37:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1c29e127-5f7b-421f-9734-c94217103bba.jsonl`
- `/ll:format-issue` - 2026-05-24T13:23:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/101e364c-669a-4add-9c9a-d2fd416d3171.jsonl`
