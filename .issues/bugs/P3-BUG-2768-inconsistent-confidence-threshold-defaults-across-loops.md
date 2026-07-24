---
id: BUG-2768
title: Confidence threshold defaults disagree across built-in loops, so gate verdicts
  depend on which loop touched the issue
type: bug
status: done
priority: P3
labels:
- bug
- fsm
- loops
- consistency
captured_at: 2026-07-24
completed_at: '2026-07-24T22:06:25Z'
discovered_date: 2026-07-24
discovered_by: capture-issue
discovered_commit: 8926f14b
relates_to:
- BUG-2767
decision_needed: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 23
---

# BUG-2768: Confidence threshold defaults disagree across built-in loops

## Summary

Every built-in loop that gates on readiness/outcome confidence picks its own default
pair, and no two families agree. The same issue with the same scores therefore passes
in one loop and defers in another, with no user-visible signal that the bar moved.

## Current Behavior

Observed defaults (readiness / outcome):

| Source | readiness | outcome |
|--------|-----------|---------|
| `config/automation.py` `ConfidenceGateConfig` (ll-config default) | 85 | 65 |
| `loops/autodev.yaml` | 90 | 75 |
| `loops/recursive-refine.yaml` | 90 | 75 |
| `loops/eval-driven-development.yaml` | 90 | 75 |
| `loops/refine-to-ready-issue.yaml` | 85 | 65 |
| `loops/rn-implement.yaml` | 85 | 75 |
| `loops/rn-remediate.yaml` | 85 | 75 |
| `init/tui.py` (written into generated config) | 85 | *(omitted)* |

Concrete divergence: an issue scoring `confidence 88 / outcome 70` is **ready** under
`refine-to-ready-issue` (85/65), **outcome-blocked** under `rn-implement` (85/75), and
**readiness-blocked** under `autodev` (90/75). `refine-to-ready-issue` is routinely the
loop that declares an issue ready — and it uses the *loosest* pair — so issues get
handed to `autodev` already stamped "ready" and are then rejected by a stricter bar.

`init/tui.py` writes `{"enabled": True, "readiness_threshold": 85}` with no
`outcome_threshold`, so a freshly-initialized project has an asymmetric config that
pins only half the gate.

## Expected Behavior

One canonical default pair, defined once (in `config/automation.py`'s
`ConfidenceGateConfig`), inherited by every built-in loop. A loop that genuinely needs
a stricter bar declares the deviation explicitly with a comment justifying it, rather
than silently drifting. `init/tui.py` writes both halves or neither.

## Root Cause

- **File**: `scripts/little_loops/loops/*.yaml`
- **Anchor**: each loop's top-level `context:` block
- **Cause**: Each loop was authored independently with its thresholds inlined as
  literals, with no shared source and no test asserting agreement. The literals then
  drifted as loops were tuned in isolation. This is the same missing-single-source
  problem as [[BUG-2767]] (which covers the config-resolution half); this issue covers
  the value-agreement half.

## Steps to Reproduce

1. `grep -rn "readiness_threshold:\|outcome_threshold:" scripts/little_loops/loops/`
2. Observe the six distinct literal pairs above.
3. Take an issue at `confidence 88 / outcome 70`; run it through
   `refine-to-ready-issue` (passes) then `autodev` (defers).

## Motivation

Cross-loop disagreement makes "ready" meaningless as a handoff contract: the refine
family blesses an issue that the implement family then rejects, and the rejection is
recorded as a quality verdict on the issue (`low_readiness` / `oversized_atomic`)
rather than as a threshold mismatch. Users cannot reason about why a loop deferred
without reading each loop's YAML.

## Proposed Solution

1. Pick the canonical pair. Recommendation: **85 / 65**, matching
   `ConfidenceGateConfig`'s existing defaults and `refine-to-ready-issue` — i.e. make
   the already-documented default real, rather than promoting one loop's drift.
2. Have every built-in loop inherit it (mechanism comes from [[BUG-2767]]; this issue
   is the value reconciliation and should land after or alongside it).
