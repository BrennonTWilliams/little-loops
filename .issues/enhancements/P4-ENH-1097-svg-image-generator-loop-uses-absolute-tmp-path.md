---
discovered_date: 2026-04-13
discovered_by: capture-issue
---

# ENH-1097: svg-image-generator loop should create a timestamped run folder in .loops/tmp/

## Summary

The `svg-image-generator` loop hardcodes `output_dir: "/tmp/ll-svg-generator"` — an absolute
system path that writes outside the project tree, ignores `.gitignore` coverage, and shares one
directory across all runs. Each loop invocation should get its own timestamped folder under
`.loops/tmp/svg-image-generator/<timestamp>/`, keeping artefacts scoped to the project and
isolated per run.

## Current Behavior

`scripts/little_loops/loops/svg-image-generator.yaml` defaults `output_dir` to
`"/tmp/ll-svg-generator"`. Every run overwrites the same directory, making it impossible to
compare outputs across runs or recover from a partially-completed run.

## Expected Behavior

Each invocation creates a fresh, timestamped directory under `.loops/tmp/svg-image-generator/`,
e.g. `.loops/tmp/svg-image-generator/20260413-143022/`. Artefacts from separate runs are
preserved side-by-side and covered by `.gitignore`.

## Motivation

- **Consistency**: all other built-in loops use `.loops/tmp/` (e.g. `harness-multi-item`,
  `sprint-refine-and-implement`, `test-coverage-improvement`).
- **Run isolation**: timestamped folders preserve artefacts across retries and let the user
  compare generations.
- **Project hygiene**: keeps generated files inside the project directory under `.gitignore`
  rather than polluting `/tmp/`.

## Proposed Solution

Context variable values cannot embed `${loop.started_at}` (context values are not re-interpolated
at access time). Instead, add a new `init` shell state as the first state that:
1. Creates a `YYYYMMDD-HHMMSS` timestamped directory under the base path
2. Captures the full path via `capture: run_dir`
3. Passes control to `plan`

All subsequent states replace `${context.output_dir}` with `${captured.run_dir.output}`.
The `context.output_dir` default changes to the base path `.loops/tmp/svg-image-generator`.

```yaml
# context block — base path only, no timestamp
context:
  description: ""
  output_dir: ".loops/tmp/svg-image-generator"
  pass_threshold: 6

# new first state
  init:
    action_type: shell
    action: |
      TS=$(date -u +%Y%m%d-%H%M%S)
      DIR="${context.output_dir}/$TS"
      mkdir -p "$DIR"
      echo "$DIR"
    capture: run_dir
    next: plan
```

Then in every other state, replace:
```
${context.output_dir}/brief.md
```
with:
```
${captured.run_dir.output}/brief.md
```

And update `initial: plan` → `initial: init`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/svg-image-generator.yaml`
  - Change `output_dir` default to `.loops/tmp/svg-image-generator`
  - Change `initial: plan` → `initial: init`
  - Add `init` shell state before `plan`
  - Replace all `${context.output_dir}` → `${captured.run_dir.output}` in all states

### Similar Patterns
- `scripts/little_loops/loops/harness-multi-item.yaml` — uses `.loops/tmp/`; canonical `capture:` + `${captured.*.output}` pattern
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — uses `.loops/tmp/`
- `scripts/little_loops/loops/test-coverage-improvement.yaml` — uses `.loops/tmp/`
- `scripts/little_loops/loops/evaluation-quality.yaml:159-165` — **canonical template**: `action_type: shell` state uses `$(date +%Y-%m-%d)` to generate a timestamped path, `capture: report_path`, then the next prompt state uses `${captured.report_path.output}` inline

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestSvgImageGeneratorLoop` class at line 1403; add assertions that `initial == "init"`, an `init` state exists with `action_type: shell`, and `output_dir` default is `.loops/tmp/svg-image-generator`

### Documentation
- `docs/guides/LOOPS_GUIDE.md:697` — hardcodes `/tmp/ll-svg-generator` as the `output_dir` default in the context variables table; update to `.loops/tmp/svg-image-generator`
- `docs/guides/LOOPS_GUIDE.md:711-716` — FSM flow diagram; add `init →` before `plan` in the flow
- `scripts/little_loops/loops/README.md:101` — catalog entry; no path reference, no update needed

### Configuration
- N/A — `output_dir` remains user-overridable; callers passing a custom value are unaffected

### Engine Files (reference only — no changes needed)
- `scripts/little_loops/fsm/schema.py:225` — `StateConfig.capture: str | None` field declaration
- `scripts/little_loops/fsm/executor.py:535-541` — captured dict stored in `_run_action()` as `{"output": ..., "stderr": ..., "exit_code": ..., "duration_ms": ...}`
- `scripts/little_loops/fsm/executor.py:801` — `captured` passed to `InterpolationContext`
- `scripts/little_loops/fsm/interpolation.py:79,102-123` — `${captured.run_dir.output}` resolution: splits on `.`, traverses `self.captured["run_dir"]["output"]`

