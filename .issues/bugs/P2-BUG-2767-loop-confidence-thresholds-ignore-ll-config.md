---
id: BUG-2767
title: Built-in loops hardcode confidence thresholds and never read commands.confidence_gate
  from ll-config
type: bug
status: done
priority: P2
labels:
- bug
- fsm
- config
- loops
captured_at: 2026-07-24
completed_at: '2026-07-24T21:39:46Z'
discovered_date: 2026-07-24
discovered_by: capture-issue
discovered_commit: 8926f14b
relates_to:
- BUG-2768
decision_needed: false
confidence_score: 98
outcome_confidence: 80
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 17
---

# BUG-2767: Built-in loops hardcode confidence thresholds and never read `commands.confidence_gate` from ll-config

## Summary

`autodev.yaml`, `recursive-refine.yaml`, and `eval-driven-development.yaml` declare
`context.readiness_threshold` / `context.outcome_threshold` as plain literals. Each
carries an inline comment claiming ll-config is canonical:

```yaml
context:
  readiness_threshold: 90   # canonical: commands.confidence_gate.readiness_threshold in ll-config.json
  outcome_threshold: 75     # canonical: commands.confidence_gate.outcome_threshold in ll-config.json
```

Nothing reads config. `${context.outcome_threshold}` resolves to the literal `75`,
so a project that sets `commands.confidence_gate.outcome_threshold` in
`.ll/ll-config.json` gets **no effect at all** inside these loops. The comment is
actively misleading — it documents an integration that does not exist.

## Current Behavior

The gate states interpolate the literal directly. `regate_after_atomic_remediation`
(`scripts/little_loops/loops/autodev.yaml`, anchor `regate_after_atomic_remediation`):

```yaml
readiness_ok = conf >= ${context.readiness_threshold}
outcome_ok = waived or (outc >= ${context.outcome_threshold})
```

Same shape at `check_readiness_for_atomic_remediation` and `recheck_after_size_review`,
and at the `ll-issues check-readiness --readiness … --outcome …` call sites.

Note that `ll-issues check-readiness` itself *does* honor config
(`cli/issues/check_readiness.py`, `cg.get("readiness_threshold", default_readiness)`),
and hard-ANDs config against the CLI overrides — so the loop passing its own literals
produces a gate whose effective thresholds are `max(literal, config)` on those paths
and pure-literal on the inline-Python paths. The behavior is inconsistent within a
single loop.

## Expected Behavior

`context.readiness_threshold` / `context.outcome_threshold` resolve from
`commands.confidence_gate.readiness_threshold` / `.outcome_threshold` when the project
sets them, falling back to the loop literal only when unset. An explicit
`--context readiness_threshold=…` on the command line must still override both.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: top-level `context:` block (also `recursive-refine.yaml`, `eval-driven-development.yaml`)
- **Cause**: The FSM already has a config-layering mechanism for exactly this —
  `scripts/little_loops/fsm/schema.py`, the `config.readiness_threshold` /
  `config.outcome_threshold` fields, which layer over `commands.confidence_gate`
  (see `LoopConfig.to_confidence_gate()` / `from_dict()` around the
  `confidence_gate` merge). These three loops bypass it and use plain `context:`
  vars instead, which have no config source.

## Steps to Reproduce

1. In a project, set `commands.confidence_gate.outcome_threshold: 65` in `.ll/ll-config.json`
   (or leave it unset — the ll-config default is also 65, per
   `config/automation.py` `ConfidenceGateConfig.outcome_threshold: int = 65`).
2. Take an issue whose `confidence_score` ≥ 90 and `outcome_confidence` is between
   65 and 74 — e.g. 99 / 72.
3. Run `ll-loop run autodev <ISSUE_ID>`.
4. Observe: the issue is deferred rather than implemented, because the loop compares
   against its own literal `75`, not the configured `65`.

## Real-World Repro

`ll-loop run autodev FEAT-069` in `/Users/brennon/AIProjects/animation/sketch-storyboards`
(2026-07-24, run `autodev-20260724T135044`). The issue took the BUG-2734
ready-but-atomic path: `run_size_review` scored it Very Large but declined to
decompose, `check_readiness_for_atomic_remediation` passed, and
`remediate_oversized_atomic` + `rerun_confidence_after_atomic_remediation` scored it
`confidence_score: 99` / `outcome_confidence: 72`.

