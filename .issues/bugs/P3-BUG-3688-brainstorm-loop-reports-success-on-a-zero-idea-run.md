---
id: BUG-3688
type: BUG
title: Brainstorm loop reports success on a zero-idea run
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T05:35:56Z'
completed_at: '2026-10-01T20:33:28Z'
verify_verdict: VALID
labels:
- loops
- brainstorm
relates_to:
- EPIC-3581
- FEAT-3582
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-3688: Brainstorm loop reports success on a zero-idea run

## Summary

The shipped `brainstorm` loop can finish `done` with **zero ideas**: `verify_artifacts` only checks that `brainstorm.md` is non-empty, and `converge` writes an honest "No synthesis produced" report that passes it. The 2026-07-01 run (`.loops/runs/brainstorm-20260701T202115`) produced 0 ideas (`lenses.txt` still held all 9 lenses, no `diverge` calls) and still succeeded, and sinks (`file`/`issue`/`decision`) can execute on it.

## Current Behavior

`verify_artifacts` only checks that `brainstorm.md` is non-empty, so a zero-idea run finishes `done` and sinks can execute.

## Expected Behavior

`verify_artifacts` (and the sinks' entry) fail the run to `finalize_failed` when `ideas.jsonl` is missing or has no valid idea rows. Minimal hotfix on the old loop, independent of the EPIC-3581 rewrite (whose `check_floors` / `validate_portfolio` supersede it); the rewrite may delete this check. Every little-loops project on this machine is `local-editable`, so the silent success stays live until FEAT-3582 lands.

## Steps to Reproduce

1. Run `ll-loop run brainstorm` with a brief that yields no ideas (the 2026-07-01 run, `.loops/runs/brainstorm-20260701T202115`, is the recorded case: `lenses.txt` still held all 9 lenses, no `diverge` calls).
2. Let the run reach `converge`, which writes an honest "No synthesis produced" report to `brainstorm.md`.
3. Observe: `verify_artifacts` passes on the non-empty `brainstorm.md`, the run ends in `done`, and any configured sink (`file`/`issue`/`decision`) has already executed.

## Root Cause

- **File**: `scripts/little_loops/loops/brainstorm.yaml`
- **Anchor**: `in states converge, route_sink, verify_artifacts`
- **Cause**: `ideas.jsonl` is created empty by `init` and appended only by `dedup_novelty`, which exits 0 on a zero-novel round (it only exits 2 on a crash). Nothing downstream inspects it: `cluster`, `rank` and `converge` are prompt states with unconditional `next:` edges, so a zero-idea run still reaches `converge`, which writes a non-empty `brainstorm.md` (and a `winners.md` holding an empty JSON array). `route_sink` is a `classify` state whose route table has no edge to `finalize_failed`, so `sink_file`/`sink_issue`/`sink_decision` all run before the only gate. `verify_artifacts` then checks `brainstorm.md` alone and routes to `finalize_done`.

## Proposed Solution

Add a shell guard state on the `converge` -> `route_sink` edge (`exit_code` evaluator, `on_yes: route_sink`, `on_no`/`on_error: finalize_failed`) that fails when `ideas.jsonl` is missing or has no non-blank rows; extend `verify_artifacts` with the same check (after the `brainstorm.md` check) as a self-sufficient terminal invariant; update `finalize_failed`'s diagnostic. See Program Design and Implementation Steps below.

## Program Design

### Signatures

- `verify_artifacts` (state in `scripts/little_loops/loops/brainstorm.yaml`) — shell action extended to exit 2 when `ideas.jsonl` is absent or has no non-blank rows, in addition to the existing `brainstorm.md` check.
- `route_sink` (same file) — gate the sink entry so an empty `ideas.jsonl` routes to `finalize_failed` before `sink_file` / `sink_issue` / `sink_decision` run (sinks currently execute *before* `verify_artifacts`).
- `TestBug2468ErrorRouting._verify_action(self, data: dict, run_dir: Path) -> str` (`scripts/tests/test_brainstorm.py`) — reused to build the shell action for the new zero-idea fixture.

### Call Path

`route_sink` -> `sink_file` / `sink_issue` / `sink_decision` -> `verify_artifacts` -> `finalize_done` | `finalize_failed`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-01 — based on codebase analysis:_

- Actual edge into the sinks is `converge` -> `route_sink`; `route_sink` is a `classify` state (`echo` of `context.sink`, last stdout line is the verdict, exit code ignored) whose route table is `none`/`_` -> `verify_artifacts` and `file`/`issue`/`decision` -> the three sinks. It has no `_error` route and no edge to `finalize_failed` today, and `_route` never consults `on_error` when a route table is present. A zero-idea guard therefore cannot be expressed by `verify_artifacts` alone; it must sit on the `converge` -> `route_sink` edge or inside `route_sink`'s own routing.
- `exit_code` evaluator verdicts: exit 0 -> yes, exit 1 -> no, any other code -> error; `finalize_failed` is reachable from a shell guard via either `on_no` or `on_error`.
- `ideas.jsonl` validity today: the only writer (`dedup_novelty`) appends one `json.dumps` object per line, accepting any parsed JSON object (no required `text`/`rationale` check), so blank or non-JSON rows are never written by the loop itself. A zero-idea run leaves a 0-byte file; an absent file means `init` failed or `run_dir` was removed.
- Recorded zero-idea run (`.loops/runs/brainstorm-20260701T202115`): `ideas.jsonl` 0 bytes, `winners.md` an empty JSON array, `saturation.txt` still `0` (so `dedup_novelty` never ran) and `lenses.txt` still full; the path went `pop_lens` straight to `cluster`. Why `pop_lens` took its empty-queue exit there is not explained by the surviving artifacts; the issue's fix does not depend on it, since any path that reaches `converge` with no idea rows must fail.
- `failed` is a failure terminal by name (`FAILURE_TERMINAL_NAMES`): reaching it yields run status `failed` and exit code 2, which is what "routes to `failed`" in the acceptance criteria resolves to.

### Decision Rules
- Zero-idea condition: `ideas.jsonl` missing, or containing no line with a non-whitespace character. Threshold is zero rows; there is no minimum-count knob and no dismissal escape hatch (the issue scopes this as a hotfix superseded by `check_floors` in EPIC-3581).
- The condition must hold for every `sink` value, including `none`, an unset sink and unknown values that fall to the `_` route.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — the only live copy of the loop (the copies under `.claude/worktrees/` and `postmortems/brainstorm-baseline/` are stale and out of scope). States involved: `converge` (`next: route_sink`), `route_sink`, `sink_file`, `sink_issue`, `sink_decision`, `verify_artifacts`, `finalize_failed`.
- `scripts/tests/test_brainstorm.py` — `TestBug2468ErrorRouting` has no test that touches `ideas.jsonl` at `verify_artifacts`; its three `verify_artifacts` execution tests create only `brainstorm.md`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — **conditional**: `MR11_MARKER_ALLOWLIST` (pinned by `TestMr11MarkerSet::test_marker_set_matches_enumeration`) needs a new `("loops/brainstorm.yaml", "captured.run_dir.output", "BUG-3688")` tuple only if a new/changed shell action carries an `mr11-ok` marker citing `BUG-3688`; a marker citing `ENH-3358` collapses into the existing tuple and needs no edit [Agent 2/3 finding]
- `scripts/tests/data/loop_interpolation_baseline.json` — **conditional**: add an entry only if the new guard embeds a Python heredoc / `python3 -c` interpolating `${context.*}` / `${captured.*}` (`TestInterpSweepBaseline::test_completeness_guard`); a plain-bash guard adds no site [Agent 2/3 finding]
- `scripts/little_loops/fsm/fence.py` — **conditional**: only if `finalize_failed`'s new text interpolates `${context.brief}` (then it must be registered in `FENCE_ROLES`, else `TestBriefFencing::test_completeness_guard` in `test_builtin_loops.py` fails); simplest is to word the diagnostic without `${context.brief}` [Agent 2 finding]

### Dependent Files (Callers/Importers)
- No other loop invokes `brainstorm` as a sub-loop; `interactive-component-generator.yaml` mentions it in a comment only. `ideas.jsonl` is read only by `brainstorm.yaml` and `test_brainstorm.py`.
- `scripts/little_loops/fsm/fence.py` registers per-state fences for `brainstorm.yaml` (`frame`, `diverge`, `converge`, `finalize_done`); the `finalize_done` entry is worth re-checking if any of those states change.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — corpus-wide gates that run over the edited `brainstorm.yaml` with no brainstorm-specific edit but constrain the new shell action: `TestBuiltinLoopFiles::test_no_grep_c_or_echo_fallback_in_shell_actions` (bans `grep -c ... || echo 0`; use `grep -c ... || true` plus `[ -z "$VAR" ] && VAR=0`, or `grep -q '[^[:space:]]'`), `test_no_bare_bash_variable_in_shell_actions` (bash `${VAR}` must be `$${VAR}`), `test_no_failure_edge_routes_to_a_success_terminal` (guard `on_no`/`on_error` must reach `finalize_failed`), `test_no_gate_completeness_violations`, `test_all_validate_as_valid_fsm`, and `TestValidatorWarningBudget` (no allowlist entry for brainstorm: any new `partial-route` / `capture-ordering` / `stale-mr11-marker` warning fails) [Agent 3 finding]
- `scripts/little_loops/fsm/schema.py` (`FAILURE_TERMINAL_NAMES`) and `scripts/little_loops/fsm/validation/structural_rules.py` — why `finalize_failed` -> `failed` counts as a failure terminal; no edit needed [Agent 1 finding]

### Conventions in Force
- An artifact-invariant gate is its own `action_type: shell` state with an `exit_code` evaluator and all three of `on_yes`/`on_no`/`on_error` declared; the failure branch writes `ERROR: ...` to stderr. Evidence: `verify_artifacts` (BUG-2468), `check_any_built` in `interactive-component-generator.yaml`. The examples disagree on the empty-case code: `verify_artifacts` uses `exit 2` (lands on `on_error`) while `check_any_built`, `rn-decompose.yaml` and `mechanize-skills.yaml` use `exit 1` (lands on `on_no`).
- Invariants sit in a separate named state on the edge ahead of their target; no built-in loop embeds an artifact check inside a `classify` dispatch state's own action. Evidence: `check_decision_before_done` in `refine-to-ready-issue.yaml`, `check_any_built` ahead of `select_best`.
- "Rows with content" in shell is counted with `grep -c '[^[:space:]]'` guarded against its zero-match exit 1 (`rn-refine.yaml` `QN=`), or tested with `[ -s FILE ]`. No built-in loop gates on a non-blank row count of a `.jsonl` file; `[ -s ]` alone catches only a 0-byte file, not a file of blank lines.
- A shell use of `${captured.run_dir.output}` carries an `# ll-lint: mr11-ok(captured.run_dir.output) <reason citing an issue ID>` marker. `MR11_MARKER_ALLOWLIST` in `test_builtin_loops.py` is pinned by exact set equality on `(file, var, issue-id)` triples, so a marker with a new issue ID needs a matching allowlist tuple (and one reusing `ENH-3358` does not).
- Bug IDs are cited in the state's header comment and in the test class/docstring (e.g. `TestBug2468ErrorRouting`).

### Tests
- `scripts/tests/test_brainstorm.py` `TestBug2468ErrorRouting`: `test_verify_artifacts_routes` pins `on_yes: finalize_done`, `on_no`/`on_error: finalize_failed`; `test_all_success_paths_route_through_verify_artifacts` pins the `verify_artifacts` targets of every sink and of `route_sink`'s `none` and `_` routes; these must keep passing or be deliberately revised if the entry topology changes.
- `TestBrainstormShellStates::test_route_sink_has_all_branches` pins `route_sink`'s five route keys and their targets.
- `TestBrainstormYaml::test_required_states_exist` (additions allowed, removals not), `test_no_issue_system_writes_in_core_states`, `test_max_steps_is_60`; `TestBrainstormDryRun::test_no_ratcheted_category_warnings` and `test_all_states_reachable` (shells out to `ll-loop validate brainstorm`).
- `_verify_action` substitutes only `${captured.run_dir.output}`; any other FSM token in a new or extended shell action reaches bash unsubstituted unless the test helper substitutes it too.
- No test in `scripts/tests/` drives a built-in loop YAML through `FSMExecutor`, so "no sink executes" is verifiable today only as topology (route targets) plus real shell execution of the guard action, not as a runtime visit trace.
- Other pins on this file: `test_bug_2816_cli_invocations.py` (`sink_decision` action text), `test_builtin_loops.py` (`MR11_MARKER_ALLOWLIST`, `TestInterpSweepBaseline` against `scripts/tests/data/loop_interpolation_baseline.json`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_brainstorm.py` `TestBug2468ErrorRouting::test_nonempty_brainstorm_md_exits_0` — **will break** once `verify_artifacts` also requires `ideas.jsonl` rows (it seeds only `brainstorm.md`); update it to also write a populated `ideas.jsonl` [Agent 2/3 finding]
- `scripts/tests/test_brainstorm.py` `TestBug2468ErrorRouting::test_empty_brainstorm_md_exits_2` / `test_missing_brainstorm_md_exits_2` — still pass only if the `brainstorm.md` check runs first and keeps its `"empty or missing"` stderr text and exit 2; order the new `ideas.jsonl` check after it [Agent 2/3 finding]
- `scripts/tests/test_brainstorm.py` `TestBrainstormYaml::test_required_states_exist` and `test_no_issue_system_writes_in_core_states` (hard-coded `core_states`) — add the new guard state name to both so it is covered (neither fails if left alone) [Agent 3 finding]
- `scripts/tests/test_brainstorm.py` `TestBrainstormShellStates::test_route_sink_has_all_branches` and `TestBug2468ErrorRouting::test_all_success_paths_route_through_verify_artifacts` — survive if the guard is a new state on `converge.next`; they break only if the guard is placed inside `route_sink` or the sink/`none`/`_` targets are retargeted. No existing test pins `converge.next == "route_sink"` or `finalize_failed` text, so add a new structural test for the guard's `converge.next`/`on_yes`/`on_no`/`on_error` edges [Agent 2/3 finding]
- New tests follow the `TestBug2468ErrorRouting._verify_action` + module helper `_bash(script, cwd)` pattern (add a parallel `_guard_action` helper that substitutes the same `${captured.run_dir.output}` token); `TestPopLensEmptyQueue` is the other template for empty/missing/populated variants [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` `TestBriefFencing::test_completeness_guard` — fails if `finalize_failed`'s new diagnostic text interpolates `${context.brief}` without a `fence.py` registration [Agent 2/3 finding]

### Documentation
- `finalize_failed`'s action text enumerates the failure sources and names only the `brainstorm.md` invariant; a zero-idea failure would be mis-described by it.
- `scripts/little_loops/loops/README.md` and `docs/guides/LOOPS_GUIDE.md` describe the loop (the guide cites 13 LLM states; a shell guard does not change that count).

_Wiring pass added by `/ll:wire-issue`:_
- No doc edit required: `scripts/little_loops/loops/README.md` (loop-table row), `docs/guides/LOOPS_REFERENCE.md` (catalog row), `docs/guides/LOOPS_GUIDE.md` ("Host Guard" `13 LLM subprocess spawns` is a runtime spawn count, unchanged by a shell state) and `README.md` / `scripts/README.md` (line-131 example) contain no state list, count or failure semantics for the loop. No README loop-count bump or mirror-gate run applies (a state is added, not a loop) [Agent 1/2 finding]
- `CHANGELOG.md` — fix entry belongs in the next concrete release section at release prep, not under `[Unreleased]` [Agent 1 finding]
- `brainstorm.yaml` `description:` block mentions neither verification nor failure; no edit needed [Agent 2 finding]

### Configuration
- `max_steps` is pinned at 60 by `test_max_steps_is_60`; a zero-idea run's path is short, so an added state does not threaten the budget.

## Impact

- **Priority**: P3 - silent success on an empty run, small blast radius
- **Effort**: Small - one added check in `verify_artifacts` plus a fixture
- **Risk**: Low - fails a run that has no ideas; nothing else changes
- **Breaking Change**: No

## Implementation Steps

1. A run reaching `converge` with no `ideas.jsonl` rows ends at `finalize_failed` -> `failed` for every `sink` value, with `sink_file`/`sink_issue`/`sink_decision` never entered; the guard lands on the `converge` -> `route_sink` edge or in `route_sink`'s routing, since `verify_artifacts` runs after the sinks.
2. `verify_artifacts` keeps its `brainstorm.md` check and also rejects a missing or row-less `ideas.jsonl`, so the terminal invariant stays self-sufficient if the early guard is ever bypassed.
3. `finalize_failed`'s diagnostic text names the zero-idea case alongside the existing failure sources.
4. Tests in `scripts/tests/test_brainstorm.py` execute the real guard shell against a `tmp_path` run dir for empty, missing, blank-lines-only and populated `ideas.jsonl`, and assert the route targets so no sink is reachable on failure; existing `TestBug2468ErrorRouting` assertions either still pass or are revised deliberately where the entry topology changed.
5. Verification: `python -m pytest scripts/tests/test_brainstorm.py scripts/tests/test_builtin_loops.py -q` passes, `ll-loop validate brainstorm` reports no new warnings, and any new `mr11-ok` marker is reflected in `MR11_MARKER_ALLOWLIST`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_brainstorm.py` `TestBug2468ErrorRouting::test_nonempty_brainstorm_md_exits_0` — seed a populated `ideas.jsonl` alongside `brainstorm.md`, since the extended `verify_artifacts` now rejects a missing or row-less file
- Write the guard and the `verify_artifacts` extension to satisfy the corpus gates in `scripts/tests/test_builtin_loops.py`: no `grep -c ... || echo 0` (use `grep -q '[^[:space:]]'` or `grep -c ... || true` + default), bash variables escaped `$${VAR}`, `on_yes`/`on_no`/`on_error` all declared with failure branches ending at `finalize_failed`, and no new embedded Python heredoc interpolating `${context.*}` / `${captured.*}` (otherwise `loop_interpolation_baseline.json` needs an entry)
- Keep `verify_artifacts`'s `brainstorm.md` check first, with its `"empty or missing"` stderr and exit 2, so `test_empty_brainstorm_md_exits_2` / `test_missing_brainstorm_md_exits_2` keep passing
- Add the new guard state name to `TestBrainstormYaml::test_required_states_exist` and the `core_states` set in `test_no_issue_system_writes_in_core_states` in `scripts/tests/test_brainstorm.py`
- Word `finalize_failed`'s zero-idea diagnostic without `${context.brief}` (or register the state in `scripts/little_loops/fsm/fence.py` `FENCE_ROLES`), else `TestBriefFencing::test_completeness_guard` fails
- If a `# ll-lint: mr11-ok(captured.run_dir.output)` marker is added, cite `ENH-3358` (no allowlist edit) or add the `BUG-3688` tuple to `MR11_MARKER_ALLOWLIST` in `scripts/tests/test_builtin_loops.py`
- Note for sequencing: `cluster`, `rank` and `converge` (three LLM calls) still run before a guard placed on `converge` -> `route_sink`; the guard stops the sinks, not that spend. In-flight FEAT-3582..3586 / FEAT-3667 / FEAT-3596 rewrite the same file and pin the same gates, so expect merge conflicts

## Acceptance Criteria

- A run whose `ideas.jsonl` is empty or absent routes to `failed`, and no sink executes (fixture in `scripts/tests/test_brainstorm.py`, extending the existing `verify_artifacts` tests).
- Existing brainstorm tests stay green.

## Resolution

- Added `check_ideas` shell guard on the `converge` -> `route_sink` edge (`exit_code`; `on_no`/`on_error: finalize_failed`) so no sink runs on a zero-idea run.
- `verify_artifacts` now also rejects a missing or row-less `ideas.jsonl` (after the `brainstorm.md` check).
- `finalize_failed` diagnostic names the zero-idea case.
- Tests added in `scripts/tests/test_brainstorm.py` (missing/empty/blank-only/populated + topology).
- Note: `test_builtin_loops.py::TestAutoRefineAndImplementLoop::test_recheck_set_folds_back_abandoned_residual` fails independently of this change (verified on clean tree).

## Status

**Done** | Created: 2026-09-30 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-10-01T20:33:27 - `c9c8464c-96ed-4bc3-87be-627354577545.jsonl`
- `/ll:ready-issue` - 2026-10-01T20:30:07 - `1b59cbb2-bf74-47e5-a50f-cae5c70bb3aa.jsonl`
- `/ll:confidence-check` - 2026-10-01T20:28:30 - `15be2d3a-2441-4da0-9e82-d2792da8b317.jsonl`
- `/ll:wire-issue` - 2026-10-01T20:25:53 - `0c85d761-8535-49dd-b50b-0a0bfc73c9ce.jsonl`
- `/ll:refine-issue` - 2026-10-01T20:21:39 - `513bdb18-265e-405a-b8e0-03a3e12c85c5.jsonl`
- `/ll:format-issue` - 2026-10-01T20:14:54 - `24fb683c-c17a-4d4e-b334-cd62127dc4c9.jsonl`
