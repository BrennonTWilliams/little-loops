---
id: ENH-1912
title: Name router/composer/supervisor as selectable shapes in create-loop wizard
type: ENH
priority: P4
status: done
captured_at: '2026-06-03T20:59:38Z'
completed_at: '2026-06-04T01:12:03Z'
discovered_date: 2026-06-03
discovered_by: capture-issue
relates_to:
- EPIC-1811
labels:
- discoverability
- orchestration
- create-loop
- wizard
confidence_score: 98
outcome_confidence: 80
score_complexity: 20
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 20
---

# ENH-1912: Name router/composer/supervisor as selectable shapes in create-loop wizard

## Summary

Surface the orchestration loop shapes little-loops already ships or is building —
**router** (dynamic dispatch), **composer** (goal → multi-loop DAG), and **supervisor**
(adaptive re-plan) — as named, selectable pattern templates in the `create-loop` wizard.
This is a discoverability fix, not a new capability: `loop-router` is a shipped built-in and
the composer/adaptive variants are specced under EPIC-1811, but the wizard's 7 templates don't
name these orchestration shapes, so a user authoring an orchestration loop has no on-ramp to
clone them.

## Current Behavior

The `create-loop` wizard (`/ll:create-loop`, driven by `skills/create-loop/templates.md`) offers
7 named shapes ("Fix until clean", "Drive a metric", "Harness a skill", "Optimize a harness
(meta-loop)", etc.) plus 3 RL patterns. None of the branches or entries name orchestration
shapes (router, composer, supervisor). `loop-router.yaml` ships as a built-in but is not
referenced anywhere a wizard user would encounter it. A user wanting to build an orchestration
loop has no wizard-guided on-ramp and must discover `loop-router.yaml` by browsing the
filesystem directly.

## Expected Behavior

The wizard includes an "Orchestration" branch (or equivalent entries) that:
- Names the three shapes — **router** (dynamic dispatch via `loop:` interpolation), **composer**
  (goal → multi-loop DAG via `depends_on`), **supervisor** (adaptive re-plan via `reassess`
  gate) — and explains when to pick each.
- Points the user at the canonical built-in to clone (`loop-router.yaml` for router;
  composer/adaptive stubs gated on EPIC-1811 status).
- Cross-links to `docs/guides/LOOPS_GUIDE.md` so wizard and guide agree on terminology.

## Motivation

`create-loop`'s `templates.md` offers 7 shapes ("Fix until clean", "Drive a metric",
"Harness a skill", "Optimize a harness (meta-loop)", etc.) plus 3 RL patterns. None of them
name the orchestration family even though the primitives exist:
- `scripts/little_loops/loops/loop-router.yaml` — runtime dynamic dispatch
  (`loop: "${captured.chosen.output}"`), shipped (FEAT-1654, done).
- `loop-composer` (FEAT-1808) and adaptive re-plan (FEAT-1809) under EPIC-1811.

**Why:** A review comparing little-loops to `revfactory/harness` initially mis-judged
"supervisor / dynamic dispatch" as a gap — precisely because the capability is real but not
*named* anywhere a loop author would look. If a careful review missed it, users will too.
**How to apply:** Pure documentation/template surface in the wizard; do not change FSM
semantics. Point authors at the existing built-ins to clone.

## Implementation Steps

1. **`skills/create-loop/templates.md:7-23` (Step 0.1 — template selection menu)** — Add a new
   option entry following the exact `label:` / `description: "... Pattern: state → state → done"`
   format used by all existing entries. Suggested label:
   `"Route / compose / supervise other loops"` with description explaining the three shapes and
   citing `Pattern: classify → score → dispatch → review → done`.

2. **`skills/create-loop/templates.md:229-455` (Step 0.2 — template customization)** — Add a
   `### For "Route / compose / supervise other loops"` block (heading must match Step 0.1 label
   exactly). Include a sub-question distinguishing the three shapes and a `**Apply substitutions:**`
   line. For the router shape, point at `loop-router.yaml` as the canonical loop to clone via
   `ll-loop install loop-router`.

