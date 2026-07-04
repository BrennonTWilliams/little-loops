---
id: FEAT-1874
title: Extract implement-issue-chain sub-loop
type: FEAT
priority: P3
parent: ENH-1777
captured_at: '2026-06-02T00:00:00Z'
completed_at: '2026-06-02T06:45:16Z'
discovered_date: 2026-06-02
discovered_by: issue-size-review
decision_needed: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
status: done
---

# FEAT-1874: Extract implement-issue-chain sub-loop

## Summary

Extract the 5-state `implement-issue-chain` sequence shared by `auto-refine-and-implement.yaml` and `sprint-refine-and-implement.yaml` into a reusable sub-loop oracle, eliminating the explicitly-noted mirrored duplication between the two sprint loops.

## Parent Issue

Decomposed from ENH-1777: Wave 4 — Remaining Fragments, Sub-loops, and Flows

## Current Behavior

`auto-refine-and-implement.yaml` and `sprint-refine-and-implement.yaml` share an explicitly noted mirrored chain: `get_passed_issues → implement_next → go_no_go → implement_issue → skip_and_continue`. Both files carry a comment: _"NOTE: … are mirrored in sprint-refine-and-implement.yaml. Keep both files in sync when editing."_

The 5 states are structurally identical; only the queue-file prefix differs (`auto-refine-and-implement-` vs `sprint-refine-and-implement-`). Both use `.loops/tmp/` paths (not `${context.run_dir}/`), which triggers an MR-3 warning — cross-run sharing of `recursive-refine-passed.txt` is intentional and warrants `shared_state_ok: true`.

**Key structural details verified in source:**

- `get_passed_issues` (`fragment: shell_exit`) reads `.loops/tmp/recursive-refine-passed.txt` and `.loops/tmp/recursive-refine-skipped.txt`, populates `<prefix>-impl-queue.txt`
- `implement_next` (`fragment: shell_exit`, `capture: impl_id`) pops head from `<prefix>-impl-queue.txt` using `head`/`tail`/`mv` pattern
- `go_no_go` (`fragment: shell_exit`) calls `ll-action invoke go-no-go --args "${captured.impl_id.output} --check --auto"`
- `implement_issue` (`fragment: with_rate_limit_handling`) runs `ll-auto --only <id>` after a `.issues/completed/` guard; `next: implement_next`, `on_rate_limit_exhausted: done`
- `skip_and_continue` (plain shell, `next: get_next_issue`) appends `${captured.input.output}` to `<prefix>-skipped.txt` — note this references the OUTER loop's `get_next_issue` capture, not `impl_id`

The two callers also differ in how `refine_issue` calls `recursive-refine`:
- `auto-refine-and-implement.yaml`: `loop: recursive-refine` + `with: {input: "${captured.input.output}"}` (explicit binding)
- `sprint-refine-and-implement.yaml`: `loop: recursive-refine` + `context_passthrough: true` (implicit injection)
This difference is in `refine_issue`, which is NOT part of the 5 extracted states.

## Expected Behavior

- `implement-issue-chain` extracted as a shared sub-loop at `loops/oracles/implement-issue-chain.yaml`
- Both `auto-refine-and-implement.yaml` and `sprint-refine-and-implement.yaml` replace the 5 mirrored states with `loop:` delegation to the new oracle
- `shared_state_ok: true` at the oracle top level (queue files cross-run by design)
- All modified loops pass `ll-loop validate`

## Proposed Solution

### Option A: 4-state oracle (exclude `skip_and_continue`)

> **Selected:** Option A: 4-state oracle — extracts only the 4 "implement queue" states; `skip_and_continue` stays in each caller where it has legitimate access to `${captured.input.output}` from the outer loop, matching the established partial-extraction pattern used across all 6+ oracle callers.

Extract only the 4 "implement queue" states (`get_passed_issues`, `implement_next`, `go_no_go`, `implement_issue`) into the oracle. Keep `skip_and_continue` in each caller — it is 3 lines, changes only the file prefix, and is trivially readable in context.