`regate_after_atomic_remediation` then failed on `72 < 75`, wrote
`FEAT-069  oversized_atomic` to `autodev-skipped.txt`, and stamped
`status: deferred, deferred_by: automation, deferred_reason: oversized_atomic`.
The project's effective configured outcome threshold was **65** — under which the
issue would have passed the gate and proceeded to `decide_current` / implement.

## Motivation

The gate decides whether an issue gets implemented or silently deferred. A project
that deliberately tunes its thresholds down (or up) is ignored, so autodev's
behavior cannot be configured per-project at all. Worse, the deferral is *silent* and
stamped with an authoritative-sounding reason code (`oversized_atomic`), so the user
sees a plausible verdict rather than a config bug. Every such misfire costs a full
autodev cycle (~27 min and ~500k tokens in the FEAT-069 case) and leaves an issue
parked in `deferred` needing manual triage.

## Proposed Solution

Make the three loops source their thresholds from config rather than from literals.
Two viable approaches:

**Option A (preferred) — use the existing FSM `config:` block.** Add to each loop:

```yaml
config:
  readiness_threshold: null   # inherits commands.confidence_gate.readiness_threshold
  outcome_threshold: null
```

and change the interpolations from `${context.readiness_threshold}` to whatever
namespace exposes the resolved `LoopConfig` value. This reuses the tested
`fsm/schema.py` layering path and is the mechanism the codebase already intends.
Requires confirming that resolved `config.*` values are interpolable from state
actions; if they are not, that plumbing is the bulk of the work.

**Option B — resolve at context-default time.** Have the loader seed
`context.readiness_threshold` / `context.outcome_threshold` from
`commands.confidence_gate.*` when the loop does not explicitly set them, keeping
`--context` precedence highest. Simpler, but adds a second config path parallel to
`fsm/schema.py`'s, which is the divergence that caused this bug in the first place.

> **Selected:** Option B — resolve at context-default time — extends an existing, near-exact precedent in `cli/loop/run.py` with minimal risk; Option A would introduce new interpolation-engine surface with no functional precedent.

Either way: delete or correct the "canonical:" comments, and make sure
`--context readiness_threshold=…` still wins.

Precedence must end up: `--context` override > project `commands.confidence_gate.*` >
loop literal / ll-config default.

### Decision Rationale

**Selected: Option B — resolve at context-default time.**

`/ll:decide-issue` spawned parallel `codebase-pattern-finder` agents to gather codebase
evidence for each option, then scored both against Consistency / Simplicity / Testability
/ Risk (0-3 each, 12 max):

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-----------:|:----------:|:------------:|:----:|:-----:|
| A — `config:` block + new interpolation namespace | 1 | 1 | 1 | 1 | 4/12 |
| **B — context-default seeding** | **3** | **3** | **2** | **2** | **10/12** |

**Key evidence:**
- `cli/loop/run.py:227-235` already has a near-exact structural template — a
  `_config = BRConfig(Path.cwd())` block that injects a config-derived default
  (`loops.run_defaults.include`) into `fsm.context` only when `--context` didn't already
  set it, with an explicit "`--context` already applied above takes precedence" comment.
  Extending it with two more `if "X" not in fsm.context: fsm.context["X"] = _config...`
  lines for `readiness_threshold`/`outcome_threshold` is a minimal, same-shape addition.
- Option A's `LoopConfigOverrides` dataclass (`fsm/schema.py:912-970`) exists and parses,
  but its `readiness_threshold`/`outcome_threshold` fields are display-only today
  (`cli/loop/info.py`) with zero runtime consumers — Option A would be the first
  functional consumer, requiring both a new startup-time config-merge step and a brand
  new `config` namespace in `InterpolationContext.resolve()` (`fsm/interpolation.py`),
  a documented, shared core primitive with no partial scaffolding for this addition.
  The one existing functional precedent for the dataclass (`handoff_threshold` → env var
  injection, `cli/loop/run.py:216-217` / `cli/loop/lifecycle.py:539-540`) uses a *different*
  mechanism than Option A proposes, making Option A internally inconsistent as well.