3. **`skills/create-loop/SKILL.md:120-161` (Step 1 — build-from-scratch shape picker)** — Add
   three option entries using the `"RL: Name (tagline)"` prefix convention as the model:
   `"Orch: Router (dynamic dispatch)"`, `"Orch: Composer (goal → DAG)"`,
   `"Orch: Supervisor (adaptive re-plan)"`. Extend the Type Mapping table with the new
   `orch-router` type entry.

4. **`skills/create-loop/SKILL.md:38-48` (Step -1 — keyword inference table)** — Add:
   `"route", "dispatch", "compose", "orchestrate", "supervisor", "router"` → `orch-router`.
   Without this entry, users who type "route to the right loop" get no auto-detection path.

5. **`skills/create-loop/loop-types.md` (after `## Sub-Loop Composition` at line 1509)** — Add
   an `## Orchestration Loops` section mirroring the `## RL Loops` section structure (H2 family
   header → H3 per-shape questions → H4 YAML generation). For the router shape, the YAML
   generation block should reference the `dispatch` state pattern from `loop-router.yaml:335-342`
   (`loop: "${captured.chosen.output}"`). Composer/supervisor shapes: mark as "forthcoming —
   see EPIC-1811" until FEAT-1808/1809 ship.

6. **`docs/guides/LOOPS_GUIDE.md:111-142` (Common Loop Patterns decision tree)** — Add an
   orchestration row to the summary table and a leaf in the decision tree. The `**Routing**`
   category entry for `loop-router` already exists at lines 292–332; add a cross-reference from
   the decision tree to that entry.

7. **Acceptance test**: Run `/ll:create-loop` and verify the "Route / compose / supervise" option
   appears in the Step 0.1 menu and the "Orch: Router" option appears in Step 1. Confirm
   `ll-loop run loop-router` still works (no runtime changes).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `skills/create-loop/reference.md` — add `### Orchestration (Router)` state diagram block under `## Loop Type State Structures` so the reference doc stays complete for all wizard-selectable types
9. Update `docs/reference/COMMANDS.md` — find the `### /ll:create-loop` type enumeration list and add `orch-router` (or `Orchestration`) alongside the existing `fix-until-clean, maintain-constraints, …` entries
10. Update `docs/generalized-fsm-loop.md` — add the new option to the literal wizard menu in `### Example Session` (inside `## The /ll:create-loop Command`)
11. Write `scripts/tests/test_enh1912_doc_wiring.py` — one class per changed file, using the `test_enh1639_doc_wiring.py` string-presence pattern; cover all five primary files (SKILL.md, templates.md, loop-types.md, LOOPS_GUIDE.md, COMMANDS.md)

## Scope Boundaries

- **In scope**: Markdown additions to `skills/create-loop/templates.md`,
  `skills/create-loop/SKILL.md` (Step 1 options + Step -1 keyword table),
  `skills/create-loop/loop-types.md`, and `docs/guides/LOOPS_GUIDE.md`. No FSM YAML changes,
  no Python code changes, no runner modifications.
- **Out of scope**: Building the composer or adaptive-supervisor loops — that is EPIC-1811
  (FEAT-1808, FEAT-1809). This issue only names and links the shapes; it does not create them.
- **Out of scope**: Composer/supervisor wizard entries that point at unbuilt loops. Entries for
  FEAT-1808/1809 should be gated as "forthcoming" until those issues reach `done`.
- **Out of scope**: Renaming or restructuring existing wizard branches for non-orchestration shapes.
- **Out of scope**: Runtime changes to how the wizard collects user input or how the FSM runner
  interprets `loop:` interpolation.

## Open Questions

1. **New top-level branch vs. entries under an existing one.** Orchestration loops differ
   enough (they dispatch other loops) to warrant their own branch in the wizard.
2. **Sequencing vs. EPIC-1811.** The router entry can land now; composer/supervisor entries
   should track FEAT-1808/1809 so the wizard doesn't advertise unbuilt loops.

## Integration Map