**Oracle structure (`loops/oracles/implement-issue-chain.yaml`):**
```yaml
name: implement-issue-chain
description: |
  Oracle sub-loop that drains a recursive-refine passed-issues queue: reads
  recursive-refine-passed.txt, populates a caller-prefixed impl-queue, pops
  each issue, gates it through go-no-go, and runs ll-auto --only. Used by
  auto-refine-and-implement and sprint-refine-and-implement (ENH-1874).

initial: get_passed_issues
on_handoff: spawn
shared_state_ok: true

parameters:
  caller_prefix:
    type: string
    required: true
    description: "Prefix for queue/skip files, e.g. 'auto-refine-and-implement'"

import:
  - lib/common.yaml

states:
  get_passed_issues:   # fragment: shell_exit; uses .loops/tmp/${context.caller_prefix}-*.txt
  implement_next:      # fragment: shell_exit; capture: impl_id
  go_no_go:            # fragment: shell_exit; ll-action invoke go-no-go
  implement_issue:     # fragment: with_rate_limit_handling; on_rate_limit_exhausted: done
  done:
    terminal: true
  failed:
    terminal: true
```

**Caller delegation (auto):**
```yaml
refine_issue:
  loop: recursive-refine
  with:
    input: "${captured.input.output}"
  on_success: implement_chain
  on_failure: skip_and_continue
  on_error: skip_and_continue

implement_chain:
  loop: oracles/implement-issue-chain
  with:
    caller_prefix: "auto-refine-and-implement"
  on_success: get_next_issue
  on_failure: done
  on_error: done

skip_and_continue:    # ← stays in caller
  action: |
    echo "Skipping ${captured.input.output} after refinement failure"
    echo "${captured.input.output}" >> .loops/tmp/auto-refine-and-implement-skipped.txt
  action_type: shell
  next: get_next_issue
```

**Sprint caller:** same pattern with `caller_prefix: "sprint-refine-and-implement"` and `refine_issue` keeping `context_passthrough: true`.

### Option B: 5-state oracle with `route` gateway (full elimination)

Extract all 5 states. The oracle has `initial: route` — a gateway state that checks a `skip_mode` parameter and branches to `skip_and_continue` (when `"true"`) or `get_passed_issues` (when `"false"`). Each caller routes both `refine_issue.on_success` and `refine_issue.on_failure` to the oracle via two delegation states with different `skip_mode` bindings.

**Oracle `parameters:` block (Option B):**
```yaml
parameters:
  caller_prefix:
    type: string
    required: true
    description: "Prefix for queue/skip files"
  input:
    type: string
    required: true
    description: "Outer-loop issue ID (for skip_and_continue); same as captured.input.output in caller"
  skip_mode:
    type: string
    required: false
    description: "Set to 'true' to skip directly to skip_and_continue (refinement failed)"
```

**Caller (Option B):**
```yaml
refine_issue:
  loop: recursive-refine
  with:
    input: "${captured.input.output}"
  on_success: implement_chain
  on_failure: skip_chain
  on_error: skip_chain

implement_chain:
  loop: oracles/implement-issue-chain
  with:
    caller_prefix: "auto-refine-and-implement"
    input: "${captured.input.output}"
    skip_mode: "false"
  on_success: get_next_issue
  on_failure: done
  on_error: done

skip_chain:
  loop: oracles/implement-issue-chain
  with:
    caller_prefix: "auto-refine-and-implement"
    input: "${captured.input.output}"
    skip_mode: "true"
  on_success: get_next_issue
  on_failure: get_next_issue
  on_error: get_next_issue
```

Option B completely eliminates all duplication but adds a `route` state and two delegation states per caller (vs one in Option A).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-02.

**Selected**: Option A: 4-state oracle (exclude `skip_and_continue`)