3. Where a loop keeps a deliberate deviation, require an inline comment stating why.
4. Fix `init/tui.py` to write both halves or neither.
5. Add a test in `scripts/tests/test_builtin_loops.py` that walks every
   `loops/*.yaml` and asserts each declared threshold either matches the canonical
   default or is accompanied by an explicit deviation marker — so future drift fails
   the suite rather than shipping silently.

## Integration Map

- `scripts/little_loops/config/automation.py` — `ConfidenceGateConfig`, the canonical default
- `scripts/little_loops/loops/autodev.yaml`
- `scripts/little_loops/loops/recursive-refine.yaml`
- `scripts/little_loops/loops/eval-driven-development.yaml`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- `scripts/little_loops/loops/rn-implement.yaml`
- `scripts/little_loops/loops/rn-remediate.yaml`
- `scripts/little_loops/init/tui.py` — generated-config threshold write
- `scripts/tests/test_builtin_loops.py` — new drift test

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py` — `next-action --outcome-threshold` argparse default is `70` (not 65); `check-readiness --readiness`/`--outcome` argparse defaults are `90`/`75` — both are independent literal sources, decoupled from `ConfidenceGateConfig`, used only when `.ll/ll-config.json` is absent
- `scripts/little_loops/cli/issues/next_action.py` — inline `getattr(args, "outcome_threshold", 65)` fallback (line 35); already matches canonical by coincidence but is a fourth independent literal
- `scripts/little_loops/cli/issues/check_readiness.py` — reads `commands.confidence_gate.{readiness_threshold,outcome_threshold}` from config (lines 37-42)
- `scripts/little_loops/cli/loop/lifecycle.py`, `scripts/little_loops/cli/loop/run.py`, `scripts/little_loops/cli/loop/info.py` — access `config.commands.confidence_gate` fields
- `scripts/little_loops/fsm/schema.py` — `LoopConfigOverrides`/`OverrideConfig` (lines 920-969) is the override pass-through every loop's `context:`/`--context` funnels threshold values through; no embedded defaults itself
- `scripts/little_loops/config/__init__.py`, `scripts/little_loops/config/core.py` — re-export/construct `ConfidenceGateConfig`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — stale numbers at lines 132, 135, 426-427, 595, 604-605, 1087-1088 (mix of 90/75 and 85/70 examples that will disagree with the new canonical 85/65)
- `docs/reference/CONFIGURATION.md:444` — already-wrong "`refine-to-ready-issue` … (defaults: 90/75)" claim; that loop is actually 85/65 today
- `skills/configure/show-output.md:86-87` — config-editor template hardcodes `(default: 85)` / `(default: 70)` next to the confidence_gate placeholders; the `70` disagrees with both `ConfidenceGateConfig` (65) and the proposed canonical pair
- `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/guides/LOOPS_GUIDE.md` — general confidence_gate/threshold documentation to sanity-check for drift after the reconciliation (CLI.md's own 85/65 table entries are already correct and need no change)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_implement.py:765-766` (`test_context_defaults_match_spec`, asserts `ctx["outcome_threshold"] == 75`) and `:1448-1449` (shell-substitution fixture using `"75"`) — will break once `rn-implement.yaml` reconciles to 65; update in lockstep
- `scripts/tests/test_rn_remediate.py:700` (docstring), `:1111,1161-1162` (`test_context_defaults_match_spec`, asserts `ctx["outcome_threshold"] == 75`), `:1518-1519` (`"OUTCOME_THRESHOLD=75"`) — same update needed for `rn-remediate.yaml`
- `scripts/tests/test_builtin_loops.py:1664` `test_context_fallbacks_match_selector_defaults` (inside the `refine-to-ready-issue` test class) — already asserts 85/65, no change needed, but is the closest existing precedent/template for the new `TestConfidenceThresholdDefaultParity` class (style analog alongside `TestLearningGateConsistency:11788` and `TestAutodevRnImplementDeferralParity:5608`)
- **Gap**: no existing test asserts exact `context.readiness_threshold`/`outcome_threshold` values for `autodev.yaml`, `recursive-refine.yaml`, or `eval-driven-development.yaml` (only key-presence checks exist at `test_builtin_loops.py:5798-5801`) — the new drift test must cover these three or the 90/75→85/65 change ships unverified
- `scripts/tests/test_init_tui.py:798,1120` — assert `config["commands"]["confidence_gate"]["readiness_threshold"] == 85` but have no matching `outcome_threshold` value assertion; add one alongside `init/tui.py`'s fix so both halves are test-covered
- `scripts/tests/test_config.py` `TestConfidenceGateConfig` (lines 465-494, 877-886) already exercises `ConfidenceGateConfig`'s 85/65 default and legacy fallback — unaffected, no change needed (confirms the dataclass itself is already canonical; only the loop YAMLs drift)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Confirmed exact literal locations (no other `loops/*.yaml` declares these keys):
  `autodev.yaml:33-34` (90/75), `recursive-refine.yaml:33-34` (90/75),
  `eval-driven-development.yaml:16-17` (90/75), `rn-implement.yaml:25-26` (85/75),
  `refine-to-ready-issue.yaml:16-17` (85/65), `rn-remediate.yaml:58-59` (85/75).
