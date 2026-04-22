---
id: ENH-1243
type: ENH
priority: P3
title: "Add decide-issue conditional gate to autodev loop"
status: backlog
captured_at: "2026-04-21T23:34:57Z"
completed_at: "2026-04-22T18:37:15Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
decision_needed: false
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1243: Add decide-issue gate to autodev loop

## Summary

The `autodev` loop refines and implements issues end-to-end, but has no hook for issues
that carry `decision_needed: true` after refinement. Such issues currently fall through
to `implement_current` with an unresolved multi-option proposed solution, which produces
inconsistent or incorrect implementations. A conditional `decide_current` state should be
inserted between confidence-check and implementation so the `/ll:decide-issue` skill runs
exactly when — and only when — the flag is set.

## Current Behavior

After `check_passed` routes to `implement_current`, the loop calls `ll-auto --only <ID>`
regardless of whether the issue's frontmatter contains `decision_needed: true`. Issues
with competing implementation options are implemented without a winner being selected,
leaving the choice to the implementing agent at random.

## Expected Behavior

When `check_passed` (or `recheck_scores` / `recheck_after_size_review`) routes toward
implementation, the loop first checks whether the issue has `decision_needed: true`. If
so, it runs `/ll:decide-issue <ID> --auto`, which selects a winning option and clears the
flag. Only after that does it call `ll-auto --only <ID>`. Issues without the flag skip
the new state entirely with zero overhead.

## Motivation

`/ll:refine-issue --auto` deliberately sets `decision_needed: true` when it can't pick
between two valid approaches without codebase evidence. The `decide-issue` skill was
built to close that gap. Without a gate in `autodev`, the refinement → decision →
implementation pipeline is broken: the middle step is silently skipped, and the quality
guarantee of the whole loop degrades.

## Proposed Solution

Add a `decide_current` state to `autodev.yaml` positioned between all three
implementation-routing states and `implement_current`:

```
check_passed        → on_yes: decide_current   (was: implement_current)
recheck_scores      → on_yes: decide_current   (was: implement_current)
recheck_after_size_review → on_yes: decide_current (was: implement_current)

decide_current:
  action: |
    ISSUE_ID="${captured.input.output}"
    FLAG=$(ll-issues show "$ISSUE_ID" --json \
      | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('decision_needed','false'))")
    [ "$FLAG" = "true" ] && exit 0 || exit 1
  fragment: shell_exit
  on_yes: run_decide   # decision needed → run the skill
  on_no:  implement_current

run_decide:
  fragment: with_rate_limit_handling
  action: "/ll:decide-issue ${captured.input.output} --auto"
  action_type: slash_command
  next: implement_current
  on_error: implement_current        # degraded: proceed even if decide fails
  on_rate_limit_exhausted: done
```

The `on_error: implement_current` fallback ensures a decide-skill failure doesn't silently
drop the issue; it still gets implemented (with the unresolved options), which is no worse
than the current behavior.

### Codebase Research Findings — Bug in `decide_current` Shell

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`ll-issues show --json` does NOT expose `decision_needed`** — `show.py:_parse_card_fields()`
(lines 101–247) only extracts `confidence`, `outcome`, `effort`, `risk`, `labels`, `path`, and
related fields. The proposed `d.get('decision_needed','false')` call would always return `'false'`,
so the gate would never fire. Two options exist:

**Option A — Read the issue file directly (no `show.py` changes):**

```yaml
decide_current:
  action: |
    ISSUE_ID="${captured.input.output}"
    ISSUE_FILE=$(ll-issues path "$ISSUE_ID")
    FLAG=$(python3 -c "
    import sys, yaml
    content = open('$ISSUE_FILE').read()
    parts = content.split('---')
    fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
    print('true' if fm.get('decision_needed') is True else 'false')
    " 2>/dev/null || echo 'false')
    [ "$FLAG" = "true" ] && exit 0 || exit 1
  fragment: shell_exit
  on_yes: run_decide
  on_no:  implement_current
```

Follows the file-based flag pattern used by `check_broke_down` (`autodev.yaml:257–280`) and
requires no changes outside `autodev.yaml`.