**Reasoning**: All 6+ existing oracle callers retain tail states that reference outer-loop context — `skip_and_continue`'s dependency on `${captured.input.output}` (an outer-loop variable never passed to the oracle) is structurally identical to why those tail states stay in callers elsewhere. Option A reuses the `enumerate-and-prove` template exactly (parameters block, `on_handoff: spawn`, `shared_state_ok: true`, `TestEnumerateAndProveOracle` test class) with zero novel infrastructure. Option B introduces four patterns absent from the entire oracle corpus: `initial: route`, `skip_mode` parameter branching, two delegation states per caller, and `source: "${context.skip_mode}"` evaluator — none with a single precedent.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (4-state oracle) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B (5-state + route) | 0/3 | 1/3 | 1/3 | 1/3 | 3/12 |

**Key evidence**:
- Option A: Every existing oracle caller retains local tail states for context-specific routing (html-website-generator, adopt-third-party-api, integrate-sdk, etc.); `caller_prefix` string parameter matches enumerate-and-prove/generator-evaluator parameters blocks exactly; `TestEnumerateAndProveOracle` at test_builtin_loops.py:5232 is a direct 1:1 template.
- Option B: Zero existing oracles use `initial: route`; zero use parameter-controlled entry branching; zero oracle callers use two delegation states to the same oracle; `source: "${context.skip_mode}"` has no instances across all 30+ existing evaluator `source:` fields.

## Integration Map

