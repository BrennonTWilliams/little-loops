---
id: ENH-2805
title: Audit builtin-loop skill-invoking states for missing pruning_profile coverage
type: ENH
priority: P2
status: done
captured_at: '2026-07-25T18:10:35Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
relates_to:
- ENH-2714
- EPIC-2456
labels:
- token-cost
- fsm
- loops
confidence_score: 98
outcome_confidence: 65
score_complexity: 17
score_test_coverage: 15
score_ambiguity: 15
score_change_surface: 18
completed_at: '2026-07-25T19:14:30Z'
---

# ENH-2805: Audit builtin-loop skill-invoking states for missing pruning_profile coverage

## Summary

Sweep `scripts/little_loops/loops/*.yaml` for skill/command-invoking states
that run without a `pruning_profile` (state-level or loop default), rank them
by measured per-state token volume from `.ll/history.db` `usage_events`, and
apply profiles to the high-volume states.

## Motivation

A 2026-07-25 `usage_events` audit (last 7 days) established where fleet
tokens actually go:

- Loop **state-tagged** traffic (the only traffic `request_path: sdk` and the
  EPIC-2456 F1/F10 optimizations can touch) is **~1% of fleet tokens**
  (77 calls; 35K uncached input, 259K output, 4.0M cache-write).
- **Session-level** traffic (skill harness turns + interactive) carries the
  real spend: **20.5M output tokens** and **154M cache-creation tokens**
  (billed 1.25×) against 3.27B cache reads (~99% cached).

The SDK request-path work structurally cannot reduce this — no builtin skill
can move to the raw SDK (all 16 skills invoked from loops are tool-dependent:
shell, file writes, or subagents). The shipped levers that *do* target this
traffic are per-state `pruning_profile` (ENH-2714) and automation profiles,
but coverage was never audited after ENH-2714 landed.

Top three skill states by measured volume (7-day window):
`wire_issue` (9.9M cache-read / 1.03M cache-write / 89K out),
`refine_issue` (7.7M / 1.06M / 54K), `confidence_check` (10.9M / 1.05M / 52K)
— all in `autodev.yaml`.

## Current Behavior

Zero of the 89 non-`lib/` builtin loop YAMLs set `pruning_profile` at the
state or loop-default level (`grep -n "pruning_profile"
scripts/little_loops/loops/*.yaml` returns no matches). Every skill/command
state, including the highest-traffic ones in `autodev.yaml`
(`run_wire`, `refine_current`, the six `/ll:confidence-check` states), runs
with full automation-context — no lever from ENH-2714 is actually applied
anywhere.

## Expected Behavior

A sweep mode ranks skill/command-invoking states with no resolvable
`pruning_profile` by measured token volume from `usage_events`, and the
top-volume states (starting with `autodev.yaml`'s `run_wire`,
`refine_current` family, and `/ll:confidence-check` states) have an
appropriate `pruning_profile` applied, with a before/after token comparison
documented.

## Impact

Session-level skill-harness traffic accounts for ~20.5M output tokens and
~154M cache-creation tokens (billed 1.25x) over the measured 7-day window —
the dominant share of fleet spend. Applying `pruning_profile` to the
highest-volume uncovered states is the only shipped lever that can reduce
this traffic without touching the SDK request-path (which structurally
cannot reach it, since all invoked skills are tool-dependent).

## Implementation Steps

1. Script the sweep: for every non-`lib/` loop YAML, list skill/command
   states where neither the state nor the loop default sets
   `pruning_profile` (resolution mirrors `executor.py`'s
   `state.pruning_profile or fsm.pruning_profile`).
2. Join against `usage_events` per-state token sums (7- or 14-day window) to
   rank uncovered states by cache-write + output volume.
3. Apply appropriate profiles to the top-volume uncovered states
   (`autodev.yaml`'s `run_wire`/`refine_current`/`confidence_check` family
   first), respecting states that deliberately need full context.
4. Record the before/after comparison method so the win is measurable.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Coverage confirmed empty**: `grep -n "pruning_profile" scripts/little_loops/loops/*.yaml`
  returns zero matches across all 89 non-`lib/` loop YAMLs — this is a
  full-coverage gap, not partial, including `autodev.yaml`.
