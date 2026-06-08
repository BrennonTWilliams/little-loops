---
id: ENH-2016
title: "rn-build \u2014 Resume-from-epic path for continuing a partial build across\
  \ sessions"
type: ENH
priority: P4
status: done
parent: EPIC-1811
captured_at: '2026-06-08T01:29:25Z'
completed_at: '2026-06-08T04:19:37Z'
discovered_date: 2026-06-08
discovered_by: capture-issue
size: Medium
decision_needed: false
blocked_by:
- FEAT-1992
relates_to:
- FEAT-1990
- FEAT-1992
labels:
- loops
- orchestration
- rn-build
confidence_score: 98
outcome_confidence: 89
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 25
---

# ENH-2016: `rn-build` — Resume-from-epic path for continuing a partial build across sessions

## Summary

When `rn-build` exhausts `max_eval_retries`, `synthesize_result` emits
`still_open` items and the loop ends. There is no way to re-enter `rn-build`
for an already-scoped EPIC without re-running the full front half (init →
tech_research → design_artifacts → commit_design → scope_project → refine_seed
→ eval_harness). For large projects or interrupted runs, this forces unnecessary
re-work of phases whose artifacts already exist. A `resume_epic` context knob
that skips the front half and enters directly at `cluster_execute` would make
`rn-build` usable across multiple sessions.

## Current Behavior

When `rn-build` exhausts `max_eval_retries`, the loop ends after
`synthesize_result` emits `still_open` items. Re-entering `rn-build` for a
project with an already-scoped EPIC requires running the full front half from
scratch (`init → tech_research → design_artifacts → commit_design →
scope_project → refine_seed → eval_harness`). EPIC IDs, harness names, and
design artifacts generated in the prior run are not reused.

## Expected Behavior

`rn-build` supports a context-knob resume invocation (`--context resume_epic=EPIC-NNN --context resume_harness=<name>`) that reads `resume_epic`
and `resume_harness` from context, writes them to `${context.run_dir}/`, and
enters directly at `cluster_execute`. The 7 front-half phases are skipped.
When `eval_passed: false`, `synthesize_result` includes a `resume_command`
field with the exact invocation needed to resume the build in a subsequent
session.

## Motivation

A 24-hour timeout and 30-iteration cap make `rn-build` susceptible to
partial completion on large projects. The front half (tech research, design
artifacts, EPIC scoping) represents significant LLM work that should not need
to repeat just because a subsequent `rn-implement` batch failed. EPIC IDs,
harness names, and design artifacts already exist on disk — a resume path
should be able to read them rather than regenerate them.

## Success Metrics

- **Resume time**: Skips 7 front-half phases (init → tech_research → design_artifacts → commit_design → scope_project → refine_seed → eval_harness) on re-entry
- **Re-work eliminated**: EPIC scoping and design artifacts generated once per project, not once per session
- **Validation**: `ll-loop run rn-build --context resume_epic=EPIC-042 --context resume_harness=myproject-harness` completes successfully on a project that previously hit `max_eval_retries`

## Scope Boundaries

- **In scope**: `resume_epic` / `resume_harness` context knobs; `resume` state (via `init` routing); `synthesize_result` `resume_command` field; context-knob resume invocation; tests and docs
- **Out of scope**: Mid-state resume (resuming from within a running state); automatic resume detection without explicit flag; persistent FSM checkpoint state beyond `epic-id.txt` and `harness-name.txt`

## Proposed Solution

### Context knob

Add `resume_epic: ""` to the `context:` block. When set, `rn-build` treats
it as an existing EPIC ID and skips to `cluster_execute`.

```yaml
context:
  resume_epic: ""  # EPIC-NNN: skip front half, re-enter cluster_execute
  resume_harness: ""  # harness name for eval_gate when resuming
```

### Alternative initial state

Add a `resume` initial state that reads `resume_epic` and `resume_harness`
from context, writes them to `${context.run_dir}/epic-id.txt` and
`${context.run_dir}/harness-name.txt`, then routes to `cluster_execute`:

```yaml
resume:
  action_type: shell
  action: |
    EPIC="${context.resume_epic}"
    HARNESS="${context.resume_harness:-}"
    RUN_DIR="${context.run_dir}"
    mkdir -p "$RUN_DIR"
    if [ -z "$EPIC" ]; then
      echo "ERROR: resume_epic is required for resume mode"
      exit 1
    fi
    echo "$EPIC" > "$RUN_DIR/epic-id.txt"
    [ -n "$HARNESS" ] && echo "$HARNESS" > "$RUN_DIR/harness-name.txt"
    echo "$EPIC"
  capture: epic_id
  evaluate:
    type: exit_code
  on_yes: cluster_execute
  on_no: failed
```

Override `initial:` dynamically by checking `resume_epic` in `init` and
routing to `resume` instead of `tech_research` (Option B — selected). Invocation:

```bash
ll-loop run rn-build \
  --context resume_epic=EPIC-042 \
  --context resume_harness=myproject-harness
```

### `synthesize_result` — resume hint

When `eval_passed: false`, add a `resume_command` field to the synthesis JSON:

```json
{
  "eval_passed": false,
  "resume_command": "ll-loop run rn-build --context resume_epic=EPIC-042 --context resume_harness=myproject-harness"
}
```

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-07.

**Selected**: Option B — Check `resume_epic` in `init` state

**Reasoning**: Option B has a direct, complete template in `rn-implement.yaml` lines 27–65 (ENH-1977 Fix 3) matching the proposed structure at every level: default-empty context knob, early guard in `init` shell action, `exit 0` reuses `on_yes`, no CLI changes. Option A would require adding `--initial` to `run_parser`, forwarding it in `run_background`, and potentially touching `persistence.py` — introducing CLI surface area for a feature scoped to one loop. The acceptance criterion text referencing `--initial resume` should be updated to reflect Option B's invocation: `ll-loop run rn-build --context resume_epic=EPIC-042 --context resume_harness=myproject-harness`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — `--initial` CLI flag | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| Option B — init-routing via context knob | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- **Option A**: `--state` analog exists on `cmd_test`; `run_parser`/`run_background` forwarding pattern established; but no `--initial` flag anywhere in CLI; `PersistentExecutor` change has no precedent (simpler path: mutate `fsm.initial` before executor construction in `run.py:117–125`)
- **Option B**: Direct template in `rn-implement.yaml` lines 27–65; context-knob idiom in 5+ other loops; `resume_read_harness` is a copy of `read_harness_name`; test template in `test_rn_implement.py:676`

## Implementation Steps

1. **Decision made — Option B selected** (init-routing, see Decision Rationale): lower-risk, matches rn-implement's proven pattern, no CLI changes required.
2. Add `resume_epic: ""` and `resume_harness: ""` context knobs to the `context:` block in `scripts/little_loops/loops/rn-build.yaml`
3. Add `resume` state (shell, writes `epic-id.txt`, captures `epic_id`, routes to `resume_read_harness`)
4. Add `resume_read_harness` state (shell, reads `harness-name.txt`, captures `harness_name`, routes to `cluster_execute`) — mirrors `read_harness_name` (lines 225–259); required to populate `${captured.harness_name.output}` for `check_harness_name`
5. **Option B only**: modify `init` state to check `${context.resume_epic}` and route to `resume` if non-empty (follow rn-implement lines 56–68 pattern)
6. **Option A only**: add `--initial` to `run_parser` in `scripts/little_loops/cli/loop/__init__.py`; wire through `run.py` → `executor.py:PersistentExecutor`
7. Update `synthesize_result` action to include `resume_command` field in JSON when `eval_passed: false`; dynamically populate epic_id from `${context.run_dir}/epic-id.txt`
8. Add `"resume"` and `"resume_read_harness"` to `REQUIRED_STATES` in `scripts/tests/test_rn_build.py` (line 22); add tests: resume state exists, resume routes to `resume_read_harness`, `resume_read_harness` routes to `cluster_execute`, `synthesize_result` emits `resume_command` when `eval_passed: false`
9. Document resume invocation in `docs/guides/LOOPS_GUIDE.md` under `rn-build`; add `resume_epic` and `resume_harness` rows to the "Context variables" table in that section
10. Update `docs/reference/API.md` — add `resume_epic` and `resume_harness` rows to the "Context knobs" table under `### rn-build` (lines ~7391–7398)
11. Run `ll-loop validate rn-build` and `python -m pytest scripts/tests/test_rn_build.py -v`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-build.yaml` — add `resume_epic`/`resume_harness` context knobs; add `resume` state (and `resume_read_harness` state to populate `captured.harness_name`); update `synthesize_result`; if Option B, also modify `init` routing
- `scripts/tests/test_rn_build.py` — add resume tests; add `"resume"` and `"resume_read_harness"` to `REQUIRED_STATES` set (line 22); `test_initial_state_is_init` (line 94) remains valid for Option B
- `docs/guides/LOOPS_GUIDE.md` — document resume invocation under `rn-build`
- **Option A only**: `scripts/little_loops/cli/loop/__init__.py` — add `--initial` argument to `run_parser`
- **Option A only**: `scripts/little_loops/cli/loop/run.py` — pass initial state override to executor
- **Option A only**: `scripts/little_loops/fsm/executor.py` — accept `initial_state_override` in `PersistentExecutor.__init__` (line 172)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/rn-implement.yaml` — downstream loop; unaffected (no changes needed)

