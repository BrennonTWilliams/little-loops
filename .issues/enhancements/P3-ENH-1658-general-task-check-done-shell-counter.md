---
captured_at: "2026-05-23T16:40:11Z"
discovered_date: 2026-05-23
discovered_by: capture-issue
status: open
depends_on: BUG-1628
---

# ENH-1658: Replace general-task `check_done` LLM evaluator with a shell counter

## Summary

The `general-task` loop's `check_done` state currently uses an `llm_structured` evaluator to confirm a deterministic, mechanical property: "all DoD criteria are `[x]`, all plan steps are `[x]`, and the Sample Verification section has no FAILED entries." That is a checkbox-counting task — exactly the shape `dead-code-cleanup.yaml`'s `count_findings` state already solves with `action_type: shell` + `evaluate: output_json`. Replacing the LLM gate with a shell counter removes LLM judgment from the termination decision, eliminates one model call per iteration, and makes the success contract auditable from the loop YAML alone.

## Current Behavior

`scripts/little_loops/loops/general-task.yaml:83-142` defines `check_done` as a prompt-action followed by an `llm_structured` evaluator:

- The prompt asks the model to re-read both files, verify each criterion by evidence, write a `## Sample Verification` section, and print the final DoD/plan to stdout.
- The evaluator reads that stdout and answers YES iff (1) all DoD criteria are `[x]`, (2) all plan steps are `[x]`, (3) the Sample Verification section has no FAILED entries.

All three of those checks are pure string parsing over two markdown files — no judgment required. The current LLM evaluator can drift, hallucinate a YES, or hallucinate a NO; it costs a model call per iteration; and the bar lives inside the prompt rather than in the YAML.

## Expected Behavior

`check_done` is split into two states:

1. **`check_done`** (existing prompt action, lightly trimmed) — still asks the model to verify by evidence, mark criteria `[x]`/`[ ]`, and append the Sample Verification section. No `evaluate:` block; routes unconditionally to the new shell state.
2. **`count_done`** (new shell state, modeled on `dead-code-cleanup.yaml`'s `count_findings`) — parses `.loops/tmp/general-task-dod.md` and `.loops/tmp/general-task-plan.md`, emits a single JSON object summarizing remaining work, and uses `evaluate: output_json` to route deterministically:
   - `on_yes: done` when all criteria pass.
   - `on_no: continue_work` when anything remains.
   - `on_error: diagnose` if either file is missing or malformed.

The contract becomes machine-readable: "zero unchecked DoD criteria, zero unchecked plan steps, zero FAILED sample-verification entries."

## Motivation

- **Removes LLM judgment from a deterministic gate.** The "is this checkbox `[x]`?" question doesn't benefit from a language model; it benefits from `grep -c`. The current evaluator can flip YES/NO based on prompt drift even when the underlying files are unchanged.
- **One fewer model call per iteration.** Over a 100-iteration cap, that's 100 fewer calls. The shell state runs in milliseconds.
- **Audit-friendly.** `/ll:audit-loop-run` can quote the JSON output (`{"unchecked_dod": 2, "unchecked_plan": 0, "failed_samples": 1}`) directly instead of inferring pass/fail from the evaluator's prose.
- **Pairs with [[BUG-1628]].** Once the plan-exhaustion deadlock is fixed, the success contract still needs to be unambiguous — a shell counter is the clean way to express it.

Precedent: `scripts/little_loops/loops/dead-code-cleanup.yaml:28-46` already uses this pattern (`grep -c` → JSON → `output_json` evaluator → terminate on count == 0). This issue applies the same pattern to general-task.

## Proposed Solution

Replace the `evaluate:` block on `check_done` with a routed transition to a new `count_done` shell state.

```yaml
check_done:
  action_type: prompt
  action: |
    # unchanged — still writes DoD updates and the Sample Verification section
    ...
  next: count_done
  on_error: diagnose

count_done:
  action_type: shell
  action: |
    DOD=".loops/tmp/general-task-dod.md"
    PLAN=".loops/tmp/general-task-plan.md"
    if [ ! -f "$DOD" ] || [ ! -f "$PLAN" ]; then
      echo '{"error": "missing artifact"}'
      exit 1
    fi
    # Count unchecked checkboxes in the Verification Criteria section
    UNCHECKED_DOD=$(awk '/^## Verification Criteria/,/^## /' "$DOD" \
      | grep -c '^[[:space:]]*-[[:space:]]*\[[[:space:]]\]' || true)
    UNCHECKED_PLAN=$(grep -c '^[[:space:]]*-[[:space:]]*\[[[:space:]]\]' "$PLAN" || true)
    # Count FAILED entries in the Sample Verification section (if present)
    FAILED_SAMPLES=$(awk '/^## Sample Verification/,0' "$DOD" \
      | grep -c 'FAILED' || true)
    printf '{"unchecked_dod": %d, "unchecked_plan": %d, "failed_samples": %d}\n' \
      "$UNCHECKED_DOD" "$UNCHECKED_PLAN" "$FAILED_SAMPLES"
  capture: done_counts
  evaluate:
    type: output_json
    # Pass only when all three counts are zero. If the FSM runtime supports
    # a sum/all-zero operator, prefer that; otherwise add a tiny shell-side
    # `total` field and compare `total == 0`.
    path: ".total"
    operator: eq
    target: 0
  on_yes: done
  on_no: continue_work
  on_error: diagnose
```

If `output_json` only supports comparing a single scalar path (the dead-code precedent uses `.count`), add `"total": UNCHECKED_DOD + UNCHECKED_PLAN + FAILED_SAMPLES` to the JSON and compare `.total == 0`. The individual fields still get captured for audit/diagnostics.

## Acceptance Criteria

- [ ] `check_done` state in `general-task.yaml` no longer has an `evaluate:` block; it routes unconditionally to `count_done`.
- [ ] New `count_done` state uses `action_type: shell`, emits a JSON object with at least `{unchecked_dod, unchecked_plan, failed_samples, total}`, and routes via `evaluate: output_json` against `.total == 0`.
- [ ] Existing routes (`on_no: continue_work`, `on_error: diagnose`, `on_yes: done`) are preserved on the new gate state, not on `check_done`.
- [ ] A test loop run where all DoD/plan boxes are `[x]` and no sample is FAILED terminates with `success` via `count_done`.
- [ ] A test loop run with one unchecked criterion routes to `continue_work` (not `done`).
- [ ] A test loop run with `general-task-dod.md` missing routes to `diagnose` (not silent success).
- [ ] `ll-loop validate scripts/little_loops/loops/general-task.yaml` passes.
- [ ] `docs/guides/LOOPS_GUIDE.md` general-task section documents the new two-state gate and the JSON output schema.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — split `check_done` into `check_done` (prompt) + `count_done` (shell), move routes to `count_done`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/` — verify `action_type: shell` + `evaluate: output_json` path works the same way it does for `dead-code-cleanup.yaml`. No runtime changes expected.
- `/ll:audit-loop-run` consumers — they currently look for the `check_done` evaluator output; update to read `count_done`'s captured JSON instead.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — validates all built-in loops by name/structure including `general-task.yaml`; no direct state-name assertion but run after the change to confirm no unexpected failures in `TestBuiltinLoopFiles` [Agent 1 finding]
- `skills/debug-loop-run/SKILL.md` — reads evaluate events from loop run history to detect failure patterns; after the change, evaluate events come from `count_done` (shell/output_json) instead of `check_done` (llm_structured) — behavioral shift in what the skill's signal detection sees [Agent 1 finding]
- `skills/audit-loop-run/SKILL.md` _(expanded detail)_ — Step 3 scans `evaluate.prompt` (no `prompt` key on `output_json` evaluator → finds nothing on `count_done`); Step 6 phantom-success rubric explicitly names `llm_structured` as the phantom-risk vector (no longer applies); Step 7 iterates only `evaluate.type: llm_structured` states for rubric checks and will silently skip `count_done`. Net effect: audit-loop-run's rubric pass becomes a no-op for general-task's terminal gate. A follow-up issue is recommended after this lands. [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/loops/dead-code-cleanup.yaml:28-46` — `count_findings` state: shell action emits `{"count": N}`, `output_json` evaluates `.count == 0`, routes to `done`/`remove_code`/`done` on yes/no/error. Direct model for this change.

### Tests
- Add a fixture under `scripts/tests/` exercising `count_done` in three cases: all-clean (→ done), unchecked criterion (→ continue_work), missing DoD (→ diagnose).
- `ll-loop validate` smoke test confirming the new YAML parses.

_Wiring pass added by `/ll:wire-issue`:_
- **File for new tests**: `scripts/tests/test_general_task_loop.py` — add new classes there (no new file); consistent with existing structure [Agent 3 finding]
  - `TestChange7CountDoneShellGate` — structural YAML assertions: `count_done.action_type == "shell"`, `evaluate.type == "output_json"`, `evaluate.path == ".total"`, `evaluate.operator == "eq"`, `evaluate.target == 0`, `on_yes == "done"`, `on_no == "continue_work"`, `on_error == "diagnose"` [Agent 3 finding]
  - `TestCountDoneShellScript` — shell execution via `_bash()` helper (model after `test_loops_recursive_refine.py:14`): 3 scenarios against tmp_path/.loops/tmp/ fixtures [Agent 3 finding]
  - `ll-loop validate general-task` smoke test — follow pattern in `test_builtin_loops.py:177` or `test_create_loop.py:52` [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — run after change; `TestBuiltinLoopFiles` validates all built-in loops and may surface unexpected failures [Agent 1 finding]

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Existing tests that will break and need updating** (`scripts/tests/test_general_task_loop.py`):
- `TestChange4CheckDoneEvaluatorStructural.test_evaluator_is_llm_structured` — asserts `check_done.evaluate["type"] == "llm_structured"`; after the change `check_done` has no `evaluate:` block
- `TestChange4CheckDoneEvaluatorStructural.test_evaluator_prompt_references_three_conditions` — accesses `check_done.evaluate["prompt"]`; key will not exist
- `TestChange4CheckDoneEvaluatorStructural.test_evaluator_routes_yes_to_done_no_to_continue` — asserts `check_done.on_yes == "done"` and `check_done.on_no == "continue_work"`; these routes move to `count_done`
- `TestGeneralTaskLoopFile.test_expected_states_present` — expected set must include `"count_done"` after the new state is added

Recommended fix: rename `TestChange4CheckDoneEvaluatorStructural` to `TestChange7CountDoneShellGate`, target `count_done` instead of `check_done`, and assert `evaluate.type == "output_json"`, `evaluate.path == ".total"`, `evaluate.operator == "eq"`, `evaluate.target == 0`, `on_yes == "done"`, `on_no == "continue_work"`, `on_error == "diagnose"`, and `action_type == "shell"`.

**Shell-execution test pattern** — model after `scripts/tests/test_loops_recursive_refine.py`:
- Module-level `_bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]` helper using `subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)`
- Class-level `_COUNT_DONE_SCRIPT` constant holding the exact shell snippet from the YAML state
- `_setup_dod_plan(tmp_path, *, dod_content, plan_content)` helper that writes `.loops/tmp/general-task-dod.md` and `.loops/tmp/general-task-plan.md`
- Add new class `TestCountDoneShellScript` to `scripts/tests/test_general_task_loop.py` (no new file needed — consistent with existing structure)

**`ll-loop validate` CLI pattern** (from `scripts/tests/test_create_loop.py`):
```python
import sys
from unittest.mock import patch
with patch.object(sys, "argv", ["ll-loop", "validate", "general-task"]):
    from little_loops.cli import main_loop
    result = main_loop()
assert result == 0
```

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — update the general-task section to describe the two-state gate, the JSON output, and that termination is deterministic.

_Wiring pass added by `/ll:wire-issue`:_
- `audit-general-task-2026-05-24.md` (repo root) — committed audit artifact; scorecard names `check_done` as the evaluator and timeline references `check_done → YES/NO` routing. Becomes factually stale. No code change required, but note this during implementation. [Agent 2 finding]

### Cleanup
_Wiring pass added by `/ll:wire-issue`:_
- `.issues/bugs/P2-BUG-794-check-done-llm-evaluator-json-parse-failure-in-general-task-loop.md` — this bug is entirely premised on `check_done` using an `llm_structured` evaluator that can fail JSON parsing. Removing `llm_structured` from `check_done` makes BUG-794 obsolete. Close/cancel as part of this implementation. [Agent 2 finding]

### Configuration
- N/A.

## Implementation Steps

1. ~~Read `dead-code-cleanup.yaml`'s `count_findings` state and confirm `output_json` semantics~~ — **Confirmed**: `evaluate_output_json()` in `scripts/little_loops/fsm/evaluators.py` accepts a single `path`/`operator`/`target` and does **not** support multi-field compound checks. The `total` pre-computation workaround in the Proposed Solution is required. Use `path: ".total"`, `operator: eq`, `target: 0` (matching the `.count` pattern in `dead-code-cleanup.yaml:41-43`).
2. Add `count_done` state to `general-task.yaml` per the snippet above; include a pre-computed `total` field (`TOTAL=$((UNCHECKED_DOD + UNCHECKED_PLAN + FAILED_SAMPLES))`) and set `evaluate.path: ".total"`.
3. Strip the `evaluate:` block from `check_done` (lines 128-139); set `next: count_done`.
4. Move `on_yes: done`, `on_no: continue_work`, `on_error: diagnose` from `check_done` (lines 140-142) onto `count_done`.
5. Update `scripts/tests/test_general_task_loop.py`:
   - Rename `TestChange4CheckDoneEvaluatorStructural` → `TestChange7CountDoneShellGate`; retarget all assertions to `count_done` state (see Tests section for specifics)
   - Add `"count_done"` to the expected set in `TestGeneralTaskLoopFile.test_expected_states_present`
   - Add `TestCountDoneShellScript` class with `_bash()` helper and three-scenario shell tests
6. Run `ll-loop validate scripts/little_loops/loops/general-task.yaml`.
7. Run `python -m pytest scripts/tests/test_general_task_loop.py -v` to confirm all tests pass.
8. Run `ll-loop run general-task` against a small task that terminates in 2-3 iterations to confirm the new gate fires correctly in the happy path.
9. Manually delete `.loops/tmp/general-task-dod.md` mid-run and confirm `count_done` routes to `diagnose`.
10. Update `docs/guides/LOOPS_GUIDE.md` — general-task section (around lines 309-340) to describe the two-state gate and JSON output schema `{unchecked_dod, unchecked_plan, failed_samples, total}`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` after the YAML change to confirm no unexpected failures in the built-in loop validation suite.
12. Cancel `.issues/bugs/P2-BUG-794-check-done-llm-evaluator-json-parse-failure-in-general-task-loop.md` — the `llm_structured` evaluator being removed from `check_done` makes this bug obsolete. Update its status to `cancelled` with a note referencing ENH-1658.
13. After landing, consider filing a follow-up issue for `skills/audit-loop-run/SKILL.md`: Steps 3/6/7 target `llm_structured` evaluators and will silently skip `count_done`'s `output_json` gate — the rubric-audit and phantom-success detection become no-ops for this state.

## Scope Boundaries

- **In scope**: Replacing the `llm_structured` evaluator on `check_done` with a deterministic shell counter modeled on `dead-code-cleanup.yaml`.
- **In scope**: Preserving the existing `check_done` prompt action (the model still writes the DoD updates and Sample Verification section — only the *gate* changes).
- **Out of scope**: Adding configurable `target_pass_rate` / `min_per_category` keys. The DoD contract is binary by design; partial-credit thresholds undermine the "Definition of Done" framing and were the wrong framing in this issue's original draft.
- **Out of scope**: Generalizing the shell-counter pattern to other loops in `scripts/little_loops/loops/`. This issue is scoped to `general-task` only.
- **Out of scope**: FSM runtime changes. If `output_json` lacks the operator we need, work around it in the shell (emit a pre-computed `total`) rather than extending the runtime here.

## Success Metrics

- A `general-task` run that completes all DoD criteria terminates via `count_done` in zero LLM calls (the shell action does the gate).
- `/ll:audit-loop-run` can quote `{unchecked_dod, unchecked_plan, failed_samples}` directly from the run log without re-parsing the DoD file.
- Zero observed cases of the gate flipping YES/NO between identical inputs (currently possible with the LLM evaluator).

## Impact

- **Priority**: P3 — quality and observability improvement; complements but does not block [[BUG-1628]].
- **Effort**: Small — one YAML state added, one `evaluate:` block removed, three routes moved, plus docs. Mirrors an existing pattern.
- **Risk**: Low — the prompt that writes the DoD updates is unchanged; only the gate parsing it changes. Failure mode is conservative (missing file → `diagnose`, not silent `done`).
- **Breaking Change**: No — the loop's external contract (DoD format, plan format, terminal states) is unchanged.

## Source

`general-task-audit-proposals.md` (Proposal 2) — originally captured as ENH-1629 ("add configurable thresholds to `check_done`"). Rewritten on 2026-05-23 after review concluded that (a) the current evaluator already enforces a 100% bar implicitly, (b) configurable partial-credit thresholds undermine the Definition-of-Done contract, and (c) the genuinely valuable change is replacing the LLM gate with a deterministic shell counter (the original issue's "Phase 2"). Refiled under ID 1658 to avoid conceptual collision with the committed ENH-1629 description in git history (`e995aba1 chore(issues): file ENH-1629 and ENH-1631 from general-task loop audit`). The proposals file is a transient working doc; the durable record lives here and in [[BUG-1628]].

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `general-task`, `captured`

## Session Log
- `/ll:wire-issue` - 2026-05-24T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/claude-session.jsonl`
- `/ll:refine-issue` - 2026-05-24T14:11:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/606cff41-42fc-4284-8565-e62f63b8909b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-23T20:59:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53f5ce8a-8802-4e4f-a82f-cb8f836c6b67.jsonl`
- `/ll:format-issue` - 2026-05-23T16:43:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7684c915-f5a2-4b68-9ba1-d56622191296.jsonl`
- `/ll:capture-issue` - 2026-05-23T16:40:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue restructures the gate following `check_done` in general-task.yaml. BUG-1628 restructures the `execute`/`continue_work` state actions in the same file. This issue `depends_on: BUG-1628` — let the structural fix land first (it changes what states exist and how iteration proceeds), then swap the LLM gate for a shell counter on top of the updated structure.