- **Reuse, don't reimplement, the sweep logic**: `_validate_pruning_profile()`
  in `scripts/little_loops/fsm/validation.py:2079-2139` already walks
  `fsm.states.items()`, matches skill-invoking actions via `_SKILL_INVOKE_RE`
  (`validation.py:2069`), and resolves the effective profile through
  `_effective_pruning_profile(fsm, state)` (`validation.py:2072-2076`,
  precedence `state.pruning_profile or fsm.pruning_profile` — the exact
  mirror of `executor.py:1662`). Today it only emits ERROR (state's `tools:`
  allowlist excludes the invoked skill) and WARN (`suppress_catalog: true`
  resolves) — it does not yet flag "no profile set at all." Step 1's sweep
  script should extend this function's state-iteration/resolution rather
  than re-parsing YAML from scratch.
- **Loop enumeration helper**: `is_runnable_loop(path)`
  (`fsm/validation.py:2993`) is the existing "exclude `lib/` fragments"
  check, used identically in `cli/loop/info.py:189`, `cli/doctor.py:371`,
  and `doc_counts.py:146` — canonical usage is
  `sorted(p for p in loops_dir.rglob("*.yaml") if is_runnable_loop(p))`.
- **`pruning_profile` is a no-op for `request_path: sdk`/`batch` states**:
  those states bypass `action_runner` entirely via `_dispatch_live`
  (`executor.py:2183`, sending a bare single-turn API call with no
  catalog/CLAUDE.md/hooks at `executor.py:2205`) — there is nothing to
  prune. The sweep must exclude these states from the "uncovered" ranking,
  not just skill/command-invoking ones with a resolvable profile.
- **`usage_events.state` reliability caveat**: the column exists
  (`session_store.py:765`, added schema v20) and is populated by the live
  writer `record_usage_event()` (`session_store.py:2532-2576`, ENH-2724),
  but `_backfill_usage_events()` (`session_store.py:3630+`, ENH-2461,
  post-hoc JSONL ingestion) always leaves `state` NULL. `aggregate_usage`'s
  docstring (`history_reader.py:1116`) explicitly states "usage_events
  carries no FSM state, so per-state rollups are not offered" — Step 2's
  join must filter to non-NULL `state` rows (live-writer origin only) or
  fall back to `waste_attribution()`'s `usage_events.run_id = loop_runs.run_id`
  join pattern (`history_reader.py:999`) if per-state fidelity is
  insufficient.
- **`refine_current` (autodev.yaml:157) is not a direct skill action** — it
  `delegate`s via `loop:` to the `refine-to-ready-issue` sub-loop, so
  auditing it means following into that sub-loop's states, not the
  top-level `autodev.yaml` state itself. `run_wire` (autodev.yaml:522) is a
  direct `/ll:wire-issue ... --auto` `slash_command` action with no
  `pruning_profile` and no loop-level default to fall back to.
  `/ll:confidence-check` invocations recur at least 6× in `autodev.yaml`
  (lines 439, 565, 963, 1295, 1377, ~1513) as separate states, none with a
  profile set.
- **Before/after measurement method (Step 4)**: `cmd_promote_baseline`
  (`cli/loop/info.py:1273`) already captures latest-run `action_output`
  events per loop into `.loops/baselines/<loop>/output.txt` as a comparator
  — the closest existing "before" snapshot mechanism. For token-volume
  deltas specifically, `compute_evaluator_variance()`
  (`analytics/variance.py`, invoked by `cmd_diagnose_evaluators`/
  `cmd_calibrate_budget` at `cli/loop/info.py:1162`/`:1218`) is the model
  for "measure a per-state metric across N runs and flag against a
  threshold" — reuse that shape for the before/after token comparison
  rather than inventing a new metric pipeline.
- **Test pattern to model a new coverage test after**:
  `scripts/tests/test_builtin_loops.py`, class `TestBuiltinLoopFiles`,
  fixture `builtin_loops` (lines 32-36:
  `sorted(p for p in BUILTIN_LOOPS_DIR.rglob("*.yaml") if is_runnable_loop(p))`),
  with structural-audit examples `test_no_bare_pass_token_in_output_contains`
  (line 172) and `test_no_bare_bash_variable_in_shell_actions` (line 192) as
  the shape for a new `test_skill_invoking_states_have_pruning_profile_or_suppression`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Sweep `refine-to-ready-issue.yaml`'s own skill/command states for the
   coverage-ranking check, not just the top-level `autodev.yaml` states that
   delegate into it.
6. Decide the suppress-flag strategy before extending `_validate_pruning_profile()`:
   reuse `pruning_profile_ok` (`fsm/schema.py:1235,1351-1352,1456`) as a third
   check under the same flag, or mint a new one — if new, add the matching
   JSON-Schema block in `fsm-loop-schema.json:354-358`.
