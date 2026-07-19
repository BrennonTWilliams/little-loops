---
id: ENH-2699
title: spike-gate.yaml wrapper loop
type: ENH
priority: P3
status: done
labels:
- fsm
- loops
- confidence
- risk-reduction
parent: EPIC-2570
relates_to:
- ENH-2568
confidence_score: 100
outcome_confidence: 91
score_complexity: 22
score_test_coverage: 23
score_ambiguity: 23
score_change_surface: 23
completed_at: '2026-07-15T18:32:07Z'
---

# ENH-2699: spike-gate.yaml wrapper loop

## Summary

Add a new `spike-gate.yaml` FSM loop, shaped like `proof-first-task.yaml`, so
any implementation loop (`rn-*`, `general-task`, `ll-sprint` paths) can opt
into a spike gate on `/ll:spike --check` without growing spike states of its
own.

## Parent Issue

Decomposed from ENH-2568: autodev spike triage routing + spike-gate wrapper
loop. This child covers **Part 2** of the parent's Proposed Solution
(spike-gate.yaml wrapper loop) plus the wiring-phase test/doc items that
attach to it. Independently shippable from ENH-2640 — this loop does not
depend on the autodev triage routing to function; it is invoked directly via
`ll-loop run spike-gate --context ...`.

## Current Behavior

No wrapper loop exists that lets an arbitrary implementation loop gate on
`/ll:spike --check` the way `proof-first-task.yaml` gates on the Learning-Test
Registry for external-API mechanisms. `/ll:spike` (FEAT-2567, done) provides
the `--check` contract (SKILL.md:221-234, `evaluate: type: exit_code`) but
nothing consumes it as a generic FSM gate.

## Expected Behavior

`ll-loop run spike-gate --context issue_file=<path> impl_loop=<loop>` gates
any impl loop on `/ll:spike --check`, mirroring `proof-first-task`'s shape: no
`issue_file` → skip gate, run impl directly; `issue_file` present but
`spike_needed` not set → skip gate; `spike_needed` set and not yet
`spike_completed` → run `/ll:spike --check`, on fail run `/ll:spike --auto`
once and re-check, then delegate to `${context.impl_loop}`.

## Proposed Solution

New `scripts/little_loops/loops/spike-gate.yaml`, `category: gate`, copied
from `proof-first-task.yaml` (81 lines: `initial: check_issue_file`,
`max_steps: 150`, `timeout: 7200`, `on_handoff: spawn`,
`import: [lib/common.yaml]`):

- context: `task`, `issue_file`, `impl_loop` (default `general-task`)
- `check_issue_file` → `check_spike_flag` (`ll-issues check-flag ...
  spike_needed` minus `spike_completed`) → `gate` (`/ll:spike <ID> --check`;
  on fail, `run_spike_auto` once via `/ll:spike <ID> --auto`, re-check) →
  `run_impl` (delegate via `loop: "${context.impl_loop}"`) → `done | blocked |
  impl_failed` terminals
- No `issue_file` → skip gate, run impl directly
  (`check_issue_file.on_no → run_impl`, `proof-first-task` parity)

Loop is auto-discovered from `loops/*.yaml` — no `ll-loop list`/`validate`
special-casing needed.

## API/Interface

- New builtin loop: `spike-gate` (`ll-loop validate spike-gate`, `ll-loop
  list` visibility).
- Reads `spike_needed`/`spike_completed` frontmatter flags (written by
  `/ll:spike` per FEAT-2567; `spike_attempted` is ENH-2640's concern, not
  read here).

## Files to Create

- `scripts/little_loops/loops/spike-gate.yaml`

## Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- **⚠ `scripts/tests/test_builtin_loops.py::test_expected_loops_exist`
  (lines 76–168)** — this test asserts `expected == actual` where `actual =
  {f.stem for f in BUILTIN_LOOPS_DIR.glob("*.yaml")}`. Adding `spike-gate.yaml`
  makes `actual` gain `"spike-gate"`, which is **absent** from the hardcoded
  `expected` set → **this test WILL FAIL** unless `"spike-gate"` is added to the
  set literal (insert alongside `"proof-first-task"` at ~line 145). This is a
  **separate required edit** in the same file from adding `TestSpikeGateLoop`.
  [Agent 2 + Agent 3 finding]
- **`scripts/little_loops/loops/README.md`** — the internal loop catalog **does
  exist** (the refine-pass "loops/README.md does not exist" note checked the
  wrong bare path; the real file is `scripts/little_loops/loops/README.md`).
  `proof-first-task` is registered under `## API Adoption` (line 83). Add a
  `spike-gate` row in the same section (or a new "Risk Reduction" heading),
  table format matching the `proof-first-task` entry. [Agent 1 finding]

- `scripts/tests/test_builtin_loops.py` — add `class TestSpikeGateLoop`,
  cloned from `TestProofFirstTaskLoop` (~line 7220, alongside
  `TestAssumptionFirewallLoop` ~7059): `data` fixture via `yaml.safe_load`,
  per-state `fragment`/`loop`/`with`/`capture` assertions + per-edge routing
  assertions (happy path, blocked path, no-`issue_file` skip path).