- `ConfidenceGateConfig` (`scripts/little_loops/config/automation.py:139-153`) defaults
  `readiness_threshold=85`, `outcome_threshold=65` (line 143-144), with a legacy
  `from_dict` fallback (`legacy = data.get("threshold", 85)` at line 149) — this
  dataclass matches `refine-to-ready-issue.yaml` exactly and disagrees with all five
  other loops.
- `init/tui.py:721` writes only `{"enabled": True, "readiness_threshold": 85}` —
  `outcome_threshold` is omitted entirely, so a freshly-init'd project silently
  inherits the dataclass's `65` default regardless of what the loop YAMLs expect (75
  in 5 of 6 cases).
- Five of six loops carry a `# canonical: commands.confidence_gate.readiness_threshold
  in ll-config.json` comment; `rn-implement.yaml:25-26` has no such comment, so even
  the "points at canonical source" annotation is inconsistently applied — a fix should
  add it there too.
- `grep -rl "BUG-2767" scripts/little_loops scripts/tests` returns no matches — the
  single-source config-resolution mechanism this issue's Implementation Steps assumes
  BUG-2767 lands first does not exist in code yet. Each loop currently re-reads
  `commands.confidence_gate` from `ll-config.json` independently via inline Python
  (`cg.get('readiness_threshold', ${context.readiness_threshold})`), using its own
  YAML literal only as the fallback when config is absent.
- Closest existing test analogs for the proposed drift test in
  `scripts/tests/test_builtin_loops.py` (12,381 lines): `TestLearningGateConsistency`
  (line 11788) and `TestAutodevRnImplementDeferralParity` (line 5608) — both are
  parity-style tests comparing behavior/config across specific loop pairs. A new
  `TestConfidenceThresholdDefaultParity` class fits alongside them.

#### Re-research pass — 2026-07-24 (post-BUG-2767)

_Added by `/ll:refine-issue` — the findings above predate commit `909a3591` and are
now partially stale. Corrections:_