### Files to Modify
- `skills/create-loop/templates.md:7-23` — Step 0.1 options block; add "Route / compose / supervise other loops" entry following `label:` / `description: "… Pattern: state → state → done"` format
- `skills/create-loop/templates.md:229-455` — Step 0.2 customization; add `### For "Route / compose / supervise other loops"` block with shape sub-question and `ll-loop install loop-router` clone pointer
- `skills/create-loop/SKILL.md:120-161` — Step 1 shape picker; add `"Orch: Router (dynamic dispatch)"` / `"Orch: Composer (goal → DAG)"` / `"Orch: Supervisor (adaptive re-plan)"` options; extend Type Mapping table
- `skills/create-loop/SKILL.md:38-48` — Step -1 keyword inference table; add `"route", "dispatch", "compose", "orchestrate", "supervisor"` → `orch-router`
- `skills/create-loop/loop-types.md` — add `## Orchestration Loops` section after `## Sub-Loop Composition` (line 1509); H3 per-shape + H4 YAML generation, mirroring `## RL Loops` (line 1552) structure
- `docs/guides/LOOPS_GUIDE.md:111-142` — Common Loop Patterns decision tree and summary table; add orchestration leaf pointing at the existing `**Routing**` / `loop-router` entry at lines 292–332
- `skills/create-loop/reference.md` — add `### Orchestration (Router)` state diagram entry under `## Loop Type State Structures` to match the new `orch-router` type being added to SKILL.md [Agent 2 finding]
- `docs/reference/COMMANDS.md` — `### /ll:create-loop` section lists wizard types verbatim (`fix-until-clean, maintain-constraints, drive-metric, run-sequence, harness, RL variants, meta-optimize`); add `orch-router` (or `Orchestration`) to this enumeration [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — `### Example Session` literal wizard menu (lines 1925–1930) names the current four options; add the new orchestration option [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step -1 keyword gap (critical)**: `skills/create-loop/SKILL.md:38-48` keyword inference has no entries for "route", "dispatch", "compose", or "orchestrate". A user typing `/ll:create-loop route to the right loop` gets no auto-detection path. This gap was not called out in the original issue.
- **SKILL.md Step 1 gap**: The "Build from scratch" wizard at `SKILL.md:120-161` exposes 10 choices; none include orchestration. Both wizard paths (template and scratch) need new entries — the original issue named only `templates.md`.
- **loop-router.yaml dispatch pattern** (`loop-router.yaml:335-342`): `loop: "${captured.chosen.output}"` is the dynamic interpolation mechanism to describe. The `with:` field (`input: "${captured.derived_params.output}"`) shows how context passes to child loops.
- **RL family naming convention**: `SKILL.md:120-161` uses `"RL: Bandit (explore vs exploit)"` prefix — three options sharing an `"RL: "` prefix with `(tagline)`. Use `"Orch: "` prefix for the three orchestration shapes to make the family scannable: `"Orch: Router (dynamic dispatch)"`, `"Orch: Composer (goal → DAG)"`, `"Orch: Supervisor (adaptive re-plan)"`.
- **loop-types.md `## RL Loops` pattern** (line 1552): H2 family header → `### RL <Name> Questions` (H3) → `If user selected "<exact label>":` condition → `#### RL <Name> YAML Generation` (H4). Use the same structure for `## Orchestration Loops`.
- **loop-types.md Sub-Loop Composition** (line 1509): The existing `## Sub-Loop Composition` block already explains the `loop:` field and notes it "cannot be created through the interactive wizard." The new `## Orchestration Loops` section should follow immediately after it and upgrade the router shape from "hand-author only" to wizard-guided.
- **LOOPS_GUIDE.md cross-link target**: `loop-router` is already documented under `**Routing**` at lines 292–332 with full context-variable table and bash examples. The decision tree at lines 111–142 only needs an orchestration row pointing there — no new prose needed in the guide's main body.
- **composer/supervisor loops do not exist on disk**: `loop-composer.yaml` and `loop-composer-adaptive.yaml` are referenced in FEAT-1808/1809 but not yet created. Templates for these shapes must be gated as `"forthcoming — see EPIC-1811"`.

### Similar Patterns
- `scripts/little_loops/loops/loop-router.yaml:1-18` — top-level description/category/context fields; use as the source of truth for the wizard description text
- `scripts/little_loops/loops/loop-router.yaml:335-342` — `dispatch` state: canonical `loop: "${captured.chosen.output}"` dynamic interpolation example
- `skills/create-loop/SKILL.md:120-161` — RL family entries as the naming/format model for the Orch family
- `skills/create-loop/loop-types.md:1552-1910` — `## RL Loops` section structure to mirror for `## Orchestration Loops`
- `.issues/features/P3-FEAT-1808-loop-composer-goal-decomposer-above-loop-router.md` — composer status tracker
- `.issues/features/P3-FEAT-1809-adaptive-loop-composer-with-replan-on-failure.md` — supervisor/adaptive status tracker
- `.issues/epics/P3-EPIC-1811-built-in-orchestration-loops.md` — parent epic for gating composer/supervisor entries

### Dependent Files (Callers/Importers)
- `skills/create-loop/SKILL.md` — wizard entry point; reads `templates.md` and `loop-types.md` at runtime; also needs direct edits (Step 1 options + Step -1 keywords)
- No Python importers — all changes are markdown surface only

### Tests
- `scripts/tests/test_create_loop.py` — validates YAML structure; no interactive template tests; manual verification via `/ll:create-loop` is the acceptance gate
- `scripts/tests/test_loop_router.py` — validates `loop-router.yaml` FSM; no changes needed (runtime untouched)
- `scripts/tests/test_enh1912_doc_wiring.py` — new test file needed; follow `test_enh1639_doc_wiring.py` pattern (one class per changed file, `assert "<string>" in content`); assert `"Orch: Router"` in SKILL.md, `"## Orchestration Loops"` in loop-types.md, `"Route / compose / supervise"` in templates.md, `"orch-router"` in COMMANDS.md, and orchestration row in LOOPS_GUIDE.md decision tree [Agent 3 finding]

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — cross-link target; `**Routing**` category at lines 292–332 already documents `loop-router` fully; decision tree at lines 111–142 needs one new row

### Configuration
- N/A — no configuration files affected

## Relationship to Sibling Issues

- **EPIC-1811** builds the orchestration *loops*; this issue makes them *discoverable* from the
  wizard. Best landed (at least partly) after the composer ships so the templates point at real
  built-ins — though the `loop-router` entry can go in immediately.

## Provenance

Surfaced while reviewing `https://github.com/revfactory/harness`. Harness names six
architecture patterns (pipeline, fan-out, expert-pool, producer-reviewer, supervisor,
hierarchical) as first-class choices; little-loops has the equivalents but doesn't name the
orchestration ones in its authoring wizard.

## Impact

- **Priority**: P4 — Discoverability improvement; non-blocking for any current work. Reduces
  friction for users authoring orchestration loops but has no runtime effect.
- **Effort**: Small — Pure markdown additions to wizard templates and docs; no FSM YAML,
  Python, or runner changes.
- **Risk**: Low — Read-only markdown content; a mistake in the template text is trivially
  correctable and has no runtime side effects.
- **Breaking Change**: No

## Session Log
- `/ll:ready-issue` - 2026-06-04T01:04:24 - `20bd4d0f-92eb-4c5f-84ac-b72b18d19738.jsonl`
- `/ll:confidence-check` - 2026-06-03T21:05:00 - `87cbfd8d-7a5d-4900-8d43-fe8afa726245.jsonl`
- `/ll:wire-issue` - 2026-06-04T00:59:58 - `401066ef-7fde-4c47-a6e9-bf52970f6eab.jsonl`
- `/ll:refine-issue` - 2026-06-04T00:55:23 - `febc3266-d90e-4ed7-9fc4-13b11e74ebb0.jsonl`
- `/ll:refine-issue` - 2026-06-03T21:30:00 - `auto`
- `/ll:format-issue` - 2026-06-03T21:05:00 - `b62e3f92-2664-4793-81e7-cf8464c74fe6.jsonl`
- `/ll:capture-issue` - 2026-06-03T20:59:38Z - `b4fa1e68-4a59-49bd-949a-5a5b7533509f.jsonl`

---

## Status

- **State**: open
- **Created**: 2026-06-03
- **Priority**: P4
