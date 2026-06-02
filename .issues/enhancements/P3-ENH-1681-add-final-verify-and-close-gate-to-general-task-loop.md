---
captured_at: '2026-05-24T17:30:41Z'
completed_at: '2026-05-24T21:42:46Z'
discovered_date: 2026-05-24
discovered_by: capture-issue
status: done
decision_needed: false
relates_to:
- ENH-1644
- ENH-1671
- ENH-1656
- ENH-1676
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1681: Add final verify-and-close gate to general-task loop

## Summary

Add a `final_verify` state to `scripts/little_loops/loops/general-task.yaml` that runs once between `count_done`'s `on_yes` edge and the `done` terminal state. It performs a single comprehensive re-verification of **every** DoD criterion (not the 3-item sample) and routes back to `continue_work` if any criterion fails re-verification. This closes the residual "stale [x] mark" gap that ENH-1644's sample re-verification cannot fully cover on long DoDs.

## Current Behavior

After ENH-1644 (done 2026-05-24), the loop has the following terminal path:

1. `check_done.action` does delta-scoped verification (criteria touching `LAST_STEP` / `LAST_FILES`) + reconciles plan-vs-DoD coverage + samples up to `min(3, total_checked)` already-`[x]` criteria for re-verification.
2. `count_done` runs a shell counter (`grep -c '- [ ]'` style) — if zero unchecked items AND zero failed samples, routes `on_yes: done`.
3. `done` is `terminal: true` with no further verification.

Failure mode: on a DoD with N criteria (the audited mc-vault run had 75), only **3** are independently re-verified per iteration. A criterion marked `[x]` at iteration 5 whose underlying evidence rotted by iteration 40 (e.g., a file was later deleted/moved by a downstream step, a test that initially passed now fails) is never re-checked unless it happens to be in the random sample window or unless `LAST_STEP`/`LAST_FILES` plausibly touched it. The shell counter only counts boxes; it does not audit them. The loop can therefore terminate `done` with an honestly-counted set of `[x]` marks where some are stale.

## Expected Behavior

A new `final_verify` state interposed between `count_done` and `done`:

- Triggers exactly once per successful completion (on the `count_done → done` edge).
- Re-verifies **every** DoD criterion independently (filesystem read / command run / file content check), not a sample.
- Appends a `## Final Verification` section to the DoD file with per-criterion pass/fail evidence.
- If all pass → routes to `done`.
- If any fail → flips the failing criteria back to `[ ]` with a one-line failure note, then routes to `continue_work`. The next iteration's `check_done` + `count_done` will see the new `[ ]` marks and the loop resumes normally.

False-positive completion is structurally prevented: terminal `done` always implies every DoD criterion was re-verified end-to-end in the same iteration.

## Motivation

- **Residual gap from ENH-1644.** That issue's Scope Boundaries explicitly excluded "a separate `verify` state" on the grounds that strengthening `check_done` in place avoids duplication. The rationale held for *replacing* `check_done`, but does not apply to a *terminal-gate* addition that runs only on the success edge.
- **Sample-only verification is statistically insufficient on long DoDs.** With 3 samples per iteration on a 75-criterion DoD, the per-iteration chance of catching any specific stale `[x]` is 4%. Over ~10 verify cycles before terminal, the cumulative miss probability for a specific rotted criterion is still >65%. For multiple rotted criteria, miss probability compounds further.
- **Low ongoing cost.** Runs once per successful run, not per iteration. The amortized cost over a 20–100-iteration loop is negligible.
- **False-positive completion is the worst failure mode.** A loop that runs longer is recoverable; a loop that lies about being done is not. The mc-vault audit (`general-task-loop-audit-mc-vault.txt`, surfaced in ENH-1644) is exactly this class of failure.
- **Aligns with the "non-LLM evaluator required" design rule** for meta-loops (`.claude/CLAUDE.md` § Loop Authoring). general-task is not strictly a meta-loop, but the underlying concern about LLM self-grading bias (~33–55% accurate per SHOR) applies whenever an LLM is the sole judge of "are we done." Pairing the LLM `check_done` with a final-pass full sweep increases evidence diversity at the terminal boundary.

## Proposed Solution