**Option B — Extend `ll-issues show --json` to expose `decision_needed`:**
> **Selected:** Option B — autodev.yaml already uses `ll-issues show --json` for issue metadata (3 call sites); Option B aligns `decide_current` with that pattern. Option A introduces inline YAML frontmatter parsing with no loop-YAML precedent.

Modify `show.py:_parse_card_fields()` (line 101) to extract and include `decision_needed` from
frontmatter — consistent with how `issue_manager.py:562–578` and `scripts/little_loops/parallel/worker_pool.py:372–383` already
handle this field. This enables the original proposed shell script verbatim and makes the field
available to any future shell-based tooling, but adds scope beyond `autodev.yaml` alone.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-04-22.

**Selected**: Option B — Extend `ll-issues show --json` to expose `decision_needed`

**Reasoning**: `autodev.yaml` already calls `ll-issues show <id> --json` via Python subprocess three times (lines 144–145, 304–305, 415–416) — this is the established pattern for reading issue metadata in loop YAML files. Option B makes `decide_current` use that same pattern, while Option A would introduce inline YAML frontmatter parsing with no precedent in any loop YAML file. Option B requires exactly two new lines in `_parse_card_fields()` following the identical `frontmatter.get("field")` + return-dict pattern already used 10+ times in that function, whereas Option A adds a new data-access approach that diverges from the file's conventions without reducing scope.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (file read) | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |
| Option B (show --json) | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |

**Key evidence**:
- **Option A**: `ll-issues path` has zero call sites in any loop YAML file; the claimed `check_broke_down` model reads a temp numeric flag, not YAML frontmatter; inline `yaml.safe_load` is a new loop-YAML pattern
- **Option B**: `_parse_card_fields()` already uses `frontmatter.get()` + string coercion 10+ times; `IssueInfo.to_dict()` already serializes `decision_needed` (`issue_parser.py:284`); exact test pattern exists at `test_issues_cli.py:1737–1776`

## Integration Map

- **Modified**: `scripts/little_loops/loops/autodev.yaml`
  - States `check_passed`, `recheck_scores`, `recheck_after_size_review`: change
    `on_yes` target from `implement_current` to `decide_current`
  - New states: `decide_current`, `run_decide`
- **Consumed skill**: `skills/decide-issue/SKILL.md` — invoked via `run_decide`
- **Issue frontmatter field**: `decision_needed` (boolean) — read by `decide_current`
  check; cleared by `decide-issue` on success

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact state locations in `autodev.yaml`:**
- `check_passed` — lines 121–163 → `on_yes: implement_current` becomes `on_yes: decide_current`
- `recheck_scores` — lines 282–323 → `on_yes: implement_current` becomes `on_yes: decide_current`
- `recheck_after_size_review` — lines 393–439 → `on_yes: implement_current` becomes `on_yes: decide_current`
- `implement_current` — line 165 (insertion target for new states)

**Pattern models:**
- `run_size_review` (`autodev.yaml:325–336`) — exact structural model for `run_decide` (slash_command + `with_rate_limit_handling` fragment + non-fatal `on_error`)
- `check_wire_done` + `wire_issue` (`refine-to-ready-issue.yaml:81–103`) — two-state conditional gate pattern (shell check → skill runner)

**Fragment definitions:**
- `shell_exit` — `scripts/little_loops/loops/lib/common.yaml:14–19`
- `with_rate_limit_handling` — `scripts/little_loops/loops/lib/common.yaml:49–62`

**`decision_needed` reading precedents (Python):**
- `issue_parser.py:414–422` — parses boolean + string coercion for `decision_needed`
- `issue_manager.py:562–578` — existing `decide-issue` gate (ll-auto sequential path)
- `scripts/little_loops/parallel/worker_pool.py:372–383` — existing `decide-issue` gate (ll-parallel path)

**Tests to update:**
- `scripts/tests/test_builtin_loops.py:TestAutodevLoop` (~line 1009) — add `decide_current` and `run_decide` to `test_required_states_exist`; add routing assertions for all three modified states and new states
- `test_builtin_loops.py:test_all_validate_as_valid_fsm` — automatically covers updated `autodev.yaml`; no changes needed
- `test_fsm_fragments.py:TestBuiltinLoopMigration` (~line 873) — automatically covers fragment resolution; no changes needed