- **[[BUG-2767]] has landed and is `done`** (commit `909a3591`, "fix(loops): seed
  confidence-gate thresholds from ll-config"). Implementation Step 1's hard
  dependency and the Confidence Check "Dependencies Satisfied" concern are both
  **resolved** — the single source now exists. The earlier finding that
  `grep -rl "BUG-2767"` returns no matches is obsolete; it now matches
  `cli/loop/_helpers.py`, `cli/loop/run.py`, `cli/loop/lifecycle.py`,
  `fsm/executor.py`, `autodev.yaml`, `recursive-refine.yaml`,
  `eval-driven-development.yaml`, and two test modules.

- **The inheritance mechanism** is
  `seed_confidence_thresholds(context, config=None)` at
  `scripts/little_loops/cli/loop/_helpers.py:1354-1367`. It is a *fill-if-absent*
  seeder: it early-returns when both keys are already present, then fills each
  missing key from `config.commands.confidence_gate.{readiness,outcome}_threshold`.
  Precedence is therefore **`--context` > loop YAML `context:` literal > ll-config >
  `ConfidenceGateConfig` defaults**. Call sites: `cli/loop/run.py` (normal launch),
  `cli/loop/lifecycle.py` (resume), and `fsm/executor.py:885-887`
  (`_execute_sub_loop`, so child loops seed too).

- **Consequence for this issue: a YAML literal is now not merely inconsistent, it is
  actively shadowing.** Because the seeder skips any key already in context, the
  three loops that still declare literals silently override whatever the project set
  in `.ll/ll-config.json`. Reconciling the *values* is no longer sufficient —
  the literals must be **deleted**, not renumbered.

- **Remaining scope is 3 loops, not 6.** Current state on `main`:

  | Loop | `context:` thresholds | Status |
  |------|----------------------|--------|
  | `autodev.yaml:33-36` | none (comment block explaining seeding) | ✅ fixed by BUG-2767 |
  | `recursive-refine.yaml:33-36` | none (comment block) | ✅ fixed by BUG-2767 |
  | `eval-driven-development.yaml:16-19` | none (comment block) | ✅ fixed by BUG-2767 |
  | `refine-to-ready-issue.yaml:16-17` | `85` / `65` + `# canonical:` comments | ❌ still shadows |
  | `rn-implement.yaml:25-26` | `85` / `75` | ❌ still shadows |
  | `rn-remediate.yaml:58-59` | `85` / `75` | ❌ still shadows |

  The three fixed loops carry the canonical replacement comment block to copy
  verbatim (`autodev.yaml:33-36`), including the `(BUG-2767)` back-reference.

- **`rn-remediate.yaml` needs a second edit the Integration Map misses**: its
  `parameters:` block at lines 36-43 documents `default: 85` / `default: 75` in the
  `description:` strings. Those prose defaults must be updated (or reworded to point
  at the config) alongside the `context:` deletion, or the YAML self-documents a
  value it no longer uses. `rn-implement.yaml` has no equivalent parameter-doc block.

- **Sub-loop pass-through is already correct and needs no change**: `rn-implement`
  passes `readiness_threshold`/`outcome_threshold` into `rn-remediate` via `with:`
  (`rn-remediate.yaml:17-18` docstring, `rn-implement.yaml:756-757`). Once
  `rn-implement`'s literals are deleted, its own context is seeded from config and
  the correct values propagate to the child automatically.

- **The drift test already exists in part** —
  `scripts/tests/test_builtin_loops.py:12387` `TestConfidenceGateThresholdsNotHardcoded`
  parametrizes over `LOOPS = ("autodev", "recursive-refine", "eval-driven-development")`
  and asserts (a) neither key appears in `context:`, (b) no `# canonical:
  commands.confidence_gate` comment survives, (c) `seed_confidence_thresholds` supplies
  every `${context.*_threshold}` the YAML references. **The cheapest correct fix for
  Implementation Step 5 is to add the three remaining loop names to that existing
  `LOOPS` tuple**, not to author a new `TestConfidenceThresholdDefaultParity` class as
  the earlier research suggested. Note assertion (b) will then fire on
  `refine-to-ready-issue.yaml:16-17`'s `# canonical:` comments, so those must go too.

- **Test fallout confirmed still present** (line numbers verified against `main`):
  `test_rn_implement.py:766` (`assert ctx["outcome_threshold"] == 75`) and `:1449`
  (`.replace("${context.outcome_threshold}", "75")`); `test_rn_remediate.py:1111`
  (docstring), `:1162` (`assert ctx["outcome_threshold"] == 75`), `:1519`
  (`"OUTCOME_THRESHOLD=75"`). Once the literals are deleted, `ctx[...]` assertions
  must become either a `not in ctx` check (mirroring
  `TestConfidenceGateThresholdsNotHardcoded.test_thresholds_absent_from_context`) or a
  post-`seed_confidence_thresholds` assertion; the string-substitution fixtures at
  `:1449` / `:1519` are test-local stand-ins and can simply move to `"65"`.

- **CLI argparse defaults confirmed divergent** (`cli/issues/__init__.py`):
  `next-action --outcome-threshold` default `70` (line 583),
  `check-readiness --readiness` default `90` (line 672) and `--outcome` default `75`
  (line 679). Both consumers read `.ll/ll-config.json` first and use the argparse
  value only as a fallback (`check_readiness.py:31-42`, `next_action.py:34-40`), so
  these are dead literals in any configured project — but they are exactly the
  "unconfigured project" path this issue is about, and `check-readiness` is the
  binary `autodev.yaml:287-289` and `rn-remediate.yaml:191-192` shell out to.

- **`init/tui.py:721` unchanged** — still writes
  `{"enabled": True, "readiness_threshold": 85}` with no `outcome_threshold`.
  BUG-2767 did not touch it.

##### Decision point: what to do with `rn-implement` / `rn-remediate`'s outcome `75`

> **Selected:** Option A — reuses the already-shipped BUG-2767 comment-block
> pattern verbatim and extends the existing `TestConfidenceGateThresholdsNotHardcoded`
> test class with a one-line tuple edit; Option B has no existing mechanism for a
> non-shadowing per-loop deviation and would recreate the cross-family disagreement
> this issue exists to fix.

**Option A**: Delete the literals from all three loops unconditionally, so every
built-in loop gates at the config value (85/65 unconfigured). Uniform, satisfies
"one canonical default pair" as written, and makes
`TestConfidenceGateThresholdsNotHardcoded` cover all six loops with no exemption
list. Cost: loosens the implement family's outcome bar from 75 → 65, and the
`rn-*` test assertions must be rewritten rather than renumbered.

**Option B**: Delete the literals from `refine-to-ready-issue.yaml` only (its 85/65
already equals the canonical pair, so removing it is pure de-shadowing with zero
behavior change), and keep `rn-implement` / `rn-remediate` at outcome `75` as a
declared deviation — but move it out of `context:` into an explicit,
non-shadowing form so config still wins when set, with the justifying comment
Proposed Solution step 3 requires. Cost: preserves a second bar, so "ready" still
does not mean the same thing across the refine → implement handoff, which is the
defect this issue exists to fix.

**Recommended**: Option A — the Motivation section's whole complaint is that a
stricter implement-family bar rejects issues the refine family blessed, and the
Impact section already accepts "loosening … will let through issues it currently
defers. That is the intended correction." Option B re-creates the reported bug in a
tidier form. A project wanting the stricter bar sets
`commands.confidence_gate.outcome_threshold: 75` once in `ll-config.json` and gets it
everywhere — which is precisely the capability BUG-2767 just shipped.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-24.

**Selected**: Option A — delete the threshold literals from all three remaining loops
(`refine-to-ready-issue.yaml`, `rn-implement.yaml`, `rn-remediate.yaml`) unconditionally.

**Reasoning**: Option A is a direct copy of the comment-block pattern BUG-2767 already
shipped for `autodev.yaml`, `recursive-refine.yaml`, and `eval-driven-development.yaml`,
and its test coverage is a one-line extension of the existing
`TestConfidenceGateThresholdsNotHardcoded.LOOPS` tuple — no new code or test
infrastructure required. Option B's core mechanism (a per-loop declared deviation that
is simultaneously non-shadowing and explicit) does not exist anywhere in the codebase,
would require new plumbing in `seed_confidence_thresholds` or a new test-exemption path,
and — per the issue's own Motivation section — would recreate the exact cross-family
refine-vs-implement disagreement this issue was filed to eliminate.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B | 0/3 | 0/3 | 1/3 | 1/3 | 2/12 |

