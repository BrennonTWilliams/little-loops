---
id: ENH-2016
title: "rn-build — Resume-from-epic path for continuing a partial build across sessions"
type: ENH
priority: P4
status: open
parent: EPIC-1811
captured_at: '2026-06-08T01:29:25Z'
discovered_date: 2026-06-08
discovered_by: capture-issue
size: Medium
blocked_by:
- FEAT-1992
relates_to:
- FEAT-1990
- FEAT-1992
labels:
- loops
- orchestration
- rn-build
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
- **Validation**: `ll-loop run rn-build --initial resume` completes successfully on a project that previously hit `max_eval_retries`

## Scope Boundaries

- **In scope**: `resume_epic` / `resume_harness` context knobs; `resume` initial state; `synthesize_result` `resume_command` field; `--initial resume` invocation; tests and docs
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
routing to `resume` instead of `tech_research`. Alternatively, document
`--initial resume` as the invocation pattern:

```bash
ll-loop run rn-build \
  --context resume_epic=EPIC-042 \
  --context resume_harness=myproject-harness \
  --initial resume
```

### `synthesize_result` — resume hint

When `eval_passed: false`, add a `resume_command` field to the synthesis JSON:

```json
{
  "eval_passed": false,
  "resume_command": "ll-loop run rn-build --context resume_epic=EPIC-042 --context resume_harness=myproject-harness --initial resume"
}
```

## Implementation Steps

1. Add `resume_epic` and `resume_harness` context knobs to `rn-build.yaml`
2. Add `resume` state (shell, routes to `cluster_execute`)
3. Update `synthesize_result` to emit `resume_command` when `eval_passed: false`
4. Document `--initial resume` invocation in `docs/guides/LOOPS_GUIDE.md` under `rn-build`
5. Add tests to `test_rn_build.py`: resume state existence, resume routes to cluster_execute, synthesis emits resume_command on failure
6. Run `ll-loop validate rn-build.yaml` and `pytest scripts/tests/test_rn_build.py -v`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-build.yaml` — add `resume_epic`/`resume_harness` context knobs; add `resume` state; update `synthesize_result`
- `scripts/tests/test_rn_build.py` — add resume tests
- `docs/guides/LOOPS_GUIDE.md` — document resume invocation under `rn-build`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/rn-implement.yaml` — downstream loop; unaffected (no changes needed)

### Similar Patterns
- `ll-loop run --initial <state>` — existing flag reused; no new mechanism required

### Tests
- `scripts/tests/test_rn_build.py` — resume state exists, routes to cluster_execute, synthesis emits `resume_command` when `eval_passed: false`

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — document `--initial resume` invocation under `rn-build`

### Configuration
- N/A — context knobs live in `rn-build.yaml` context block; no new config files

## Acceptance Criteria

- `ll-loop run rn-build --context resume_epic=EPIC-042 --initial resume` skips the front half and enters `cluster_execute`.
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

## Status

**Open** | Created: 2026-06-08

## Session Log
- `/ll:format-issue` - 2026-06-08T01:37:02 - `6443e1b2-a4d1-4257-be1b-aa306b6f46e7.jsonl`
- `/ll:capture-issue` - 2026-06-08T01:29:25Z - `00fefddf-56f7-43f8-8a57-dd53f6c3526d.jsonl`