- `loops/README.md` — register `spike-gate` under a gate/risk-reduction
  heading, table format matching `proof-first-task`/`assumption-firewall`
  entries.
- `docs/guides/LOOPS_REFERENCE.md` — register `spike-gate`. **No
  `commands/help.md` entry** — gate loops (`proof-first-task`,
  `assumption-firewall`) have none; do not add one for `spike-gate` either.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **⚠ `loops/README.md` does not exist.** Verified: only
  `docs/guides/LOOPS_REFERENCE.md` carries the loop registration table
  (2-column `| name | description |`). Drop `loops/README.md` from Files to
  Modify — registration is a single row added to `LOOPS_REFERENCE.md`.
  - **CORRECTION (`/ll:wire-issue`):** this finding checked the wrong path.
    The bare `loops/README.md` does not exist, but
    **`scripts/little_loops/loops/README.md` DOES** — it is a full loop catalog
    where `proof-first-task` is registered under `## API Adoption` (line 83).
    `spike-gate` must be registered there **in addition to**
    `LOOPS_REFERENCE.md`. See Files to Modify.
- **Registration table shape** (`docs/guides/LOOPS_REFERENCE.md`): existing
  gate rows are `assumption-firewall` (line 160) and `proof-first-task`
  (line 164), single backtick-wrapped name + one-sentence description ending
  with routing outcomes. `ready-to-implement-gate` is at line 159; an example
  run invocation appears at line 173. Match this format for the `spike-gate`
  row.
- **Test-class line anchors** (`scripts/tests/test_builtin_loops.py`):
  `TestAssumptionFirewallLoop` is at **~7114–7274**; `TestProofFirstTaskLoop`
  at **~7275+** (the issue's ~7059/~7220 anchors are stale). Clone
  `TestProofFirstTaskLoop`'s pattern: `LOOP_FILE = BUILTIN_LOOPS_DIR /
  "spike-gate.yaml"` class constant, a `data` fixture asserting
  `LOOP_FILE.exists()` and returning `yaml.safe_load(...)`, then per-test
  `data["states"].get("<state>", {})` assertions on `fragment` /
  `on_yes`/`on_no`/`on_success`/`on_failure` / `loop` / `with`.
- **Skill-invocation pattern for the gate state** (from `autodev.yaml:704-718`,
  `run_spike`): invoke `/ll:spike` as a slash command with
  `action: "/ll:spike ${context.<id>} --check"` +
  `action_type: slash_command`. For the pass/fail gate, pair it with
  `evaluate: {type: exit_code}` — `/ll:spike --check` returns 0=ACs pass
  (gate passes), 1=ACs fail or no spike package, 2+=error
  (`skills/spike/SKILL.md:221-234`). The `--auto` retry uses
  `action: "/ll:spike ${...} --auto"` (writes `spike_attempted`/
  `spike_completed`, `SKILL.md:190,199`).
- **`ll-issues check-flag` confirmed** (`scripts/little_loops/cli/issues/check_flag.py`,
  parser at `__init__.py:626-634`): signature is `ll-issues check-flag
  <issue_id> <field>` (alias `cf`), exit 0 iff the boolean frontmatter field
  is `true`. It checks **one** field per call — the issue's "spike_needed minus
  spike_completed" logic needs **two** states via `fragment: shell_exit`:
  first `check-flag <ID> spike_needed` (on_no → skip to `run_impl`), then
  `check-flag <ID> spike_completed` (on_yes short-circuits → `run_impl`,
  on_no → `gate`). Mirrors proof-first-task's chained `check_issue_file` →
  `check_targets_csv` shell_exit gating.
- **Template top-level keys confirmed** (`proof-first-task.yaml:1-15`):
  `category: gate`, `initial: check_issue_file`, `max_steps: 150`,
  `timeout: 7200`, `on_handoff: spawn`, `import: [lib/common.yaml]`. Terminals
  `done` / `blocked` / `impl_failed`. `assumption-firewall.yaml` is also
  `category: gate` — consistent classification for `spike-gate`.
- **No external-API dependencies** — this is a pure-FSM/YAML + pytest change;
  `learning_tests_required` correctly omitted. Validate with `ll-loop validate
  spike-gate` (MR-1..MR-11 zero-ERROR gate).

## Tests

- `test_builtin_loops.py::TestSpikeGateLoop`: happy path (spike passes,
  delegates to impl_loop), blocked path (spike gate fails after retry),
  no-`issue_file` skip-to-impl path, `spike_completed` short-circuit.
- `ll-loop validate spike-gate` passes with zero ERROR (MR-1..MR-11).
- Full regression: `python -m pytest scripts/tests/test_builtin_loops.py -v`.

_Wiring pass added by `/ll:wire-issue`:_
- **`test_expected_loops_exist` must be updated** (add `"spike-gate"` to the
  `expected` set, ~line 145) — otherwise this existing test regresses on
  exact-set mismatch. This is the one test that **breaks** by adding the new
  file; the glob-based generic tests (`test_all_validate_as_valid_fsm`,
  `test_all_have_description_field`, `test_all_static_loop_references_resolve`,
  MR lint) auto-pick up `spike-gate.yaml` and need no code changes. [Agent 3]
- Structural clone target confirmed: `TestProofFirstTaskLoop`
  (`test_builtin_loops.py:7275–7409`) — `LOOP_FILE` class const + `data`
  fixture (`yaml.safe_load`) + per-state/per-edge assertion methods. Sibling
  `TestAssumptionFirewallLoop` (7114–7273) shows the LLM-state non-LLM-evaluator
  assertion pattern (`evaluate.type == "output_contains"`) if any spike-gate
  state is LLM-judged. [Agent 3]

### Documentation

_Wiring pass added by `/ll:wire-issue` (optional cross-references, SOFT tier):_
- `docs/guides/LOOPS_GUIDE.md` (line 361) — the "API adoption" purpose-grouping
  row lists `assumption-firewall`; optionally cross-list `spike-gate` here.
  Separate table from the `LOOPS_REFERENCE.md` catalog row. [Agent 2]
- `skills/spike/SKILL.md` `## Check Mode Behavior` (line 221) — optional
  back-reference noting `spike-gate.yaml` consumes the `--check` exit-code
  contract; improves traceability, not structurally required. [Agent 2]

_Confirmed NO changes needed_ (checked, not coupled): `.claude/CLAUDE.md`
(lists skills/commands, not loop names), `docs/ARCHITECTURE.md`,
`scripts/little_loops/fsm/validation.py` (`category` is free-form metadata, no
gate special-casing), `.claude-plugin/plugin.json` (loops auto-discovered),
`ll-artifact` policy-builder (stamps a skill catalog, not loops).

## Scope Boundaries

- No rn-* loop edits — adoption is documentation-only (callers substitute
  `impl_loop: spike-gate` via `with: impl_loop=<real loop>` composition); a
  future issue if the base rate justifies direct state additions.
- No changes to `/ll:explore-api`, Learning-Test Registry, or
  `proof-first-task.yaml` itself.
- autodev's own triage routing (`check_spike_needed`/`run_spike`/
  `rerun_confidence_after_spike`) is out of scope — see ENH-2640.