**Key evidence**:
- Option A: Matches `autodev.yaml:32-36`'s already-shipped comment-block pattern exactly;
  extends `TestConfidenceGateThresholdsNotHardcoded` (`test_builtin_loops.py:12387`) by
  adding three names to its `LOOPS` tuple — all three assertions already exist generically.
- Option B: No existing "config-wins, but loop declares a different default" primitive
  in `seed_confidence_thresholds` (`cli/loop/_helpers.py:1341-1367`); would conflict with
  `test_thresholds_absent_from_context`'s hard presence check and preserve the
  refine/implement disagreement the issue reports as its defect.

## Implementation Steps

1. Land [[BUG-2767]]'s config-resolution mechanism first (this issue is a no-op
   without a single source to inherit from).
2. Decide the canonical pair; record the decision via `ll-issues decisions add`.
3. Update the six loops to inherit, keeping only justified deviations.
4. Fix `init/tui.py`.
5. Add the drift test.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/little_loops/cli/issues/__init__.py` — reconcile `next-action --outcome-threshold` (currently `70`) and `check-readiness --readiness`/`--outcome` (currently `90`/`75`) argparse defaults to 85/65, since these are independent literal fallbacks used when config is absent.
7. Update `scripts/tests/test_rn_implement.py:765-766,1448-1449` and `scripts/tests/test_rn_remediate.py:700,1111,1161-1162,1518-1519` — change asserted `outcome_threshold` from `75` to `65` in lockstep with the YAML changes.
8. Extend `scripts/tests/test_init_tui.py` (near lines 798, 1120) with an `outcome_threshold` value assertion alongside the existing `readiness_threshold == 85` checks, so `init/tui.py`'s fix (step 4) is test-covered on both halves.
9. Add exact-value threshold assertions for `autodev.yaml`, `recursive-refine.yaml`, and `eval-driven-development.yaml` to the new drift test (step 5) — no existing test asserts specific numbers for these three loops today, only key-presence.
10. Update stale-number documentation: `docs/guides/LOOPS_REFERENCE.md` (lines 132, 135, 426-427, 595, 604-605, 1087-1088), `docs/reference/CONFIGURATION.md:444`, and `skills/configure/show-output.md:86-87`.

### Re-research addendum (added by `/ll:refine-issue`, 2026-07-24)

_Steps 1–5 above were written before [[BUG-2767]] landed. Amendments:_

- **Step 1 is satisfied** — BUG-2767 is `done` (commit `909a3591`). This issue is
  now unblocked and can proceed immediately.
- **Step 3 shrinks to 3 loops** (`refine-to-ready-issue`, `rn-implement`,
  `rn-remediate`) and changes in kind: **delete** the `context:` literals rather than
  renumber them, because `seed_confidence_thresholds` fills only absent keys — a
  literal at any value shadows `ll-config`. Copy the explanatory comment block from
  `autodev.yaml:33-36` in their place, and drop
  `refine-to-ready-issue.yaml`'s two `# canonical:` comments.