- **Caveat carried into Implementation Steps**: seeding only takes effect once the three
  loop YAMLs' hardcoded `context.readiness_threshold`/`context.outcome_threshold` literals
  are removed — YAML-declared `context:` values populate `fsm.context` before the
  seeding code runs, so they'd silently shadow the new config default under the same
  `not in fsm.context` guard that makes `--context` win.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Implementation Step 1 is answered: `${config.*}` is not interpolable today, and it's more than a missing case.** `InterpolationContext.resolve()` (`scripts/little_loops/fsm/interpolation.py:72-111`) supports exactly these namespaces: `context`, `captured`, `prev`, `result`, `state`, `loop`, `env`, `messages`, `param`. There is no `config` namespace — any `${config.readiness_threshold}` reference raises `InterpolationError: Unknown namespace: config` at line 111.
- **`LoopConfigOverrides` (the dataclass the issue calls "LoopConfig") is dead code with respect to execution.** It lives in `scripts/little_loops/fsm/schema.py:912-970` (fields at 926-927, `to_dict()`-style confidence_gate emission at 937-943, `from_dict()` at 951-970 reading `commands.confidence_gate`), but has no callers in `executor.py` or anywhere else — it is never loaded from ll-config nor merged into any running FSM's context/config. It's a data-shape helper that was never wired up.
- **None of the three loops declare a top-level `config:` block** — `autodev.yaml:33-34` and `recursive-refine.yaml:32-34` set `context.readiness_threshold: 90` / `context.outcome_threshold: 75` directly under `context:`; `eval-driven-development.yaml:16-17` matches. Threshold interpolation sites: `autodev.yaml:286-287,448-449,1246,1297-1298,1392-1393`; `recursive-refine.yaml:252-253,486-487`.
- **`check_readiness.py:34-42`** reads `commands.confidence_gate.{readiness,outcome}_threshold` straight from `ll-config.json` via `json.loads`, falling back to CLI-supplied `args.readiness`/`args.outcome` on missing key or read failure — it does not go through `LoopConfigOverrides` either.
- **Revised effort estimate for the two options, given the above:**
  - **Option A** now requires *both* (a) loading + merging `LoopConfigOverrides.from_dict()` against ll-config's `commands.confidence_gate` at FSM startup, storing the result somewhere reachable, *and* (b) adding a new `config` case to `InterpolationContext.resolve()` — i.e., new interpolation-engine surface, not just plumbing an existing path.
  - **Option B** is comparatively minimal: it reuses the already-interpolated `context` namespace and only needs a load-time merge step (config → context seeding) in the executor's loop-init path — no interpolation-engine changes at all. The seeding point is wherever the executor first turns a loop YAML's `context:` block into `InterpolationContext.context` (search `executor.py` for the loop-init/context-construction call before state execution begins).
  - This tips the balance toward **Option B** as the lower-risk, lower-effort path unless there's a reason to also want `${config.*}` interpolation for other future use cases.

## Integration Map