7. Confirm the new check emits `ValidationSeverity.WARNING`, not `ERROR` —
   `test_builtin_loops.py:46`'s `test_all_validate_as_valid_fsm` filters to
   ERROR only and would fail for nearly every builtin loop if the new rule
   is ERROR-severity (none currently set `pruning_profile`).
8. Add the missing MR-12 row to the `.claude/CLAUDE.md` MR-table (and a
   `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` section) alongside whatever
   row is needed for the new coverage-ranking mode — closing the
   pre-existing doc gap identified during wiring, not just documenting the
   new behavior.
9. Write the net-new `_validate_pruning_profile`/MR-12 test class in
   `test_fsm_validation.py`, modeled on `TestLLMEvidenceContractValidation`
   (line 3972): positive control, negative control, suppress-flag-honored,
   and end-to-end-via-`validate_fsm()` cases.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — extend `_validate_pruning_profile()`
  (lines 2079-2139) with a coverage-ranking mode, reusing `_SKILL_INVOKE_RE`
  (line 2069) and `_effective_pruning_profile()` (lines 2072-2076). Note this
  rule is internally labeled `MR-12` in code comments (lines 2080, 2093, 2115,
  2133) but has **no row in the `.claude/CLAUDE.md` MR-table** — a pre-existing
  doc gap, not introduced by this issue, but worth closing alongside it.
- `scripts/little_loops/loops/autodev.yaml` — apply `pruning_profile` to
  `run_wire` (line 522) and the repeated `/ll:confidence-check` states
  (lines 439, 565, 963, 1295, 1377, ~1513).
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — sub-loop delegated
  to via `autodev.yaml`'s `refine_current` (line 157); its own skill/command
  states need the same coverage sweep, not just the top-level autodev state.
- Other high-volume uncovered loop YAMLs surfaced by the Step 2 ranking join —
  `auto-refine-and-implement.yaml`, `rn-refine.yaml`, `rn-implement.yaml`,
  `rn-remediate.yaml`, `issue-refinement.yaml`, `recursive-refine.yaml` are
  plausible high-traffic candidates given they share skill states with
  `autodev.yaml`'s hot path, but must be confirmed by the ranking join, not
  assumed.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:1662` — the resolution logic being
  mirrored (`state.pruning_profile or self.fsm.pruning_profile`), applied at
  `executor.py:1668` via `automation_profile` kwarg to `action_runner.run()`.
- `scripts/little_loops/cli/loop/info.py:189`, `cli/doctor.py:371`,
  `doc_counts.py:146` — existing callers of `is_runnable_loop()`
  (`fsm/validation.py:2993`), the loop-enumeration helper to reuse for the
  sweep.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/config_cmds.py:12-52` (`cmd_validate`) —
  the only CLI call path into `validate_fsm()` → `_validate_pruning_profile()`
  (`validation.py:1300`); it renders `list[ValidationError]` as text/JSON
  (lines 26-52) with no per-rule filter — a ranked-by-token-volume report
  doesn't fit this flat violations-list shape, so the new coverage-ranking
  mode likely needs a separate surface (see CLI coupling note below), not a
  `cmd_validate` extension. [Agent 2 finding]
- `scripts/little_loops/fsm/schema.py:1235,1351-1352,1456` — `pruning_profile_ok`
  suppress flag (`FSMLoop` dataclass field + `to_dict`/`from_dict`); the
  natural reuse point for a third check under the same flag rather than
  minting a new one, unless the ranking mode is deliberately
  non-suppressible. [Agent 2 finding]
- `scripts/little_loops/config/features.py:1020-1038` (`AutomationPruningConfig`)
  — project-level automation-profile config counterpart to loop-level
  `pruning_profile`. [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — the MR-1..MR-11 table has no row for the existing
  `pruning_profile`/MR-12 rule at all (a pre-existing gap); extending the
  rule without adding a row compounds it. [Agent 2 finding]
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — zero mentions of
  `pruning_profile` despite `.claude/CLAUDE.md` naming this file "the source
  of truth" the MR table summarizes. [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` § "Automation-Context Pruning" (lines
  603-631) — documents the `pruning_profile:` YAML shape and fields table
  but says nothing about the validation/linting behavior; would need a
  cross-reference if the new mode is user-facing, matching how line 601
  cross-references the haiku-gen lint from inside this same guide. [Agent 2
  finding]

### Similar Patterns
- `cmd_promote_baseline` (`cli/loop/info.py:1273`) — before/after snapshot
  mechanism to model Step 4 after.
- `compute_evaluator_variance()` (`analytics/variance.py`) — per-state
  metric-across-runs measurement shape.