- **New sub-step**: update `rn-remediate.yaml:36-43`'s `parameters:` descriptions,
  which document `default: 85` / `default: 75` in prose.
- **Step 5 becomes an extension, not a new class**: add the three loop names to
  `TestConfidenceGateThresholdsNotHardcoded.LOOPS`
  (`scripts/tests/test_builtin_loops.py:12395`). It already asserts absence,
  no-misleading-comment, and seed-supplies-referenced-keys. No
  `TestConfidenceThresholdDefaultParity` class is needed. Step 9's "exact-value
  assertions for `autodev`/`recursive-refine`/`eval-driven-development`" is likewise
  obsolete — those three are already covered by that class.
- **Step 7 changes shape**: with the literals deleted (not renumbered), the
  `ctx["outcome_threshold"] == 75` assertions at `test_rn_implement.py:766` and
  `test_rn_remediate.py:1162` become `not in ctx` checks; only the string-fixture
  substitutions at `test_rn_implement.py:1449` and `test_rn_remediate.py:1519` are a
  straight `75` → `65` swap.
- **Resolve the Option A / B decision** (see Codebase Research Findings) before
  touching `rn-implement` / `rn-remediate` — it determines whether steps 3 and 7
  apply to those two loops at all.

## Impact

- **Severity**: Medium — no crash, but gate verdicts are unpredictable across the
  refine → implement handoff and are misreported as issue-quality problems.
- **Scope**: Six built-in loops plus the init template.
- **Risk of fix**: Loosening `autodev` from 90/75 to 85/65 will let through issues it
  currently defers. That is the intended correction, but it should be called out in
  the changelog.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Orchestration layers; refine → implement handoff |
| `config-schema.json` | `commands.confidence_gate` schema |
| `.claude/CLAUDE.md` | Loop Authoring rules |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-24_

**Readiness Score**: 81/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 78/100 → Good

### Concerns
- Dependencies Satisfied scored low (6/20): Implementation Step 1 states this issue
  is "a no-op without a single source to inherit from" and requires [[BUG-2767]] to
  land first. `grep -rl "BUG-2767" scripts/little_loops scripts/tests` confirms that
  mechanism does not exist in code yet — BUG-2767 is still `open`.