**Option B only — if extending `ll-issues show --json`:**
- `scripts/little_loops/cli/issues/show.py:_parse_card_fields()` line 101 — add `decision_needed` extraction from frontmatter and include in output dict
- `scripts/tests/test_issues_cli.py` — add test for `decision_needed` presence in `show --json` output

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:1141–1144` — `test_check_passed_on_yes_routes_to_implement_current` asserts `on_yes == "implement_current"`; **will break** — rename and update assertion to `"decide_current"`
- `scripts/tests/test_builtin_loops.py:1335–1341` — `test_recheck_after_size_review_on_yes_routes_to_implement_current` asserts `on_yes == "implement_current"`; **will break** — rename and update assertion to `"decide_current"`
- `scripts/tests/test_builtin_loops.py` (`TestAutodevLoop`) — `recheck_scores.on_yes` routing has **no test** in `TestAutodevLoop` (only `TestRecursiveRefineLoop` at line 1360 tests `recursive-refine.yaml`'s copy of that state); add a new method asserting `recheck_scores.on_yes == "decide_current"` — follow the `test_recheck_after_size_review_on_yes_*` pattern at line 1327
- `scripts/tests/test_builtin_loops.py` (`TestAutodevLoop`) — new test methods needed for `decide_current`: assert `fragment == "shell_exit"`, `on_yes == "run_decide"`, `on_no == "implement_current"` — mirror `test_recheck_after_size_review_uses_shell_exit_fragment` pattern at line 1327
- `scripts/tests/test_builtin_loops.py` (`TestAutodevLoop`) — new test methods needed for `run_decide`: assert `fragment == "with_rate_limit_handling"`, `next == "implement_current"`, `on_error == "implement_current"`, `on_rate_limit_exhausted == "done"` — mirror `TestRecursiveRefineLoop.test_run_size_review_uses_auto_flag` pattern at line 1457

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:447–460` — FSM flow diagram for autodev shows `YES → implement_current` on all three score-pass branches (`check_passed`, `recheck_scores`, `recheck_after_size_review`); must be updated to interpose `decide_current → run_decide` on each YES branch
- `docs/reference/ISSUE_TEMPLATE.md:887` — `decision_needed` field description names `ll-auto` and `ll-parallel` but not `ll-loop run autodev`; optional minor prose addition

## Implementation Steps

1. In `autodev.yaml:121`, `autodev.yaml:282`, and `autodev.yaml:393`, change `on_yes: implement_current`
   to `on_yes: decide_current` in `check_passed`, `recheck_scores`, and `recheck_after_size_review`.
2. Add `decide_current` state (after `check_passed` ~line 163): shell script that reads
   `decision_needed` from the issue file — see Option A or Option B in Proposed Solution above;
   uses `shell_exit` fragment (`lib/common.yaml:14–19`), `on_yes: run_decide`, `on_no: implement_current`.
3. Add `run_decide` state (after `decide_current`): model after `run_size_review` (`autodev.yaml:325–336`);
   `action_type: slash_command`, `fragment: with_rate_limit_handling`, `next: implement_current`,
   `on_error: implement_current`, `on_rate_limit_exhausted: done`.
4. In `scripts/tests/test_builtin_loops.py:TestAutodevLoop` (~line 1009):
   - Add `"decide_current"` and `"run_decide"` to `test_required_states_exist`
   - Add routing assertions: `check_passed.on_yes → decide_current`, `recheck_scores.on_yes → decide_current`,
     `recheck_after_size_review.on_yes → decide_current`, `decide_current.on_yes → run_decide`,
     `decide_current.on_no → implement_current`, `run_decide.on_error → implement_current`
   - (Optional B) Add `test_issues_cli.py` test for `decision_needed` in `show --json` output