## Impact

- **Priority**: P3
- **Effort**: Small — one gate loop copied from an established template, plus
  tests and doc registration.
- **Risk**: Low — new, isolated loop file; no changes to existing loops.
- **Breaking Change**: No.

## Related Issues

- **ENH-2568** — parent issue this was decomposed from.
- **ENH-2640** — sibling child covering autodev's own triage spike branch.
- **FEAT-2567** — `/ll:spike` skill (done, provides `--auto`/`--check`
  contracts this gate consumes).
- **ENH-2569** — `spike_needed` flag detection (done).

## Resolution

**Status**: Done | Completed: 2026-07-15

Implemented via `/ll:manage-issue`:
- Created `scripts/little_loops/loops/spike-gate.yaml` (`category: gate`, cloned
  from `proof-first-task.yaml`'s template keys). Keys off `issue_id` — the handle
  both `/ll:spike` and `ll-issues check-flag` resolve — with `issue_file` retained
  in context for caller parity. Chain: `check_issue_file` (no `issue_id` → skip) →
  `check_spike_needed` → `check_spike_completed` (short-circuit) → `gate`
  (`/ll:spike --check`, `evaluate: exit_code`) → `run_spike_auto` (`/ll:spike
  --auto`) → `recheck` → `run_impl` (delegates to `${context.impl_loop}`), with
  `done` / `blocked` / `impl_failed` terminals.
- Validates with zero ERROR (MR-1..MR-11) via `load_and_validate`.
- Added `TestSpikeGateLoop` (13 tests) and registered `"spike-gate"` in
  `test_expected_loops_exist`'s `expected` set in `test_builtin_loops.py`.
- Registered `spike-gate` in `scripts/little_loops/loops/README.md` (API Adoption)
  and `docs/guides/LOOPS_REFERENCE.md` (gate section + run example); cross-listed
  under a new "Risk-reduction gates" row in `LOOPS_GUIDE.md`; added a back-reference
  in `skills/spike/SKILL.md` § Check Mode Behavior.

Full `test_builtin_loops.py` suite (1162) and the full suite pass under the
worktree package (`PYTHONPATH=scripts`); the sole full-suite failure is the
documented `test_falsy_src_dir_leaves_pythonpath_uninjected` self-contamination
false-negative (passes clean without the injection), unrelated to this change.

## Status

**Done** | Created: 2026-07-15 | Completed: 2026-07-15 | Priority: P3

## Session Log
- `/ll:issue-size-review` - 2026-07-15T12:06:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-20260715-120653-subloop-epic-epic-2570-spike-workflow-skill-confidence-flag-autodev-routing/0840f459-5e13-45ee-bcca-0c5d1a7e8a86.jsonl`
- `/ll:refine-issue` - 2026-07-15T13:09:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-20260715-120653-subloop-epic-epic-2570-spike-workflow-skill-confidence-flag-autodev-routing/7320ac81-c027-45db-b51f-8b9d14bb529b.jsonl`
- `/ll:ready-issue` - 2026-07-15T13:20:00 - `session-unresolved`