- `scripts/little_loops/loops/autodev.yaml` — `context:` block; `check_readiness_for_atomic_remediation`, `regate_after_atomic_remediation`, `recheck_after_size_review`, and the `ll-issues check-readiness` call sites
- `scripts/little_loops/loops/recursive-refine.yaml` — `context:` block and gate states
- `scripts/little_loops/loops/eval-driven-development.yaml` — `context:` block and gate states
- `scripts/little_loops/fsm/schema.py` — `LoopConfig.readiness_threshold` / `.outcome_threshold`, the `confidence_gate` merge
- `scripts/little_loops/config/automation.py` — `ConfidenceGateConfig` defaults
- `scripts/little_loops/cli/issues/check_readiness.py` — the CLI half that already reads config
- `scripts/little_loops/cli/loop/info.py` — surfaces `readiness_threshold=` in loop info output; should reflect the resolved value

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py` (lines ~216-235) — **this is the actual seeding site for Option B**, not previously in the Integration Map. Already has the exact precedent pattern (`if "include" not in fsm.context and _config.loops.run_defaults.include: fsm.context["include"] = ...` for `loops.run_defaults.include`, and a `handoff_threshold` env-var injection). The fix adds two more `if "X" not in fsm.context:` blocks here, reading `commands.confidence_gate.readiness_threshold`/`.outcome_threshold` via `BRConfig`.
- `scripts/little_loops/cli/loop/lifecycle.py` (lines ~539-540) — mirrors `run.py`'s `handoff_threshold` env injection for a second FSM-launch code path; confirm whether this path also needs the same `readiness_threshold`/`outcome_threshold` seeding or whether it delegates to `run.py`.
- `scripts/little_loops/fsm/schema.py` `LoopConfigOverrides` (lines 911-973) — a **second, currently inert** override mechanism: a top-level YAML `config:` block (distinct from `context:`) whose `readiness_threshold`/`outcome_threshold` fields already round-trip `commands.confidence_gate.*` but are applied nowhere except display in `cli/loop/info.py`. Decide whether Option B's seeding also honors this block (making `docs/guides/LOOPS_GUIDE.md`'s documented precedence chain true) or leaves it display-only.
- `scripts/little_loops/cli/issues/next_action.py` — sibling config-first threshold reader (`commands.confidence_gate` via raw `json.loads`, independent of `fsm.context`); reference implementation for fallback-default precedence (85/65), not itself modified by this fix.
- `scripts/little_loops/init/tui.py` (line ~721) — `/ll:init` wizard writes `commands.confidence_gate = {"enabled": True, "readiness_threshold": 85}` into generated `.ll/ll-config.json`; confirms the schema-default value (85) that unconfigured projects will now inherit into loop context once seeding lands — a behavior change beyond "stop ignoring config" (today's loop default is 90/75, not 85/65).
- `scripts/little_loops/loops/rn-implement.yaml` (lines ~25-26, 756-757) and `scripts/little_loops/loops/rn-remediate.yaml` (lines ~58-59) — declare their own independent `context.readiness_threshold`/`outcome_threshold` defaults (85/75), a third distinct pairing. Confirm whether any of the three in-scope loops sub-loop into these, threading the seeded value through — out of scope to fix here but a landmine if seeding logic is later generalized.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` (lines ~471-494) — canonical `commands.confidence_gate.readiness_threshold`/`.outcome_threshold` schema defaults (85/65) that Option B's seeding will now surface as the effective default for unconfigured projects, diverging from the loops' current 90/75 literals.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` (line 444) — states "`refine-to-ready-issue` ... reads `readiness_threshold`/`outcome_threshold` from its `context:` block (defaults: 90/75)"; needs updating once seeding changes the effective default source (also already inconsistent with that loop's own test, which asserts 85/65 — pre-existing drift, not introduced here).
- `docs/guides/LOOPS_REFERENCE.md` (lines 135, 138, 1087-1088) — documents `--context readiness_threshold=...` overrides and "override via `commands.confidence_gate.readiness_threshold`" text that is **currently false** (this is the bug) and becomes accurate post-fix; numeric default tables (90 vs 85, inconsistent among themselves) need reconciling with whatever literal survives in the YAML `context:` blocks.
- `docs/guides/LOOPS_GUIDE.md` (lines 695-696, 701) — documents the `config:`-block (`LoopConfigOverrides`) precedence chain that is not fully backed by code today (see `LoopConfigOverrides` note above); update once the seeding/config-block relationship is decided.
- `docs/generalized-fsm-loop.md` (lines 384-386) — FSM YAML `config:` block schema reference for `confidence_gate.readiness_threshold`/`.outcome_threshold`; verify still accurate after the fix.
- Delete/correct the misleading `# canonical:` inline comments per the issue's existing Proposed Solution note (already covered by Implementation Step 3, cross-referenced here for the wiring pass).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_loop_cli_defaults.py`, class `TestLoopRunIncludeContextInjection` (lines 332-433) — **exact template to mirror** for the new config-seeding test: writes `.ll/ll-config.json`, writes a minimal loop YAML, patches `PersistentExecutor` with a context-capturing stub, asserts on the captured `fsm.context` dict. Add a new `TestLoopRunConfidenceThresholdContextInjection` class with the same three sub-cases (config value flows into `fsm.context`; `--context` override wins; absent config leaves default unset).
- `scripts/tests/test_builtin_loops.py`, `TestRecursiveRefineLoop.test_context_thresholds_defined` (lines 5797-5803) — **existing test that will break** if the fix removes `readiness_threshold`/`outcome_threshold` keys outright from `recursive-refine.yaml`'s `context:` block rather than leaving them present (possibly `null`) for the new seeding to fill; only `recursive-refine.yaml` has this presence assertion — `autodev.yaml` and `eval-driven-development.yaml` have no equivalent test pinning their `context:` keys.
- `scripts/tests/test_next_action.py`, class `TestNextActionConfigFirstThresholds` (lines 404-560+) — closest existing precedent for "config seeds a threshold with a fallback chain" test structure; reference for the new `run.py` seeding tests' precedence assertions (config → CLI/loop-YAML → hardcoded default).
- `scripts/tests/test_fsm_schema.py`, class `TestLoopConfigOverrides` (lines 2188-2263) — round-trips `LoopConfigOverrides.readiness_threshold`/`.outcome_threshold`; unaffected unless the fix also wires the `config:` block (see `LoopConfigOverrides` note above), in which case add assertions that the block's values flow into `fsm.context`.

