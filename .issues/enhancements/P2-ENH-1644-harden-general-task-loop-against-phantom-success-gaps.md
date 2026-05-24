---
captured_at: "2026-05-23T21:59:53Z"
discovered_date: 2026-05-23
discovered_by: capture-issue
status: open
relates_to: [BUG-1628, ENH-1629]
---

# ENH-1644: Harden general-task loop against phantom-success gaps

## Summary

A `general-task` loop run (`general-task-loop-audit-mc-vault.txt`, mc-vault project) reached terminal `done` with 75/75 DoD criteria marked `[x]` and 9 real implementation artifacts produced — but plan Step 11 ("Verify — dry run tests, single date injection, failure recovery, service installation") was still unchecked, and no DoD criterion mapped to it. The evaluator trusted markdown checkbox state instead of re-verifying, so the gap went undetected. Three coordinated edits to `scripts/little_loops/loops/general-task.yaml` close the gap without new states or templates.

## Motivation

Three root causes named in the audit:

1. **[contract]** DoD template invites *static* criteria only (file exists, imports work, content matches), leaving runtime-verification gaps in the plan uncovered.
2. **[state]** `check_done` reads only the DoD — never cross-checks against the plan, so plan-vs-DoD drift goes silent.
3. **[rubric]** The evaluator prompt ("Are ALL criteria marked `[x]`?") asks about checkbox state, not about evidence — an LLM step that prematurely marks `[x]` is accepted at face value.

The current loop's `check_done` *action* already says "verify by evidence" — so the action prompt body is fine. The load-bearing fixes are: (a) bias the DoD toward runtime criteria when the task warrants it, (b) read the plan in `check_done` and reconcile coverage, and (c) push sample-verify down into the `check_done` *action* (where tools are available) and have the evaluator confirm the action reported clean results.

### Evaluator capability constraint

`evaluate_llm_structured` (`scripts/little_loops/fsm/evaluators.py:572`) is a `build_blocking_json` call with **no tool access**, and it only sees the last 4000 chars of the action's stdout (line 605). It cannot read files, run commands, or check filesystem state. Therefore sample-verify must execute inside the `check_done.action` body (which is a `prompt` action with full tools) and emit its results into the action output; the `evaluate` step is restricted to structural reasoning over text the action already produced.

Adjacent to [[BUG-1628]] (plan exhaustion / oscillation) and [[ENH-1629]] (explicit thresholds). The changes here do not close either, but they harden the same surface and should not conflict.

## Current Behavior

`scripts/little_loops/loops/general-task.yaml`:

- `define_done.action` (lines 10–23) instructs the LLM to draft a DoD from the task input, with no explicit demand for runtime criteria.
- `check_done.action` (lines 62–69) reads only the DoD file and verifies criteria by evidence; the plan file is never opened in this state.
- `check_done.evaluate.prompt` (lines 73–76) asks a single question — "Are ALL criteria marked `[x]`?" — and routes to `done` on a YES.

Result: a DoD of 75 static criteria can be fully checked while a runtime verification step in the plan stays unchecked, and the loop still terminates `done`.

## Expected Behavior

Four coordinated, in-place edits to the same file:

1. `define_done` requires runtime-verification criteria whenever the task has a runtime surface.
2. `check_done.action` reads both the DoD *and* the plan, reconciles them, refuses to mark plan steps complete without DoD coverage, and performs sample re-verification of up to 3 already-`[x]` criteria.
3. `continue_work.action` is extended so that when all plan steps are `[x]` but a DoD criterion remains unchecked, it appends a remediation plan step before working — otherwise the loop has no unchecked plan step to advance on and will spin until `max_iterations`.
4. `check_done.evaluate.prompt` confirms (structurally, over the action's emitted text) that the DoD is fully `[x]`, the plan is fully `[x]`, and the sample-verification section the action wrote reports a clean pass.

The mc-vault failure mode is structurally prevented: either the DoD would have had a runtime criterion that fails verification, or the plan cross-check would add the missing criterion and block `done` until it verifies.

## Proposed Solution

Single-file edit: `scripts/little_loops/loops/general-task.yaml`. Four coordinated changes, in place, no new states, no new templates.

### Change 1 — `define_done.action`: require runtime-verification criteria when applicable

In the `define_done.action` block (lines 10–23), extend the prompt so the DoD writer is explicitly told to add **runtime** criteria for any task that involves running, testing, or installing something — not just static file/content checks. Append a clause like:

> If the task involves running code, executing tests, installing a service, or producing output at runtime, the DoD **must** include criteria for that runtime behavior (e.g., "dry-run exits 0", "service plist loads without launchd errors", "first injection produces expected output"). Static file/import checks alone are insufficient when the task has a runtime surface.

### Change 2 — `check_done.action`: cross-check + sample re-verify (the verification happens here)

In the `check_done.action` block (lines 62–69), broaden the action so it reads **both** the DoD and the plan, reconciles them, and emits sample-verification results into its own output for the evaluator to read:

- Read `${env.PWD}/.loops/tmp/general-task-dod.md` **and** `${env.PWD}/.loops/tmp/general-task-plan.md`.
- For every plan step, confirm at least one DoD criterion covers it. If a plan step has no matching DoD criterion, **add a new criterion to the DoD** before evaluating completion. Do not silently mark plan steps `[x]` without DoD coverage.
- Verify each DoD criterion by evidence (existing language preserved). Update both files: mark `[x]` only when verified, otherwise leave `[ ]` with a one-line note on what is missing.
- **Sample re-verify**: pick up to 3 already-`[x]` DoD criteria (`min(3, total_checked)`), independently re-verify each by re-running the command / re-reading the file / re-checking the filesystem, and append a `## Sample Verification` section to the DoD file in this format:
  ```
  ## Sample Verification
  - [x] <criterion>: <evidence>
  - [x] <criterion>: <evidence>
  - [ ] <criterion>: FAILED — <what happened>
  ```
  If any sample fails re-verification, flip the corresponding criterion back to `[ ]` with a note explaining the mismatch.

### Change 3 — `continue_work.action`: handle "all plan `[x]`, DoD unchecked" gap

Today's `continue_work` (lines 81–92) only knows how to advance the **first unchecked plan step**. After Change 2, `check_done` can leave a newly-added DoD criterion unchecked while every plan step is already `[x]` — in that state `continue_work` has nothing to do and the loop oscillates until `max_iterations`. Extend the prompt so that:

- If an unchecked plan step exists, behavior is unchanged (advance the first one).
- Otherwise, find the first unchecked DoD criterion, **append a remediation step to the plan** describing the work needed to satisfy it, then complete that step and mark it `[x]`.
- If the DoD is fully `[x]` and the plan is fully `[x]`, do nothing (the next `check_done` will route to `done`).

### Change 4 — `check_done.evaluate.prompt`: structural confirmation over action output

The `llm_structured` evaluator has no tool access and only sees the last ~4000 chars of the action's stdout, so it cannot independently run commands or read files (see Motivation). Its job is to confirm what the action already verified. Replace the prompt (lines 73–76) with:

> The `check_done` action wrote a sample-verification report and updated the DoD and plan files. From the action output below:
> 1. Does the action output show ALL DoD criteria marked `[x]`?
> 2. Does it show ALL plan steps marked `[x]`?
> 3. Does the `## Sample Verification` section report every sampled criterion as `[x]` with passing evidence?
>
> Answer YES only if all three conditions are met. Answer NO if any criterion or plan step remains `[ ]`, or if any sampled criterion is reported as FAILED.

Raising `min_confidence` (e.g., `0.8`) with `uncertain_suffix: _uncertain` so low-confidence YES routes to `continue_work` is deferred — see Scope Boundaries.

## Acceptance Criteria

- [ ] `define_done.action` prompt in `scripts/little_loops/loops/general-task.yaml` requires runtime-verification criteria when the task has a runtime surface.
- [ ] `check_done.action` reads both `general-task-dod.md` and `general-task-plan.md`, adds DoD criteria for any plan step that lacks coverage, and emits a `## Sample Verification` section re-checking up to `min(3, total_checked)` already-`[x]` criteria with pass/fail evidence.
- [ ] `continue_work.action` advances the first unchecked plan step when one exists; otherwise, if a DoD criterion is unchecked, it appends a remediation plan step and completes it (no spin-to-`max_iterations` when plan is fully `[x]` but DoD is not).
- [ ] `check_done.evaluate.prompt` confirms DoD all `[x]`, plan all `[x]`, and `## Sample Verification` reports all sampled criteria passing — based solely on the action output, not on independent verification.
- [ ] `ll-loop validate general-task` passes (YAML schema unchanged).
- [ ] `ll-loop --show-diagrams general-task` renders without transition changes.
- [ ] A re-run on a runtime-surface task (e.g., "write a Python script and verify it runs") either includes runtime criteria in the DoD or is blocked from reaching `done` by the plan cross-check or sample re-verification.
- [ ] Regression: a contrived run where `check_done` adds an unverifiable DoD criterion while plan is fully `[x]` does not spin to `max_iterations` — `continue_work` adds and works a remediation step.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — four in-place YAML string edits: `define_done.action`, `check_done.action`, `continue_work.action`, `check_done.evaluate.prompt`.

### Reference (no edit)
- `scripts/little_loops/loops/harness-single-shot.yaml` — pattern for multi-gate verification (`diff_stall` → `exit_code` → `llm_structured` → `output_numeric`); confirms the shape we're leaning into.
- `scripts/little_loops/fsm/evaluators.py:572` — `evaluate_llm_structured` uses `build_blocking_json` with no tools and truncates action output to the last 4000 chars (line 605); this constrains the evaluator to structural reasoning over emitted text. No runtime changes needed; this reference is what motivates pushing verification into `check_done.action`.

### Similar Patterns
- `scripts/little_loops/loops/harness-single-shot.yaml` multi-gate verification — establishes precedent for stacking conditions inside a single evaluate step.

### Tests
- `ll-loop validate general-task` smoke check after the edit (run from repo root; `ll-loop` resolves the loop by name from the package).
- Live re-run on a small task ("create `foo.txt` containing 'hello'") — expect `done` reached with DoD + plan both `[x]` and a `## Sample Verification` section in `general-task-dod.md` showing the sampled criteria re-verified.
- Live re-run on a runtime-surface task — expect DoD now contains runtime criteria (Change 1); if the runtime step is skipped, `check_done.action` adds a covering criterion (Change 2) and the sample-verify section catches a stale `[x]`.
- Contrived oscillation test: force `check_done` to add an unverifiable DoD criterion while plan is fully `[x]` (e.g., a task whose runtime check legitimately fails). Expect `continue_work` to append a remediation plan step rather than spin to `max_iterations` (Change 3).
- Regression against `general-task-loop-audit-mc-vault.txt` — confirm the "phantom Step 11" failure mode is structurally prevented.

### Documentation
- No doc changes required — prompts are inline in the loop YAML. Optional: a one-line addendum in `docs/guides/LOOPS_GUIDE.md` general-task section noting the plan-vs-DoD cross-check.

### Configuration
- N/A — no `.ll/ll-config.json` keys required.

## Implementation Steps

1. Edit `define_done.action` in `scripts/little_loops/loops/general-task.yaml` to require runtime-verification criteria when applicable (Change 1).
2. Edit `check_done.action` to read both DoD and plan, reconcile plan-vs-DoD coverage, update both files, and append a `## Sample Verification` section re-checking up to 3 already-`[x]` criteria (Change 2).
3. Edit `continue_work.action` to fall back to "find first unchecked DoD criterion, append a remediation plan step, complete it" when the plan is fully `[x]` (Change 3).
4. Replace `check_done.evaluate.prompt` with the structural 3-point check over action output (Change 4).
5. Run `ll-loop validate general-task` to confirm the YAML still parses.
6. Run `ll-loop --show-diagrams general-task` to confirm transitions render correctly (no transition changes expected).
7. Live re-run on a small task and on a runtime-surface task; inspect the action log to confirm the `## Sample Verification` section is written and the evaluator reads it.
8. Run the contrived oscillation test (unverifiable added criterion + fully-`[x]` plan) and confirm `continue_work` adds a remediation step instead of spinning.
9. Re-read `general-task-loop-audit-mc-vault.txt` and confirm the failure mode is now blocked at Change 1, 2, or 4.

If step 7 or 8 surfaces a deeper oscillation pattern beyond what Change 3 handles, stop and refine [[BUG-1628]] rather than expanding scope here.

## Scope Boundaries

- **In scope**: Four in-place edits to `scripts/little_loops/loops/general-task.yaml` (`define_done.action`, `check_done.action`, `continue_work.action`, `check_done.evaluate.prompt`).
- **Out of scope**: Adding a separate `verify` state — strengthening `check_done` in place avoids duplicating the action body and complicating routing.
- **Out of scope**: External DoD/plan template files — inline prompts are consistent with the current loop and the rest of `loops/*.yaml`.
- **Out of scope**: Runtime/evaluator changes in `scripts/little_loops/fsm/`. The existing `llm_structured` evaluator is sufficient *because* verification is being pushed into the `check_done` action body where tools are available.
- **Out of scope**: Closing [[BUG-1628]] (plan exhaustion) or [[ENH-1629]] (explicit thresholds) — mention them in the commit body as adjacent.
- **Out of scope (this pass)**: Raising `min_confidence` and adding `uncertain_suffix: _uncertain` to `check_done.evaluate`. Tracked as an optional follow-up because it changes routing semantics.

## Success Metrics

- A `general-task` run on a task with a runtime surface produces a DoD that includes at least one runtime criterion.
- A run cannot reach `done` while any plan step is unchecked — `check_done` either fills the DoD gap and re-verifies, or the evaluator answers NO.
- Re-running the mc-vault scenario (or an equivalent runtime-surface task) blocks the phantom-success path observed in `general-task-loop-audit-mc-vault.txt`.

## Impact

- **Priority**: P2 — correctness fix to a flagship loop; an observed failure produced a falsely-`done` run.
- **Effort**: Small — four YAML string edits in a single file; no runtime, schema, or template changes.
- **Risk**: Low — additive prompt language; existing transitions and states unchanged. The added `continue_work` fallback (Change 3) is what keeps the new `check_done` reconciliation (Change 2) from interacting badly with the existing single-step continue_work behavior. Worst-case impact is more iterations before `done` for runtime-surface tasks, not regressions on file-only tasks.
- **Breaking Change**: No.

## Source

User-provided plan: `~/.claude/plans/review-the-audit-of-wiggly-candle.md`. Underlying audit artifact: `general-task-loop-audit-mc-vault.txt` (mc-vault project). The plan is a transient working doc; the durable record lives here.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `general-task`, `correctness`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-05-23T21:59:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P2