Single-file change: `scripts/little_loops/loops/general-task.yaml`.

### State additions

```yaml
count_done:
  # ... existing config ...
  on_yes: final_verify   # was: done
  on_no: continue_work
  on_error: diagnose

final_verify:
  action: |
    Your task is: ${context.input}

    Read ${env.PWD}/.loops/tmp/general-task-dod.md.

    For EVERY criterion in the Verification Criteria section, independently
    re-verify it now by reading files / running commands / checking filesystem
    state. Do NOT trust the existing [x] mark — verify from evidence.

    Append a new section to the DoD file in this exact format:
    ```
    ## Final Verification
    - [x] <criterion>: <evidence>
    - [x] <criterion>: <evidence>
    - [ ] <criterion>: FAILED — <what happened>
    ```

    For any criterion that fails re-verification, flip its mark in the
    Verification Criteria list from [x] back to [ ] with a one-line note
    "(final_verify: failed — <reason>)".

    Print the full DoD file to stdout.
  action_type: prompt
  next: count_final
  on_error: diagnose

count_final:
  action: |
    DOD=".loops/tmp/general-task-dod.md"
    FAILED=$(awk '
      /^## Final Verification/ { in_section=1; count=0; next }
      in_section && /FAILED/ { count++ }
      END { print count+0 }
    ' "$DOD")
    printf '{"failed_finals": %d}\n' "$FAILED"
  action_type: shell
  capture: final_counts
  evaluate:
    type: output_json
    path: ".failed_finals"
    operator: eq
    target: 0
  on_yes: done
  on_no: continue_work
  on_error: diagnose
```

### Note on `count_final` awk correctness

The awk resets `count=0` each time it matches `## Final Verification`, not just `in_section=1`. This is intentional: if the loop passes through `final_verify` more than once (a prior pass failed, work continued, a second pass ran), the DoD file accumulates multiple `## Final Verification` sections. Without resetting `count`, old failures from earlier passes would compound into the final tally, permanently routing back to `continue_work` even after a clean second sweep. Resetting on the header ensures only the **most recent** section is evaluated.

### Rationale for two states (action + counter) rather than one

Mirrors the existing `check_done` / `count_done` split. The action is a prompt with tools; the counter is a non-LLM shell evaluator. Keeps the same trust pattern: LLM gathers evidence, shell decides routing. Avoids re-introducing the LLM-self-grade bias the project deliberately removed from `check_done` (ENH-1658).

### Why route failures to `continue_work` rather than a new state

`continue_work` already handles the "DoD criterion unchecked, plan fully `[x]`" case (Case B added in ENH-1644). A failed `final_verify` produces exactly that state shape — flipped-back DoD entries with a fully-checked plan — so `continue_work` Case B handles remediation without new logic.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — change `count_done.on_yes` from `done` to `final_verify` (line 203); add `final_verify` (prompt action) and `count_final` (shell evaluator) states after `count_done`. Also update `diagnose.action` text (line ~244) which lists states by name (`"define_done, plan, execute, check_done, or continue_work"`) — add `final_verify` and `count_final` to that list so the diagnose prompt is accurate.
- `scripts/tests/test_general_task_loop.py` — four targeted changes:
  1. `TestGeneralTaskLoopFile.test_expected_states_present` (lines 53–67): add `"final_verify"` and `"count_final"` to the `expected` set.
  2. `TestChange7CountDoneShellGate.test_count_done_routes_yes_to_done` (lines 178–180): update assertion from `== "done"` to `== "final_verify"`.
  3. Add new class `TestChange8FinalVerifyGate` with state-shape assertions mirroring `TestChange7CountDoneShellGate`: `final_verify` is `action_type: prompt`, routes `next: count_final`; `count_final` is `action_type: shell`, `evaluate.type: output_json`, `evaluate.path: ".failed_finals"`, `evaluate.operator: eq`, `evaluate.target: 0`, `on_yes: done`, `on_no: continue_work`, `on_error: diagnose`, `capture: final_counts`.
  4. Add new class `TestCountFinalShellScript` mirroring `TestCountDoneShellScript` (lines 360–411): extract shell body via a `_load_count_final_script()` helper (same pattern as `_load_count_done_script()` at lines 269–277), use `_setup_dod_plan()` fixtures; test cases: clean Final Verification section → `failed_finals == 0`; one FAILED entry → `failed_finals == 1`; two accumulated sections → only most-recent section counted (verifying `count=0` reset); missing DoD → non-zero exit.