### Gaps to Address
- Sequence this issue behind BUG-2767, or descope Implementation Step 1's hard
  dependency if the value-reconciliation work can proceed independently of the
  config-resolution mechanism.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The sole blocking concern above is resolved.** [[BUG-2767]] is `done` as of
  commit `909a3591`; `seed_confidence_thresholds` exists at
  `scripts/little_loops/cli/loop/_helpers.py:1354` and is wired into `run.py`,
  `lifecycle.py`, and `fsm/executor.py:885`. The "Dependencies Satisfied 6/20" score
  reflects a state of the world that no longer holds — re-run
  `/ll:confidence-check` to get a current readiness score before gating on this one.

## Resolution

Implemented Option A (per Decision Rationale) on 2026-07-24, TDD-first:

- Deleted the shadowing `readiness_threshold`/`outcome_threshold` `context:` literals
  from `refine-to-ready-issue.yaml` (85/65 + `# canonical:` comments),
  `rn-implement.yaml` (85/75), and `rn-remediate.yaml` (85/75), replacing each with
  the BUG-2767 comment block from `autodev.yaml` — every built-in loop now gates at
  the `seed_confidence_thresholds` config value (85/65 unconfigured).
- Updated `rn-remediate.yaml` `parameters:` descriptions to point at the config
  seeding instead of documenting stale `default: 85` / `default: 75` prose.
- `init/tui.py` now writes both halves: `{"enabled": true, "readiness_threshold": 85,
  "outcome_threshold": 65}`.
- Reconciled CLI argparse fallbacks in `cli/issues/__init__.py`:
  `next-action --outcome-threshold` 70→65, `check-readiness --readiness` 90→85,
  `--outcome` 75→65.
- Drift test: extended `TestConfidenceGateThresholdsNotHardcoded.LOOPS` to all six
  loops; rewrote `test_context_fallbacks_match_selector_defaults` to assert
  absence + seeded parity; updated `test_rn_implement.py`/`test_rn_remediate.py`
  assertions to `not in ctx` (+ fixture 75→65); pinned 85/65 in
  `test_next_action.py` fallback tests; added `outcome_threshold == 65` assertions
  in `test_init_tui.py`.
- Docs: `LOOPS_REFERENCE.md` threshold tables, `CONFIGURATION.md` seeding section
  (now lists all six loops, drops the stale refine-to-ready literal claim),
  `skills/configure/show-output.md` `(default: 70)`→`(default: 65)`.

Verification: full suite 16,124 passed (1 pre-existing unrelated failure:
`test_string_present_in_doc[README.md-39 typed CLI tools-FEAT-1045]`, stale README
count on main); `ll-loop validate` clean on all three loops; ruff + mypy clean.

Behavior note (intended correction): rn-implement/rn-remediate outcome bar loosens
75→65 on unconfigured projects; set `commands.confidence_gate.outcome_threshold: 75`
in `ll-config.json` to restore the stricter bar everywhere.

## Session Log
- `/ll:manage-issue` - 2026-07-24T22:05:48Z - `cc1bbbf9-cede-4b6a-9be8-098675d33df0.jsonl`
- `/ll:confidence-check` - 2026-07-24T21:49:56 - `04061454-ceb8-4e2d-818f-a77d9e069cb5.jsonl`
- `/ll:decide-issue` - 2026-07-24T21:48:33 - `cbab67d4-fbca-4a1b-b5c3-7069edd3d39d.jsonl`
- `/ll:refine-issue` - 2026-07-24T21:45:14 - `82878a94-ddfe-427e-84b4-0ad47ad1ca6e.jsonl`
- `/ll:confidence-check` - 2026-07-24T00:00:00Z - `6a4e4ad5-d137-4b01-b2f1-9253992162c7.jsonl`
- `/ll:wire-issue` - 2026-07-24T20:11:45 - `827a0af0-fe97-4048-8eea-b99754544e6d.jsonl`
- `/ll:refine-issue` - 2026-07-24T19:57:43 - `7f73ef49-23cc-45fa-8bf9-7ec473e8ecad.jsonl`
- `/ll:capture-issue` - 2026-07-24T19:52:19Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

done
