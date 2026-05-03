---
id: ENH-1339
type: ENH
priority: P3
status: open
discovered_date: 2026-05-02
completed_at: 2026-05-03T18:08:34Z
discovered_by: research-synthesis
related:
- ENH-1337
- ENH-1338
decision_needed: false
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1339: Per-Issue Refinement Budget Cap in `recursive-refine`

## Summary

`recursive-refine` re-routes a single issue through `refine-to-ready-issue → check_passed → detect_children → recheck_scores → run_size_review → enqueue_or_skip → dequeue_next` per attempt, but if size-review produces children that themselves fail and decompose, *the same root issue ID could indirectly consume dozens of iterations through its descendants*. Add a hard per-issue attempt counter so any individual ID that enters the sub-loop more than `max_refine_count` times (canonical config: `commands.max_refine_count`, currently 5) is flagged, skipped with reason `budget-exceeded`, and surfaced in the summary.

## Motivation

2026 research on agent failure modes converges on per-task budget caps as a stop condition independent from global iteration limits:

- "Every agent run needs a hard cap on the number of thought steps … if the goal isn't reached, the agent terminates with an error" ([fixbrokenaiapps 2026](https://www.fixbrokenaiapps.com/blog/ai-agents-infinite-loops)).
- Microsoft's CORPGEN explicitly assigns multi-horizon task budgets and escalates rather than continuing to retry ([MarkTechPost CORPGEN coverage 2026](https://www.marktechpost.com/2026/02/26/microsoft-research-introduces-corpgen-to-manage-multi-horizon-tasks-for-autonomous-ai-agents-using-hierarchical-planning-and-memory/)).
- Anthropic's "Building Effective Agents" emphasizes giving "the smallest amount of freedom that still delivers the outcome" — implying tight per-task ceilings ([Anthropic 2026](https://www.anthropic.com/research/building-effective-agents)).

Our `context.max_refine_count: 5` exists in the YAML but is currently *unused* by `recursive-refine` itself — it is referenced as canonical config but nothing in the loop reads it. This issue makes that ceiling enforced.

## Current Behavior

- `context.max_refine_count: 5` is declared at `recursive-refine.yaml:27` but never consumed by any state in the loop.
- Each issue's path through the FSM is unbounded except by the global `max_iterations: 500`.
- An issue that fails refine, gets decomposed by size-review, and has its children fail and re-decompose can indirectly consume the entire global budget.

## Expected Behavior

- New tracking file: `.loops/tmp/recursive-refine-attempts.txt` with one line per attempt: `issue_id`.
- `dequeue_next` (or the start of `run_refine`) increments a counter for the current ID.
- A new gate state `check_attempt_budget` between `dequeue_next` and `capture_baseline` checks whether the current ID's attempt count has exceeded `max_refine_count`; if so, append to `recursive-refine-skipped-budget.txt` and route to `dequeue_next` (skip this issue's processing entirely).
- `done` summary shows `Skipped (budget N): IDs...` when applicable.
- Configuration honored via `commands.max_refine_count` in `.ll/ll-config.json`.

## Proposed Solution

1. In `parse_input`, add `printf '' > .loops/tmp/recursive-refine-attempts.txt`.
2. Insert `check_attempt_budget` state between `dequeue_next` and `capture_baseline`:
   ```yaml
   check_attempt_budget:
     action: |
       python3 << 'PYEOF'
       import json, sys
       from pathlib import Path
       issue_id = '${captured.input.output}'
       cfg = {}
       p = Path('.ll/ll-config.json')
       if p.exists():
           try: cfg = json.loads(p.read_text()).get('commands', {})
           except Exception: pass
       cap = cfg.get('max_refine_count', ${context.max_refine_count})
       attempts_file = '.loops/tmp/recursive-refine-attempts.txt'
       try:
           lines = Path(attempts_file).read_text().splitlines()
       except FileNotFoundError:
           lines = []
       count = sum(1 for ln in lines if ln.strip() == issue_id)
       if count >= cap:
           Path('.loops/tmp/recursive-refine-skipped-budget.txt').open('a').write(issue_id + '\n')
           sys.exit(1)  # over budget
       with open(attempts_file, 'a') as f:
           f.write(issue_id + '\n')
       sys.exit(0)
       PYEOF
     fragment: shell_exit
     on_yes: capture_baseline
     on_no: dequeue_next
     on_error: dequeue_next
   ```
3. Update `dequeue_next.on_yes` from `capture_baseline` to `check_attempt_budget`.
4. Extend `done` summary to include the budget-skipped list.

## Acceptance Criteria

- [x] `context.max_refine_count` is actually consumed by the loop (currently unused).
- [x] Per-issue attempt count is tracked in a file under `.loops/tmp/`.
- [x] `check_attempt_budget` skips an issue once its attempts ≥ cap and records reason `budget`.
- [x] `done` summary includes a `Skipped (budget N): IDs...` line when applicable.
- [x] Test: a synthetic issue that always fails its sub-loop produces exactly `max_refine_count` attempts and then is budget-skipped.

## Scope Boundaries

- **In scope**: per-issue attempt counter, gate state, summary reporting.
- **Out of scope**: total cost/token budget across the run — that belongs in a separate proposal tied to `ll-loop`'s rate-limit infrastructure.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — `parse_input` (init attempts file), insert `check_attempt_budget` state, rewire `dequeue_next.on_yes`, extend `done`.

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — update description of `commands.max_refine_count` property (currently says "via sub-loop delegation"; after this change, recursive-refine enforces it directly via `check_attempt_budget`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — loop runner; consumes the YAML.
- `scripts/tests/test_loops_recursive_refine.py` — must verify the budget cap fires.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` — delegates to `recursive-refine` as a sub-loop; reads `recursive-refine-skipped.txt`, which gains a new writer (`check_attempt_budget`) — no code change required but the write-contract is extended
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `refine_issue` state uses `loop: recursive-refine`; `get_passed_issues` reads `recursive-refine-skipped.txt` — same file-contract extension as above
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — `refine_issue` state uses `loop: recursive-refine` with `context_passthrough: true`; `get_passed_issues` reads `recursive-refine-skipped.txt` — same file-contract extension
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — `refine_unresolved` state uses `loop: recursive-refine` with `context_passthrough: true`; does not read any recursive-refine tmp files post-return, so no behavioral change

### Similar Patterns
- Any FSM gate state with `fragment: shell_exit` and `on_yes` / `on_no` / `on_error` routing — see other states in `recursive-refine.yaml` for the exact convention.

### Tests
- `scripts/tests/test_loops_recursive_refine.py` — new test exercising a synthetic issue that always fails its sub-loop, asserting exactly `max_refine_count` attempts and a `budget` skip.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — UPDATE: `TestRecursiveRefineLoop.test_required_states_exist` (add `"check_attempt_budget"` to `required` set, line ~1614); ADD: `test_dequeue_next_routes_to_check_attempt_budget` asserting `dequeue_next.on_yes == "check_attempt_budget"` and `test_check_attempt_budget_routes_to_capture_baseline` asserting `check_attempt_budget.on_yes == "capture_baseline"`
- `scripts/tests/test_loops_recursive_refine.py` — UPDATE: `TestDoneSummary._DONE_SCRIPT` (lines ~511–537) must include `recursive-refine-skipped-budget.txt` read and `Skipped (budget N):` printf line; ADD new test methods `test_budget_line_shows_budget_ids` and `test_budget_line_shows_none_when_no_budget_issues` in `TestDoneSummary`

### Documentation
- `docs/reference/loops/recursive-refine.md` (if present) — document the now-enforced `max_refine_count`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — section `recursive-refine — Depth-First Issue Refinement with Decomposition`: (1) update FSM flow diagram to show `dequeue_next → check_attempt_budget → [budget ok?] → capture_baseline`; (2) add `Skipped (budget N): IDs...` to summary output example; (3) update `max_refine_count` row in context variables table to reflect direct enforcement via `check_attempt_budget`; (4) add `recursive-refine-attempts.txt` and `recursive-refine-skipped-budget.txt` to the Notes file list
- `docs/reference/CONFIGURATION.md` — section `commands`: update description of `max_refine_count` row (currently says "enforced ... via sub-loop delegation"; after this change, `recursive-refine` enforces it directly)
- `skills/configure/areas.md` — `Area: commands` section, "Max refines" question description: minor wording update to reflect direct enforcement in the outer loop

### Configuration
- `.ll/ll-config.json` — `commands.max_refine_count` already canonical; ensure schema documents it.

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — `commands.max_refine_count` property description (line ~382–388): update text from "enforced by the `refine-to-ready-issue` loop and by `recursive-refine` via sub-loop delegation" to reflect direct enforcement via `check_attempt_budget`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/loops/recursive-refine.yaml:63–85` — `dequeue_next` state (exact block to rewire: `on_yes: capture_baseline` → `on_yes: check_attempt_budget`)
- `scripts/little_loops/loops/recursive-refine.yaml:87–103` — `capture_baseline` state (insertion target; new `check_attempt_budget` goes between these two)
- `scripts/little_loops/loops/recursive-refine.yaml:452–481` — `done` state (terminal; read pattern from existing depth/cycle skip lines)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:34` — `check_lifetime_limit` (closest cross-run counter analog; uses `ll-issues refine-status --json` for durable counts and `cfg.get('commands', {}).get('max_refine_count', ${context.max_refine_count})` config-read pattern)
- `scripts/little_loops/loops/recursive-refine.yaml:328` — `check_depth` (closest structural analog for the budget gate; double-writes to both a reason-specific skip file and `recursive-refine-skipped.txt`)
- `scripts/tests/test_loops_recursive_refine.py:211` — `_check_depth_script(current_id, max_depth)` helper (template for `_check_attempt_budget_script`; returns bash string, parameterised by issue ID and cap value)
- `scripts/tests/test_loops_recursive_refine.py:225` — `TestCheckDepth` class (template for `TestCheckAttemptBudget`; `_setup()` pattern, tmp-file assertions)

## Implementation Steps

1. Initialize `.loops/tmp/recursive-refine-attempts.txt` in `parse_input`.
2. Insert the `check_attempt_budget` gate between `dequeue_next` and `capture_baseline`, reading `commands.max_refine_count` with fallback to `context.max_refine_count`.
3. Rewire `dequeue_next.on_yes` from `capture_baseline` to `check_attempt_budget`.
4. Append the current ID to the attempts file each pass; route to skipped with reason `budget` once count ≥ cap.
5. Extend `done` with a `Skipped (budget N): IDs...` line when the budget skip file is non-empty.
6. Add a synthetic test verifying exact `max_refine_count` attempts before budget skip.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 correction — initialize two files, not one:**
`parse_input` must clear both the attempts tracker and the budget-skip list (per `check_depth` precedent for `skipped-depth.txt`):
```bash
printf '' > .loops/tmp/recursive-refine-attempts.txt
printf '' > .loops/tmp/recursive-refine-skipped-budget.txt
```

**Step 2 corrections — two bugs in the proposed Python snippet:**
- Use `with open(...)` instead of `Path(...).open('a').write(...)` (unclosed file handle):
  ```python
  with open('.loops/tmp/recursive-refine-skipped-budget.txt', 'a') as f:
      f.write(issue_id + '\n')
  ```
- Also write to `recursive-refine-skipped.txt` (global skip list), mirroring `check_depth:352–353`:
  ```python
  with open('.loops/tmp/recursive-refine-skipped.txt', 'a') as f:
      f.write(issue_id + '\n')
  ```

**Step 5 — `done` state double-dollar escaping:**
All bash variable expansions inside YAML `action:` strings must use `$${}` to escape FSM interpolation (e.g., `$${BUDGET_LIST:-none}`). The existing depth/cycle skip lines at `recursive-refine.yaml:460–478` show this exact pattern. Failure to double the dollar sign causes silent empty substitution.

**Step 6 — test helper pattern** (`test_loops_recursive_refine.py:211` `_check_depth_script` template):
Add a module-level `_check_attempt_budget_script(issue_id, max_count)` helper returning the inlined Python gate script as a bash heredoc string. `TestCheckAttemptBudget` should assert: (a) below cap → exit 0, no skip-file write, attempts file grows; (b) at cap → exit 1, writes to both `skipped-budget.txt` and `skipped.txt`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/tests/test_builtin_loops.py` — add `"check_attempt_budget"` to `TestRecursiveRefineLoop.test_required_states_exist` required set; add structural routing assertions `test_dequeue_next_routes_to_check_attempt_budget` and `test_check_attempt_budget_routes_to_capture_baseline`
8. Update `TestDoneSummary._DONE_SCRIPT` in `scripts/tests/test_loops_recursive_refine.py` — extend the inline script to read `recursive-refine-skipped-budget.txt` and emit `Skipped (budget N): IDs...`; add `test_budget_line_shows_budget_ids` and `test_budget_line_shows_none_when_no_budget_issues` test methods
9. Update `docs/guides/LOOPS_GUIDE.md` — FSM flow diagram, summary output example, `max_refine_count` context var description, Notes file list (add two new `.loops/tmp/` files)
10. Update `docs/reference/CONFIGURATION.md` — revise `max_refine_count` description to reflect direct enforcement
11. Update `config-schema.json` — revise `commands.max_refine_count` property description to replace "via sub-loop delegation" with "directly by `check_attempt_budget` in `recursive-refine`"
12. Update `skills/configure/areas.md` — minor wording for "Max refines" enforcement description

## Impact

- **Priority**: P3 — Adds enforcement to an already-declared but unused config knob; defensive rather than urgent.
- **Effort**: Small — One new gate state plus a one-line `parse_input` change and a one-line `dequeue_next` rewire.
- **Risk**: Low — Default cap (5) is unlikely to trip on healthy issues; trips already imply runaway.
- **Breaking Change**: No — Behavior only diverges for issues that would have looped indefinitely.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `recursive-refine`, `fsm-loops`, `safety`, `config`

## Resolution

Implemented all acceptance criteria. Added `check_attempt_budget` gate state between `dequeue_next` and `capture_baseline` in `recursive-refine.yaml`. The state reads `commands.max_refine_count` from `ll-config.json` (fallback to `context.max_refine_count`), tracks per-issue attempt counts in `.loops/tmp/recursive-refine-attempts.txt`, and writes budget-exceeded IDs to both `recursive-refine-skipped-budget.txt` and the shared `recursive-refine-skipped.txt`. The `done` summary now includes a `Skipped (budget N): IDs...` line. All 7 new tests pass (4 in `TestCheckAttemptBudget`, 2 in `TestDoneSummary`, and routing assertions in `test_builtin_loops.py`). Documentation updated across `LOOPS_GUIDE.md`, `CONFIGURATION.md`, `config-schema.json`, and `areas.md`.

## Status

**Completed** | Created: 2026-05-02 | Priority: P3

## References

- `scripts/little_loops/loops/recursive-refine.yaml:27` — `max_refine_count` declaration (currently unused).
- `scripts/little_loops/loops/recursive-refine.yaml:63` (`dequeue_next`) and `:87` (`capture_baseline`) — insertion points.
- 2026 research: [Anthropic Building Effective Agents](https://www.anthropic.com/research/building-effective-agents), [Microsoft CORPGEN](https://www.marktechpost.com/2026/02/26/microsoft-research-introduces-corpgen-to-manage-multi-horizon-tasks-for-autonomous-ai-agents-using-hierarchical-planning-and-memory/).


## Session Log
- `/ll:ready-issue` - 2026-05-03T18:01:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eeb05989-bb52-4f97-a9e6-6cfc0bf7e810.jsonl`
- `/ll:confidence-check` - 2026-05-03T18:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4f5b42c3-e8ef-47a4-b2b9-4b91bb35d4b7.jsonl`
- `/ll:wire-issue` - 2026-05-03T17:57:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae7f0997-427e-458f-95b4-c226b92b17c5.jsonl`
- `/ll:refine-issue` - 2026-05-03T17:51:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/64c39cda-d1f7-426c-bbff-5c05ec002ffb.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:format-issue` - 2026-05-03T04:41:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a41e2fe5-b6da-449b-8d60-6b8ddd06d97c.jsonl`