- `docs/guides/LOOPS_GUIDE.md` — two changes: (a) update the sentence at line ~340 that says "`total == 0` → `done`" — this routing now goes to `final_verify`, not `done`; (b) append a paragraph after the current step 5 / closing paragraph (lines 343–345) describing the terminal gate: `final_verify` re-verifies every criterion, `count_final` routes to `done` on zero failures or back to `continue_work` on any failure.
- `skills/create-loop/loop-types.md` — "Partial DoD Satisfaction Threshold" section (line ~945) contains "`total == 0` routes to `done`" — update routing description to `final_verify`. [Wiring pass added by `/ll:wire-issue`]
- `CHANGELOG.md` — add new entry for ENH-1681 under the current release section, following the pattern of prior `general-task` enhancement entries. [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)
- N/A — `general-task.yaml` is loaded by the FSM runtime via path resolution; no direct imports.

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml` `check_done` + `count_done` split — exact pattern being reused for `final_verify` + `count_final`.
- ENH-1644's `## Sample Verification` markdown convention — `## Final Verification` uses the identical section format for consistency.

### Tests
- `scripts/tests/test_general_task_loop.py` — extend per above.
- `scripts/tests/test_builtin_loops.py` — generic validation should pass unchanged (one more state, two more transitions).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — general-task section; two changes needed (see Files to Modify above).
- `skills/create-loop/loop-types.md` — "Partial DoD Satisfaction Threshold (`general-task` loops)" section says `total == 0 → done`; stale after ENH-1681, must reflect `final_verify` routing.
- `CHANGELOG.md` — new entry for ENH-1681 following the pattern of prior general-task enhancement entries (e.g., ENH-1644, ENH-1658, ENH-1671 entries).

### Configuration
- N/A — no `.ll/ll-config.json` keys added.

## Implementation Steps

1. Edit `scripts/little_loops/loops/general-task.yaml`:
   - Change `count_done.on_yes` from `done` to `final_verify` (line 203).
   - Append `final_verify` (prompt, `action_type: prompt`, `next: count_final`, `on_error: diagnose`) and `count_final` (shell, `action_type: shell`, `capture: final_counts`, `evaluate.type: output_json`, `evaluate.path: ".failed_finals"`, `on_yes: done`, `on_no: continue_work`, `on_error: diagnose`) after the `count_done` block.
2. Run `ll-loop validate general-task` and `ll-loop show general-task` to confirm parse and transition diagram.
3. Extend `scripts/tests/test_general_task_loop.py`:
   - `TestGeneralTaskLoopFile.test_expected_states_present` (lines 53–67): add `"final_verify"` and `"count_final"` to the expected set.
   - `TestChange7CountDoneShellGate.test_count_done_routes_yes_to_done` (lines 178–180): update assertion from `== "done"` to `== "final_verify"`.
   - Add `TestChange8FinalVerifyGate` class with per-attribute assertions for both new states.
   - Add `TestCountFinalShellScript` class with shell-execution tests using `_setup_dod_plan()` and a new `_load_count_final_script()` helper (same extraction pattern as `_load_count_done_script()`, lines 269–277).
4. Update `docs/guides/LOOPS_GUIDE.md` general-task section (insert after lines 343–345) with a one-paragraph description of the terminal gate.
5. Live re-run on a small file-only task — confirm `## Final Verification` section is appended and loop reaches `done`.
6. Contrived failure test: seed an unverifiable criterion that initially marks `[x]` — confirm `final_verify` flips it back, `count_final` routes to `continue_work`, and the loop resumes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. In the same YAML edit as step 1: update `diagnose.action` prompt text (line ~244 of `general-task.yaml`) which names states as `"define_done, plan, execute, check_done, or continue_work"` — append `final_verify` and `count_final` so the diagnose prompt accurately reflects all states that can route there.
8. In the LOOPS_GUIDE.md edit (step 4): update the sentence at line ~340 that currently says "`total == 0` → `done`" to say "`total == 0` → `final_verify`" — this sentence describes the `count_done` routing contract and is factually stale after the rewire.
9. Update `skills/create-loop/loop-types.md` — "Partial DoD Satisfaction Threshold (`general-task` loops)" section: change the routing description "`total == 0` routes to `done`" to "`total == 0` routes to `final_verify`".
10. Add `CHANGELOG.md` entry for ENH-1681 under the current release section, following the pattern of prior `general-task` enhancement entries.