### Similar Patterns
- `scripts/little_loops/loops/rn-implement.yaml` — `resume: ""` context knob + init-state routing (lines 27–65): the proven pattern for re-entering a loop without re-seeding. Invoked as `ll-loop run rn-implement --context resume=1 --context run_dir=<prior>`. No `--initial` CLI flag required.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on direct codebase analysis:_

**`--initial <state>` CLI flag does NOT exist.** The issue's Similar Patterns entry "existing flag reused; no new mechanism required" is incorrect. Confirmed by reading `scripts/little_loops/cli/loop/__init__.py` (lines 119–257): `run_parser` has no `--initial` argument. The FSM executor sets `self.current_state = fsm.initial` at startup (`scripts/little_loops/fsm/executor.py:172`) with no override path.

**Two implementation options exist — decision required:**

**Option A — Add `--initial <state>` CLI flag** (new mechanism):
- Add `--initial` argument to `run_parser` in `scripts/little_loops/cli/loop/__init__.py`
- Pass the override to the executor in `scripts/little_loops/cli/loop/run.py`
- Modify `PersistentExecutor.__init__` in `scripts/little_loops/fsm/executor.py` to accept `initial_state_override`
- 3 additional files to modify beyond what the Integration Map lists
- Enables the documented `ll-loop run rn-build --initial resume` invocation

**Option B — Check `resume_epic` in `init` state** (no CLI changes, consistent with rn-implement):
> **Selected:** Option B — Check `resume_epic` in `init` state — lowest risk, zero CLI changes, exact replica of rn-implement's proven ENH-1977 Fix 3 pattern
- In `init` state, check `${context.resume_epic}`; if non-empty, write epic-id.txt and route to `resume` instead of `tech_research`
- Invoked as: `ll-loop run rn-build --context resume_epic=EPIC-042 --context resume_harness=myproject-harness`
- Follows the identical pattern in `rn-implement.yaml` lines 56–68 (ENH-1977 Fix 3)
- No CLI or executor changes; purely a YAML change in `rn-build.yaml`