- `waste_attribution()` (`history_reader.py:999`) — `usage_events.run_id =
  loop_runs.run_id` join pattern, needed if per-state `state` column
  fidelity proves insufficient (see caveat below).

### Tests
- `scripts/tests/test_builtin_loops.py` (`TestBuiltinLoopFiles`, `builtin_loops`
  fixture, lines 32-36) — model for a new coverage-sweep test.
- `scripts/tests/test_fsm_executor.py` — existing `pruning_profile`
  application coverage.
- `scripts/tests/test_session_store.py`, `test_usage_journal.py`,
  `test_history_reader.py` — `usage_events` schema/backfill/query coverage.

_Wiring pass added by `/ll:wire-issue`:_
- **No test file currently covers `_validate_pruning_profile()`/MR-12 at
  all** — zero matches for `pruning_profile`, `MR-12`, or `ENH-2714` anywhere
  in `scripts/tests/`. The new coverage-ranking check needs a net-new test
  class, not an extension of existing coverage. [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py:3972`
  (`TestLLMEvidenceContractValidation`, MR-8) — closest fixture pattern to
  copy: `_simple_fsm()` helper (3975-3984) + `make_state()` (line 55),
  positive control (3988), negative control (4010), exemption case (4051),
  suppress-flag-honored case (4070), and end-to-end-via-`validate_fsm()` case
  (4090). [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py:1118` (MR-1 tests) — second template,
  closer in spirit since MR-1 is also a "no backstop set" check; `:1290`
  `test_meta_self_eval_ok_recognized_as_top_level_key` is the pattern to
  mirror if a new suppress-flag name (rather than reusing
  `pruning_profile_ok`) is introduced. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:1129`
  (`TestValidatorWarningBudget`, `CATEGORY_PATTERNS`) — the warning-regression
  ratchet; a new WARN message won't be caught here unless it matches an
  existing substring category, so it won't break by itself, but review
  before assuming silence means safety. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:46` (`test_all_validate_as_valid_fsm`)
  — only filters `ValidationSeverity.ERROR`; **if the new coverage-ranking
  check is implemented as ERROR instead of WARN, this test fails for nearly
  every builtin loop** (not just autodev.yaml) since none currently set
  `pruning_profile`. Confirms severity choice (WARN) before implementation.
  [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:3895` (autodev structural tests) and
  `:1080` (refine-to-ready-issue structural tests) — no exact key-set
  assertions found on the touched states, so adding `pruning_profile:` keys
  is low breakage risk, but worth a final `.keys()) ==` grep before editing.
  [Agent 3 finding]

### Configuration
- `scripts/little_loops/fsm/fsm-loop-schema.json:354-358,552` — JSON-Schema
  properties for `pruning_profile`/`pruning_profile_ok`; needs a matching
  block only if a new (non-reused) suppress flag is introduced. [Agent 2
  finding]
- `config-schema.json` (project-level) needs **no** change — confirmed zero
  MR-suppress flags live there; all of them (`meta_self_eval_ok`,
  `shared_state_ok`, `bash_default_ok`, `pruning_profile_ok`, …) live in the
  loop-YAML schema (`fsm/schema.py` + `fsm-loop-schema.json`) instead. [Agent
  2 finding]

## Success Metric

Reduced `cache_creation_input_tokens` + `output_tokens` per state-visit for
the covered states, on a before/after `usage_events` comparison over
equivalent runs (same loop, same issue class).

## Scope Boundaries

- No changes to the pruning mechanism itself (ENH-2714 is shipped and
  unchanged) — this is a coverage audit + YAML application pass.
- No `request_path` / SDK-path work; that surface is complete and this issue
  exists precisely because it cannot address session-level spend.

## Session Log
- `ll-auto` - 2026-07-25T19:14:30 - `31ec5a62-eefc-471b-8bc7-fafbd6f30d96.jsonl`
- `/ll:ready-issue` - 2026-07-25T19:03:07 - `afcba8f3-c5af-4eab-8259-8ec7aa96f2d3.jsonl`
- `/ll:confidence-check` - 2026-07-25T19:15:00 - `722815f2-3d74-4518-b9fe-c28dd94ac7db.jsonl`
- `/ll:wire-issue` - 2026-07-25T19:00:26 - `226ab9b2-a7b7-48c8-a563-76e26caf02e5.jsonl`
- `/ll:refine-issue` - 2026-07-25T18:54:23 - `8eb805b9-76b2-4397-8e4e-10851926b76b.jsonl`
- `/ll:capture-issue` - 2026-07-25T18:10:35Z

---

## Status
- Status: open


---

## Resolution

- **Action**: improve
- **Completed**: 2026-07-25
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