## Scope Boundaries

- **In scope**: Two-state addition (`final_verify` + `count_final`) wired between `count_done.on_yes` and `done`.
- **Out of scope**: Replacing or restructuring `check_done` — its delta-scoped + sample verification continues to run every iteration as the cheap per-iteration check. `final_verify` is additive, not a substitute.
- **Out of scope**: Splitting `check_done` into "verify (collect evidence)" and "translate (flip marks)" states — discussed during capture, deemed speculative; revisit only if observed evidence of LLM mismarking inside `check_done`.
- **Out of scope**: Externalizing DoD/plan templates.
- **Out of scope**: Changing the `final_verify` action to a non-LLM evaluator. The LLM is still required because DoD criteria are free-form ("dry-run exits 0", "file X contains Y") and need an LLM to translate each to the right verification command.
- **Out of scope**: Capping iterations differently or adding a max-final-verify-attempts circuit. Existing `max_iterations: 100` and `circuit.repeated_failure` cover runaway behavior.

## Success Metrics

- A `general-task` run with at least one rotted `[x]` mark (forced by a deletion of an asset between iterations) cannot reach `done` — `final_verify` flips the mark, `count_final` routes back to `continue_work`.
- Mean iteration cost increase on file-only tasks ≤ 1 extra iteration (the final-verify + count gate runs once).
- No regressions in `scripts/tests/test_general_task_loop.py` or `test_builtin_loops.py`.

## Impact

- **Priority**: P3 — quality enhancement that closes a residual gap; the bulk of the false-positive surface was already closed by ENH-1644. Not P2 because the gap is statistical (sample miss), not structural (a missing check).
- **Effort**: Small — one YAML edit (~30 lines added), one test file extension, one paragraph of doc.
- **Risk**: Low — purely additive; new states inserted on a single edge (`count_done.on_yes`). Failure path routes through existing `continue_work` (no new sink). Worst-case impact: one extra iteration per successful run on tasks that have no rotted marks.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `general-task`, `correctness`, `captured`

## Resolution

Implemented in `scripts/little_loops/loops/general-task.yaml`: changed `count_done.on_yes` from `done` to `final_verify`, added `final_verify` (prompt) and `count_final` (shell) states, updated `diagnose.action` state list. Extended `scripts/tests/test_general_task_loop.py` with `TestChange8FinalVerifyGate` and `TestCountFinalShellScript` classes (12 new tests). Updated `docs/guides/LOOPS_GUIDE.md` routing description and added terminal-gate paragraph. Updated `skills/create-loop/loop-types.md` routing description. Added CHANGELOG entry.

## Session Log
- `/ll:manage-issue` - 2026-05-24T21:42:46Z - active session
- `/ll:ready-issue` - 2026-05-24T21:39:28 - `50341109-15ff-4471-88eb-e57b32140fc3.jsonl`
- `/ll:confidence-check` - 2026-05-24T22:00:00Z - `ba5b7ded-8a4a-4c0f-95e1-c82128f42267.jsonl`
- `/ll:wire-issue` - 2026-05-24T21:36:03 - `5b7b6432-0e31-4d2b-af37-875c0d05728f.jsonl`
- `/ll:refine-issue` - 2026-05-24T21:29:26 - `a2d89ce4-36c3-4dc3-a3b0-5dfc218f3013.jsonl`
- `/ll:format-issue` - 2026-05-24T17:35:51 - `ea088c92-461b-4afc-98b8-32abc1e0bf8d.jsonl`
- `/ll:capture-issue` - 2026-05-24T17:30:41Z - `49190dcc-d6e4-4353-bf0c-cce367d61a96.jsonl`

---

**Open** | Created: 2026-05-24 | Priority: P3