**`captured.harness_name` capture gap (both options):** The proposed `resume` state writes `harness-name.txt` to `run_dir` but uses `capture: epic_id` — it does NOT populate `captured.harness_name`. The `check_harness_name` state (lines 286–299 in `rn-build.yaml`) reads `${captured.harness_name.output}`, which will be empty after the resume path. Even with `resume_harness` set, the eval gate will be bypassed and flow routes directly to `synthesize_result`. Mitigation: add a `resume_read_harness` shell state between `resume` and `cluster_execute` that reads `harness-name.txt` and captures `harness_name` (mirroring `read_harness_name` at lines 225–259).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_build.py` — existing coverage; update `REQUIRED_STATES` (line 22) to add `"resume"` and `"resume_read_harness"`; add new class `TestRnBuildResumeState` with these methods:
  - `test_resume_context_knobs_exist` — assert `resume_epic` and `resume_harness` in `context` block with empty-string defaults (pattern: `test_context_defaults` in `test_harness_optimize.py:58`)
  - `test_resume_state_exists` — assert `"resume"` in `loop_data["states"]` with `action_type == "shell"`
  - `test_resume_checks_resume_epic` — assert `"${context.resume_epic}"` and `"epic-id.txt"` in `resume` action (pattern: `test_init_supports_resume` in `test_rn_implement.py:676`)
  - `test_resume_routes_to_resume_read_harness` — assert `resume.on_yes == "resume_read_harness"` and `resume.on_no == "failed"`
  - `test_resume_uses_exit_code_evaluator` — assert `resume.evaluate.type == "exit_code"`
  - `test_resume_read_harness_reads_harness_name_txt` — assert `"harness-name.txt"` in `resume_read_harness` action
  - `test_resume_read_harness_routes_to_cluster_execute` — assert `resume_read_harness` routes to `cluster_execute`
  - `test_init_branches_to_resume_on_resume_epic` — assert `"${context.resume_epic}"` in `init` action (pattern: `test_init_supports_resume` in `test_rn_implement.py:676`)
  - `test_synthesize_result_emits_resume_command` — assert `"resume_command"` and `"resume_epic"` in `synthesize_result` action

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — document resume invocation under `rn-build`; **also** add rows for `resume_epic` (default `""`) and `resume_harness` (default `""`) to the "Context variables" table [Agent 2 finding]
- `docs/reference/API.md` — "Context knobs" table under `### rn-build` (lines ~7391–7398) currently lists `spec`, `max_eval_retries`, `harness_name`, `epic_id`; add rows for `resume_epic` and `resume_harness`; optionally add a "0 — Resume" row to the "Key phases" table [Agent 2 finding]

### Configuration
- N/A — context knobs live in `rn-build.yaml` context block; no new config files

## Acceptance Criteria

- `ll-loop run rn-build --context resume_epic=EPIC-042 --context resume_harness=myproject-harness` skips the front half and enters `cluster_execute`.
- `resume` state writes `epic-id.txt` and (optionally) `harness-name.txt` to `${context.run_dir}/`.
- `synthesize_result` JSON includes `resume_command` when `eval_passed: false`.
- `ll-loop validate rn-build.yaml` passes.
- New resume tests in `test_rn_build.py` pass.

## Impact

- **Priority**: P4 — quality-of-life for large/interrupted builds; no user is
  blocked without it, but repeated front-half re-runs are wasteful
- **Effort**: Medium — new state, two context knobs, synthesis update, tests, docs
- **Risk**: Low — resume path is strictly additive; the default (no resume_epic) is unchanged
- **Breaking Change**: No

## Resolution

Implemented Option B (init-routing via context knob). Added `resume_epic` and
`resume_harness` context knobs; `resume` and `resume_read_harness` states for the
resume path; updated `init` to use `output_contains` evaluator (RESUME_MODE: marker
enables 3-way routing without a separate gate state); updated `synthesize_result` to
emit `resume_command` when `eval_passed: false`. Nine new tests in
`TestRnBuildResumeState`; docs updated in LOOPS_GUIDE.md and API.md.

## Status

**Done** | Created: 2026-06-08

## Session Log
- `/ll:ready-issue` - 2026-06-08T04:01:03 - `dadbcbf7-c373-4033-a24b-07aa94be3e2b.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:00:00Z - `68893e4c-e94e-407f-bff4-d02d3bd60472.jsonl`
- `/ll:wire-issue` - 2026-06-08T03:54:26 - `54d220fe-a422-4aa0-add9-f4136f7d61fb.jsonl`
- `/ll:decide-issue` - 2026-06-08T03:46:43 - `0d230446-bc14-4aff-9a59-c35c0682b646.jsonl`
- `/ll:refine-issue` - 2026-06-08T03:39:40 - `bbcdc3b4-32cc-4f1a-b941-25eb18e3048a.jsonl`
- `/ll:format-issue` - 2026-06-08T03:27:09 - `c8af87dd-4322-43dc-b305-4be76e1c1339.jsonl`
- `/ll:format-issue` - 2026-06-08T01:37:02 - `6443e1b2-a4d1-4257-be1b-aa306b6f46e7.jsonl`
- `/ll:capture-issue` - 2026-06-08T01:29:25Z - `00fefddf-56f7-43f8-8a57-dd53f6c3526d.jsonl`