### Files to Create
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` — new sub-loop oracle

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — replace 5 mirrored states with `loop:` delegation; `refine_issue.on_success` → `implement_chain`; `skip_and_continue` stays (Option A) or becomes oracle call (Option B)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — same replacement; preserve `context_passthrough: true` on `refine_issue` (this state is NOT extracted)

### Reference Patterns
- `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml` — canonical oracle structure: `parameters:`, `on_handoff: spawn`, `import: [lib/common.yaml]`, terminal states `done`/`failed`
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — oracle with `context:` defaults for optional parameters, `import: [lib/harness.yaml]`
- `scripts/little_loops/loops/lib/common.yaml` — provides `shell_exit` fragment (used by `get_passed_issues`, `implement_next`, `go_no_go`) and `with_rate_limit_handling` fragment (used by `implement_issue`)
- `scripts/little_loops/loops/adopt-third-party-api.yaml` — caller using `loop: oracles/enumerate-and-prove` with `with:` bindings (reference delegation syntax)
- `scripts/little_loops/loops/prompt-across-issues.yaml` — sole existing `shared_state_ok: true` usage in built-in loops

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:49` — comment marks start of mirrored block
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:57` — same mirror comment

### Tests
- `scripts/tests/test_builtin_loops.py`:
  - `TestAutoRefineAndImplementLoop` (line 1199) — 19 methods asserting the 5 extracted states (e.g., `test_required_states_exist` at line 1215 expects `get_passed_issues`, `implement_next`, etc. in `states`); these break post-delegation and must be updated
  - `TestSprintRefineAndImplementLoop` (line 1359) — 5 methods; `test_required_states_exist` at line 1369 expects `implement_next`, `implement_issue`; breaks post-delegation
  - `test_expected_loops_exist` (line 66) — uses `BUILTIN_LOOPS_DIR.glob("*.yaml")` (non-recursive, top-level only); oracle is NOT in this set; no change needed here
  - `builtin_loops` fixture (line 26) — `BUILTIN_LOOPS_DIR.glob("*.yaml")` should become `BUILTIN_LOOPS_DIR.rglob("*.yaml")` filtered by `is_runnable_loop()` so oracle files pass `test_all_validate_as_valid_fsm`, `test_all_have_description_field`, etc.
  - Add `TestImplementIssueChainOracle` class following `TestEnumerateAndProveOracle` pattern (line 5232): `LOOP_FILE = BUILTIN_LOOPS_DIR / "oracles/implement-issue-chain.yaml"`, `test_required_top_level_fields`, `test_has_parameters_block`, `test_done_is_terminal`, `test_imports_common_yaml`, `test_get_passed_issues_reads_recursive_refine_outputs`, etc.
  - `test_impl_queue_file_uses_loops_tmp` (line 1339): scans all states for `"auto-refine-and-implement-impl-queue"`; after extraction the reference moves to the oracle so this assertion's `found` guard will fail — either delete this test or move it to `TestImplementIssueChainOracle` [Wiring pass finding]
  - Fixture update in step 6 requires `from little_loops.fsm import is_runnable_loop` added to the imports at the top of `test_builtin_loops.py` (not currently imported there) [Wiring pass finding]
- `scripts/tests/test_doc_counts.py`:
  - Add `test_implement_issue_chain_is_runnable()` to `TestIsRunnableLoop` class following `test_enumerate_and_prove_is_runnable` pattern (line 151)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — Contains inline FSM flow diagrams for both `auto-refine-and-implement` (around line 689) and `sprint-refine-and-implement` (around line 651) that show the extracted states (`implement_next → go_no_go → implement_issue`) as inline nodes; these diagrams will be stale after extraction and must show the `implement_chain` delegation state instead [Agent 2 finding]
- `scripts/little_loops/loops/README.md` — Oracle Sub-loops section (lines 148–156); add `implement-issue-chain` entry

## Implementation Steps

1. **Read and diff the two source loops** (`auto-refine-and-implement.yaml`, `sprint-refine-and-implement.yaml`) to confirm the exact 5 states are byte-for-byte identical except for the caller-prefix substitution. The current diff:
   - `auto` prefix: `auto-refine-and-implement-` (skipped.txt, impl-queue.txt)
   - `sprint` prefix: `sprint-refine-and-implement-`
   - `skip_and_continue`: appends to `${captured.input.output}` → same logic, different prefix file

2. **Decide Option A vs Option B** (see Proposed Solution) — run `/ll:decide-issue ENH-1874` to select before implementing.

3. **Create `loops/oracles/implement-issue-chain.yaml`**:
   - Follow `enumerate-and-prove.yaml` top-level structure: `name`, `description`, `initial`, `on_handoff: spawn`, `shared_state_ok: true`, `parameters:`, `import: [lib/common.yaml]`, `states:`
   - Copy the 4 shared state bodies from `auto-refine-and-implement.yaml`, replacing the hardcoded prefix strings with `${context.caller_prefix}` interpolation
   - For Option B: add `route` as `initial:` and a `skip_and_continue` state with `${context.input}` replacing `${captured.input.output}`
   - Verify terminal states: `done` (success, `on_rate_limit_exhausted` in `implement_issue` routes here), `failed` (unused but required for oracle interface)

4. **Update `auto-refine-and-implement.yaml`**:
   - Delete states `get_passed_issues`, `implement_next`, `go_no_go`, `implement_issue`
   - Update `refine_issue.on_success` → `implement_chain` (new delegation state)
   - Add `implement_chain` delegation state with `loop: oracles/implement-issue-chain`, `with: {caller_prefix: "auto-refine-and-implement"}`
   - Option A: keep `skip_and_continue` as-is (rename its skip-file path if using `${context.caller_prefix}` — no, it stays hardcoded)
   - Option B: delete `skip_and_continue`, add `skip_chain` delegation state; update `refine_issue.on_failure/on_error` → `skip_chain`
   - Remove the `# NOTE: ... mirrored` comment

5. **Update `sprint-refine-and-implement.yaml`**:
   - Same changes as step 4 with `caller_prefix: "sprint-refine-and-implement"`
   - `refine_issue` keeps `context_passthrough: true` (unchanged — this state is not being extracted)
   - Remove the `# NOTE: ... mirrored` comment