## Implementation Steps

1. Confirm whether resolved `LoopConfig.readiness_threshold` is interpolable from state
   actions today; if not, decide between Option A (add the plumbing) and Option B.
2. Apply the chosen resolution to `autodev.yaml`, `recursive-refine.yaml`,
   `eval-driven-development.yaml`.
3. Remove/correct the misleading `# canonical:` comments.
4. Add a test in `scripts/tests/test_builtin_loops.py` asserting that a project config
   with a non-default `commands.confidence_gate.outcome_threshold` changes the
   effective threshold these loops gate on.
5. Add a test asserting `--context outcome_threshold=…` still overrides config.
6. Update `ll-loop info` output so the displayed threshold is the resolved one.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Implement the seeding in `scripts/little_loops/cli/loop/run.py` (~line 227), extending the existing `if "include" not in fsm.context:` pattern with two more guarded blocks for `readiness_threshold`/`outcome_threshold` reading from `commands.confidence_gate.*` via `BRConfig`.
8. **Resolved (2026-07-24, `/ll:confidence-check` follow-up):** `scripts/little_loops/cli/loop/lifecycle.py` builds `fsm.context` directly at load time (lines 512-527) and does its own `handoff_threshold` env injection (539-545) — it does **not** delegate to `run.py`. It is a separate FSM-launch path and needs the same `readiness_threshold`/`outcome_threshold` seeding logic added (duplicated inline or factored into a shared helper both `run.py` and `lifecycle.py` call), not just a "confirm and skip" check.
9. **Resolved (2026-07-24, `/ll:decide-issue` follow-up):** leave `LoopConfigOverrides.readiness_threshold`/`.outcome_threshold` (`fsm/schema.py` lines 911-973) display-only in `cli/loop/info.py` — do not wire it into the seeding. Rationale: Option B was selected specifically to avoid new config-merge/interpolation surface (10/12 vs Option A's 4/12, largely on Simplicity/Risk); feeding `LoopConfigOverrides` in now reintroduces that complexity for a dataclass with zero functional consumers today, and would create two competing config inputs (`commands.confidence_gate.*` seeding vs. `config.readiness_threshold`) with no established precedence between them. Mark `docs/guides/LOOPS_GUIDE.md`'s `config:`-block precedence chain as aspirational in the docs update (step 13) rather than implementing it here; a follow-up issue can revisit if a real need for the `config:` block emerges.
10. **Resolved:** the seeded default for unconfigured projects is 85/65 (the `commands.confidence_gate` schema default in `config-schema.json` and `init/tui.py`), not the loops' current hardcoded 90/75 literals — this is an intentional behavior change, not a bug to avoid. Call it out explicitly in the changelog per the existing Impact note.
11. Add `TestLoopRunConfidenceThresholdContextInjection` to `scripts/tests/test_loop_cli_defaults.py`, mirroring `TestLoopRunIncludeContextInjection` (lines 332-433): config-seeds-context, `--context` overrides config, absent config leaves default unset.
12. Update `test_context_thresholds_defined` in `scripts/tests/test_builtin_loops.py` (lines 5797-5803) if `recursive-refine.yaml`'s `context:` keys are removed rather than left present with a fallback value.
13. Update `docs/reference/CONFIGURATION.md` (line 444) and `docs/guides/LOOPS_REFERENCE.md` (lines 135, 138, 1087-1088) to describe the now-working config override instead of the currently-false claim.

## Impact

- **Severity**: Medium-high — silently overrides project configuration on the decision
  that determines whether work gets done, and misattributes the resulting deferral to
  issue quality.
- **Scope**: Three built-in loops, including `autodev` (the primary single-issue
  driver) and `recursive-refine`.
- **Risk of fix**: Changing effective thresholds will change gating behavior for
  projects that set config — which is the point, but worth calling out in the
  changelog since some projects may be unknowingly relying on the 90/75 literals.
  For unconfigured projects, the effective default also moves from the loops'
  current hardcoded 90/75 to the confirmed `commands.confidence_gate` schema
  default of 85/65 — an intentional, slightly-looser gate, not an oversight.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Orchestration layers; loop/config interaction |
| `config-schema.json` | `commands.confidence_gate` schema |
| `.claude/CLAUDE.md` | Loop Authoring rules; Issue File Format deferral discriminators |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-24_

**Readiness Score**: 98/100 → READY
**Outcome Confidence**: 80/100 → HIGH

### Outcome Risk Factors
- Change surface spans ~8 files across two layers (seeding logic in `run.py`/`lifecycle.py`, three loop YAMLs, one new test class, one existing test update, two docs). Steps 8, 9, and 10 — previously open sub-decisions — are now all marked Resolved in Implementation Steps, so this is largely mechanical execution against an already-decided design rather than judgment calls made mid-implementation.

## Resolution

_Implemented 2026-07-24 via Option B (context-default seeding)._

**Seeding helper.** `seed_confidence_thresholds(context, config=None)` in
`scripts/little_loops/cli/loop/_helpers.py` fills `readiness_threshold` /
`outcome_threshold` from `commands.confidence_gate.*`, skipping any key already
present. Precedence: `--context` > loop YAML `context:` literal >
`commands.confidence_gate.*` > `ConfidenceGateConfig` defaults (85/65).

**Call sites (three, not two).** `cli/loop/run.py` (beside the existing
`loops.run_defaults.include` injection) and `cli/loop/lifecycle.py` (the separate
resume launch path, per step 8) — plus `fsm/executor.py::_execute_sub_loop`,
which step 8 did not anticipate. That third site is load-bearing: `autodev` and
`recursive-refine` are invoked as sub-loops by `scan-and-implement`,
`auto-refine-and-implement`, `issue-refinement`, `rn-build`, and
`sprint-build-and-validate`, and a child FSM never passes through `run.py`.
Without it, removing the YAML literals would have raised `InterpolationError` on
every sub-loop invocation.

**Loop YAMLs.** The `context.readiness_threshold` / `outcome_threshold` literals
were removed from `autodev.yaml`, `recursive-refine.yaml`, and
`eval-driven-development.yaml` (a literal shadows the seeding under the same
guard that makes `--context` win) and replaced with a comment naming the config
key. The misleading `# canonical:` comments are gone.

**Out of scope, deliberately.** `refine-to-ready-issue.yaml` keeps its own 85/65
literals — `test_builtin_loops.py:1665` pins them under BUG-2035, and its gate
states already read `commands.confidence_gate` directly. `LoopConfigOverrides`
stays display-only per step 9; `LOOPS_GUIDE.md`'s `config:`-block precedence
chain is now labeled aspirational rather than implemented.

**Behavior change:** unconfigured projects now gate at 85/65 instead of 90/75
(step 10 — intentional, called out in the changelog).

**Verification:** `python -m pytest scripts/tests/` → 16115 passed, 38 skipped.
(One unrelated pre-existing failure, `test_string_present_in_doc[README.md-39
typed CLI tools]`, reproduces on clean `main`.) `ruff check` clean, `mypy` clean,
`ll-loop validate` passes for all three loops with no new warnings.
`ll-loop show autodev` now prints `gate: readiness_threshold=85,
outcome_threshold=65`.

## Session Log
- `/ll:manage-issue` - 2026-07-24T21:39:14Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/15d1fb18-c849-4828-aeff-4a5464ee6ee8.jsonl`
- `/ll:confidence-check` - 2026-07-24T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/806d3d5d-9481-4f49-9763-99583ba281d1.jsonl`
- `/ll:wire-issue` - 2026-07-24T20:38:19 - `4083d30b-3c26-4c92-a9d7-cef0b98ab1cb.jsonl`
- `/ll:decide-issue` - 2026-07-24T20:09:38 - `9011fd25-bf92-4159-a529-61f1828a9755.jsonl`
- `/ll:refine-issue` - 2026-07-24T19:57:55 - `7f73ef49-23cc-45fa-8bf9-7ec473e8ecad.jsonl`
- `/ll:capture-issue` - 2026-07-24T19:52:19Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

open