5. Run `python -m pytest scripts/tests/test_builtin_loops.py::TestAutodevLoop -v` to validate routing.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Fix two breaking test methods in `scripts/tests/test_builtin_loops.py:TestAutodevLoop` — rename `test_check_passed_on_yes_routes_to_implement_current` (line 1141) and `test_recheck_after_size_review_on_yes_routes_to_implement_current` (line 1335); update their `on_yes` assertions from `"implement_current"` to `"decide_current"`
7. Add missing `recheck_scores.on_yes` routing test to `TestAutodevLoop` — assert `recheck_scores.on_yes == "decide_current"` (currently untested in `TestAutodevLoop`; `TestRecursiveRefineLoop` tests only the `recursive-refine.yaml` copy of this state)
8. Update `docs/guides/LOOPS_GUIDE.md:447–460` — revise the autodev FSM flow diagram to show `YES → decide_current → [decision_needed?] → run_decide / implement_current` on each of the three score-pass branches

## Scope Boundaries

- **In scope**: `autodev.yaml` state machine changes only — two new states (`decide_current`, `run_decide`) and three one-line routing updates
- **In scope**: Test updates in `test_builtin_loops.py:TestAutodevLoop` to cover new states and updated routing
- **In scope** (Option B only): `show.py:_parse_card_fields()` extension and `test_issues_cli.py` update
- **Out of scope**: Changes to `ll-auto`, `ll-parallel`, or `issue_manager.py` — those paths already handle `decision_needed` natively
- **Out of scope**: `decide-issue` skill changes — consumed as-is
- **Out of scope**: `refine-to-ready-issue.yaml` or other loop state machines

## Impact

- **Scope**: `autodev.yaml` only — two new states, three one-line routing changes
- **Risk**: Low — `on_error` fallback ensures no regressions for existing issues
- **Benefit**: Closes the refinement → decision → implementation pipeline gap; prevents
  under-specified issues from reaching the implementer

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/loops/autodev.yaml` | State machine being modified |
| `skills/decide-issue/SKILL.md` | Skill invoked by the new gate |

## Labels

loop, autodev, decide-issue, issue-pipeline

---

## Status

- [ ] Backlog
- [ ] In Progress
- [x] Complete

## Resolution

Implemented Option B (extend `ll-issues show --json`):
- `show.py:_parse_card_fields()` — added `decision_needed` extraction and lowercase string serialization
- `autodev.yaml` — added `decide_current` and `run_decide` states; updated `on_yes` in `check_passed`, `recheck_scores`, `recheck_after_size_review` to route through `decide_current`
- `test_builtin_loops.py:TestAutodevLoop` — added 9 new test methods, renamed 2 to reflect `decide_current` routing; added both new states to `test_required_states_exist`
- `test_issues_cli.py` — added `test_show_json_includes_decision_needed`
- `docs/guides/LOOPS_GUIDE.md` — updated FSM flow diagram to show `decide_current → run_decide` gate on all three score-pass branches

## Session Log
- `/ll:manage-issue` - 2026-04-22T18:37:15Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff12b2b-2ed2-40bc-9248-ba889878465e.jsonl`
- `/ll:ready-issue` - 2026-04-22T18:30:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3d1afef0-2ad2-480b-929e-eecd285e5996.jsonl`
- `/ll:decide-issue` - 2026-04-22T18:26:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10304d65-395d-4a6f-91a9-4ef370cc19b9.jsonl`
- `/ll:ready-issue` - 2026-04-22T18:18:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71ae5b90-f0ea-4333-8a81-7db60405635f.jsonl`
- `/ll:verify-issues` - 2026-04-22T18:13:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2b72ccf9-bc3b-4af0-a50e-d3ff002c1428.jsonl`
- `/ll:ready-issue` - 2026-04-22T00:19:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/24f9e1a8-4114-4c8d-aaaf-ac1ea1c113cf.jsonl`
- `/ll:confidence-check` - 2026-04-21T23:34:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/478870ac-71bc-41d2-80b3-aa270a1b9eb5.jsonl`
- `/ll:wire-issue` - 2026-04-22T00:13:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e770ce0-5b30-4d3b-9f04-66af39488a12.jsonl`
- `/ll:refine-issue` - 2026-04-22T00:08:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ba3ffa8-30aa-45f5-b019-215ca2aa1b61.jsonl`
- `/ll:capture-issue` - 2026-04-21T23:34:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b62f8c-b061-414c-9935-ffe01637b6ec.jsonl`