6. **Update tests in `test_builtin_loops.py`**:
   - `TestAutoRefineAndImplementLoop.test_required_states_exist` (line 1215): remove `get_passed_issues`, `implement_next`, `implement_issue`, `skip_and_continue` from `required` set; add `implement_chain`
   - `TestAutoRefineAndImplementLoop.test_refine_issue_has_success_and_failure_routes` (line 1276): update `on_success` assertion from `"get_passed_issues"` to `"implement_chain"`
   - Optionally remove or update the per-state assertion methods that target the extracted states
   - Add `test_implement_chain_delegates_to_oracle` method
   - Update `TestSprintRefineAndImplementLoop.test_required_states_exist` (line 1369): remove `implement_next`, `implement_issue`; add `implement_chain`
   - Fix `builtin_loops` fixture (line 26): `BUILTIN_LOOPS_DIR.glob("*.yaml")` → `[p for p in BUILTIN_LOOPS_DIR.rglob("*.yaml") if is_runnable_loop(p)]` (import `is_runnable_loop` from `little_loops.fsm`)
   - Add `TestImplementIssueChainOracle` class

7. **Add `test_implement_issue_chain_is_runnable` to `test_doc_counts.py`** following `test_enumerate_and_prove_is_runnable` at line 151.

8. **Run `ll-loop validate`** on all three YAML files.

9. **Run tests**: `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_doc_counts.py -v --tb=short`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `docs/guides/LOOPS_GUIDE.md` — replace the inline FSM flow diagram nodes for `implement_next → go_no_go → implement_issue` in both the `auto-refine-and-implement` (≈line 689) and `sprint-refine-and-implement` (≈line 651) sections with a `implement_chain → [oracle]` delegation node showing the sub-loop handoff
11. Delete or relocate `TestAutoRefineAndImplementLoop.test_impl_queue_file_uses_loops_tmp` (line 1339) — this test scans parent states for the impl-queue path reference, which moves into the oracle; if kept, move the assertion into `TestImplementIssueChainOracle`
12. Add `from little_loops.fsm import is_runnable_loop` import to `test_builtin_loops.py` — required for the `builtin_loops` fixture update to `rglob + is_runnable_loop` filter

## Scope Boundaries

- Extracts only the 4 "implement queue" states (`get_passed_issues`, `implement_next`, `go_no_go`, `implement_issue`) per Option A decision
- `skip_and_continue` stays in each caller — it references `${captured.input.output}` from the outer loop scope, which is not passed to the oracle
- The `refine_issue` state is NOT extracted — it differs between callers (`with:` explicit binding in auto vs `context_passthrough: true` in sprint)
- No changes to `recursive-refine` oracle or any other existing oracle/caller
- No new evaluator types, routing logic, or FSM features introduced

## Success Metrics

- `implement-issue-chain` oracle eliminates 5 duplicated states across 2 sprint loops (Option A: 4 states in oracle + `skip_and_continue` stays in callers; Option B: all 5)
- All modified and new loops pass `ll-loop validate`
- `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_doc_counts.py -v --tb=short` passes

## Impact

- **Priority**: P3 — Reduces maintenance burden; eliminates explicit "keep in sync" comment between two sprint loops
- **Effort**: Small — Follows established `enumerate-and-prove` oracle pattern exactly; straightforward prefix substitution
- **Risk**: Low — Well-established oracle pattern with comprehensive test coverage; no novel infrastructure
- **Breaking Change**: No — Callers updated in-place to delegate via `loop:` state; external behavior unchanged

## Labels

`enhancement`, `loops`, `refactoring`

## Status

**Open** | Created: 2026-06-02 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-02T06:38:15 - `53a471c8-cc99-4bc3-8990-ed0d4aab3a55.jsonl`
- `/ll:decide-issue` - 2026-06-02T06:32:24 - `e9d49176-8407-499e-96ee-6725a13a2117.jsonl`
- `/ll:confidence-check` - 2026-06-02T08:00:00 - `98147cba-e407-482b-9dd8-fc8d2460b271.jsonl`
- `/ll:confidence-check` - 2026-06-02T12:00:00 - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
- `/ll:wire-issue` - 2026-06-02T06:22:50 - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
- `/ll:refine-issue` - 2026-06-02T06:17:58 - `01491322-6ce5-4de7-b288-7d8bb4e7ee3e.jsonl`
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