## Implementation Steps

1. Open `scripts/little_loops/loops/svg-image-generator.yaml`
2. Change `output_dir` default at line 19: `"/tmp/ll-svg-generator"` → `".loops/tmp/svg-image-generator"`
3. Change `initial: plan` at line 11 → `initial: init`
4. Add `init` shell state (see Proposed Solution above) before the `plan` state
5. Replace every `${context.output_dir}` reference with `${captured.run_dir.output}` — 14 occurrences across 5 states:
   - `plan` (lines 31, 33) — also **remove** the "Create directory … if it does not already exist" instruction; `init` already runs `mkdir -p`
   - `generate` (lines 57, 59, 62)
   - `evaluate` (line 87, two occurrences on one line)
   - `score` (lines 101, 102, 105)
   - `done` (lines 148, 149, 150, 151)
6. Update `docs/guides/LOOPS_GUIDE.md:697` — change `output_dir` default from `/tmp/ll-svg-generator` to `.loops/tmp/svg-image-generator`
7. Update `docs/guides/LOOPS_GUIDE.md:711-716` — prepend `init →` to the FSM flow diagram before `plan`
8. Update `scripts/tests/test_builtin_loops.py` (`TestSvgImageGeneratorLoop` at line 1403) — assert `initial == "init"`, `init` state exists with `action_type: shell`, and `output_dir` default is `.loops/tmp/svg-image-generator`
9. Commit

## Impact

- **Priority**: P4 — consistency + run isolation improvement; no functional breakage
- **Effort**: Small — one new state, global find-replace in the YAML, one default change
- **Risk**: Low — `output_dir` remains user-overridable; only the default changes
- **Breaking Change**: No — users who relied on `/tmp/ll-svg-generator` get per-run folders in
  `.loops/tmp/svg-image-generator/` instead, which is strictly better

## Scope Boundaries

- Only `svg-image-generator.yaml` changes; the loop engine, schema, and interpolation code are
  untouched (the `capture:` field is already supported by `StateConfig`)
- Does not enforce `.loops/tmp/` for user-supplied `output_dir` overrides

## Related Key Documentation

- `docs/guides/LOOPS_GUIDE.md:678-731` — existing svg-image-generator documentation section
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:740` — references svg-image-generator as a real-world example

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Canonical implementation template** — `evaluation-quality.yaml:159-171` shows the exact pattern:
```yaml
prepare_report:
  action_type: shell
  action: |
    mkdir -p .loops
    echo ".loops/quality-report-$(date +%Y-%m-%d).md"
  capture: report_path
  next: report

report:
  action_type: prompt
  action: |
    Write a quality health report to `${captured.report_path.output}`.
```
Apply the same structure: `init` state echoes the created path, `capture: run_dir`, all subsequent states reference `${captured.run_dir.output}`.

**`${captured.*.output}` access chain** — `interpolation.py:79,102` splits `"run_dir.output"` into `["run_dir", "output"]` and traverses `self.captured["run_dir"]["output"]`, which is the shell stdout with trailing newlines stripped (`executor.py:537`). Works in both shell and prompt action strings.

**`.gitignore` coverage** — `.gitignore:43` has `tmp/` (bare pattern, no leading slash), which matches any directory named `tmp` at any depth including `.loops/tmp/`. No new gitignore entry is needed.

**Sibling loop** — `html-website-generator.yaml` also uses `output_dir: "/tmp/ll-html-generator"` with an identical structure. Out of scope for this issue but a natural follow-on.

## Labels

`enhancement`, `loops`, `consistency`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-04-13T17:48:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9350596a-47be-4b63-87f1-375aa26b430c.jsonl`
- `/ll:refine-issue` - 2026-04-13T17:45:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38b56074-42ba-45c4-a80a-86bf22a62417.jsonl`

- `/ll:capture-issue` - 2026-04-13T10:52:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ecde5189-5435-44c0-b1ce-c8b3a48ba967.jsonl`

- `/ll:manage-issue` - 2026-04-13T00:00:00Z - enh fix ENH-1097

## Resolution

**Status**: Completed
**Date**: 2026-04-13

### Changes Made

- `scripts/little_loops/loops/svg-image-generator.yaml`: Added `init` shell state as first state; changed `initial: plan` → `initial: init`; changed `output_dir` default from `/tmp/ll-svg-generator` to `.loops/tmp/svg-image-generator`; replaced all 14 `${context.output_dir}` references with `${captured.run_dir.output}` across 5 states; removed redundant "Create directory" instruction from `plan` state.
- `docs/guides/LOOPS_GUIDE.md`: Updated `output_dir` default in context variables table; updated FSM flow diagram to show `init →` before `plan`.
- `scripts/tests/test_builtin_loops.py`: Updated `test_required_top_level_fields` (asserts `initial == "init"`); updated `test_required_states_exist` (adds `init` to required set); added `test_init_state_is_shell_with_capture`; tightened `test_context_has_description_and_output_dir` to assert exact default value.

---

**Completed** | Created: 2026-04-13 | Priority: P4
