---
id: ENH-1912
title: Name router/composer/supervisor as selectable shapes in create-loop wizard
type: ENH
priority: P4
status: open
captured_at: "2026-06-03T20:59:38Z"
discovered_date: 2026-06-03
discovered_by: capture-issue
relates_to: [EPIC-1811]
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

1. Add a "Route / compose / supervise other loops" branch (or template entries) to
   `skills/create-loop/templates.md` naming the three shapes and when to pick each.
2. For each, reference the canonical built-in to clone (`loop-router` now; composer/adaptive
   once EPIC-1811 lands) and the key mechanism (`loop:` interpolation, `depends_on` DAG,
   `reassess` gate).
3. Cross-link `docs/guides/LOOPS_GUIDE.md` so the wizard and guide agree.
4. Gate any composer/supervisor template text on EPIC-1811 status, or mark it "forthcoming"
   until those loops ship, so the wizard never points at a non-existent built-in.

## Open Questions

1. **New top-level branch vs. entries under an existing one.** Orchestration loops differ
   enough (they dispatch other loops) to warrant their own branch in the wizard.
2. **Sequencing vs. EPIC-1811.** The router entry can land now; composer/supervisor entries
   should track FEAT-1808/1809 so the wizard doesn't advertise unbuilt loops.

## Integration Map

### Files to Modify
- `skills/create-loop/templates.md` — add the orchestration-shape entries
- `skills/create-loop/loop-types.md` — note the shapes alongside existing pattern docs
- `docs/guides/LOOPS_GUIDE.md` — cross-link router/composer as the multi-loop on-ramp

### Similar Patterns
- `scripts/little_loops/loops/loop-router.yaml` — the shipped router to reference/clone
- `.issues/features/P3-FEAT-1808-*` / `P3-FEAT-1809-*` — composer + adaptive variants (EPIC-1811)
- `.issues/epics/P3-EPIC-1811-built-in-orchestration-loops.md` — parent epic for the loops themselves

## Relationship to Sibling Issues

- **EPIC-1811** builds the orchestration *loops*; this issue makes them *discoverable* from the
  wizard. Best landed (at least partly) after the composer ships so the templates point at real
  built-ins — though the `loop-router` entry can go in immediately.

## Provenance

Surfaced while reviewing `https://github.com/revfactory/harness`. Harness names six
architecture patterns (pipeline, fan-out, expert-pool, producer-reviewer, supervisor,
hierarchical) as first-class choices; little-loops has the equivalents but doesn't name the
orchestration ones in its authoring wizard.

## Session Log
- `/ll:capture-issue` - 2026-06-03T20:59:38Z - `b4fa1e68-4a59-49bd-949a-5a5b7533509f.jsonl`

---

## Status

- **State**: open
- **Created**: 2026-06-03
