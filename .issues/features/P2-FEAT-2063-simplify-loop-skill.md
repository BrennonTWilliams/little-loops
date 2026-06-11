---
id: FEAT-2063
title: Add /ll:simplify-loop skill — decompose loops into sub-loops and collapse state chains into flows
type: FEAT
priority: P2
status: done
captured_at: '2026-06-09T21:04:09Z'
discovered_date: 2026-06-09
discovered_by: user-session
labels:
- loops
- fsm
- skills
- refactoring
- simplification
size: Medium
completed_at: '2026-06-09T21:04:09Z'
---

# FEAT-2063: Add /ll:simplify-loop skill — decompose loops into sub-loops and collapse state chains into flows

## Summary

little-loops had a family of loop-operating skills (`create-loop`, `review-loop`,
`rename-loop`, `cleanup-loops`, `debug-loop-run`, `audit-loop-run`) but none that
*refactors* a loop's structure. Loops accrete: a single `states:` map grows to
dozens of states, long linear runs are written verbosely, and self-contained
phases stay inline instead of becoming reusable sub-FSMs. This adds
`/ll:simplify-loop <name>` — a skill that takes a project-level or built-in FSM
loop and applies two **behavior-preserving** transforms: collapsing linear state
chains into `flow:` shorthand and extracting cohesive regions into sub-loops
invoked via `loop:`.

## Motivation

Two simplifying transforms already had first-class engine support but no tooling
to apply them:

1. **`flow:` Linear Flow Shorthand** — an ordered list of state names (with
   optional `name?yes:no` ternary branches) plus a `state_defs:` body block,
   expanded into a `states:` map by `resolve_flow()`
   (`scripts/little_loops/fsm/fragments.py`). Lets a linear chain collapse from a
   verbose map into a list.
2. **Sub-loops** — `loop: <name>` + `with: {...}` +
   `on_success`/`on_failure`/`on_error`, executed by `_execute_sub_loop()`
   (`scripts/little_loops/fsm/executor.py`). Reusable child FSMs live in
   `loops/oracles/`. Lets a cohesive region become a separately invoked FSM.

The skill detects collapsible chains and extractable regions, then applies the
rewrites while preserving FSM behavior — same `initial`, same routing semantics,
same reachable terminal set.

## Decisions (confirmed with user via AskUserQuestion)

- **Output target:** edit the loop **in place** with a `.bak` backup; run
  `ll-loop validate` after every write; restore the backup on validation failure
  (matches `review-loop`/`rename-loop`).
- **Extracted sub-loop scope:** **mirror the parent's scope** — a built-in
  parent's children go to the `oracles/` subdir of the built-in loops dir; a
  project parent's children go to `.loops/`.
- **Correctness invariant:** every transform is behavior-preserving. `flow:`
  expansion is provably equivalent to the `next:` chain it replaces; sub-loop
  extraction maps the region's success-exit → child `done` → parent `on_success`,
  and failure-exit → child `failed` → parent `on_failure`.

## Changes Made

### `skills/simplify-loop/SKILL.md` (new, 306 lines)
Operational flow as a `disable-model-invocation` skill (model: sonnet):
- **Step 0** — resolve loop + scope (project `.loops/` vs. built-in
  `scripts/little_loops/loops/`, honoring `oracles/<name>` sub-paths); refuse a
  running loop.
- **Step 1** — load resolved graph (`ll-loop show <name> --resolved -j`) +
  raw source YAML; record the behavioral baseline (state count, edge list,
  `initial`, terminal set).
- **Step 2** — detect flow-collapse candidates (2a) and sub-loop-extraction
  candidates (2b); honor `--flows-only`/`--subloops-only`.
- **Step 3** — present before/after, approve each change (skip with
  `--auto`/`--yes`); `--dry-run` stops here.
- **Step 4** — apply children first (validate each), then rewrite parent with
  `cp .bak` → `Write` → `ll-loop validate`, restoring on failure.
- **Step 5** — equivalence + regression guard (resolved-graph diff, `ll-loop
  simulate`, and `test_builtin_loops.py` for built-in loops).
- **Step 6** — stage with explicit `git add`, report, persist an artifact to
  `.loops/simplifications/<name>-<ts>.md`.

### `skills/simplify-loop/reference.md` (new)
Detection algorithms (linear-chain eligibility predicate, cohesion rules,
interface inference), the ternary mapping table, a worked `states:`→`flow:`
transform, the behavior-preservation checklist, the scope-resolution table, the
artifact schema, and an anti-patterns list. Keeps SKILL.md under the 500-line gate.

### `commands/help.md`
Added `/ll:simplify-loop` to the AUTOMATION & LOOPS block and to the summary line.

### `.claude/CLAUDE.md`
Added `simplify-loop`^ to the Automation & Loops skill list.

## Reuse (no reinvention)

- Loop name/scope resolution modeled on `rename-loop` Step 2.
- Resolved-graph load + simulate-based behavioral check from `review-loop`.
- Backup → write → validate → restore pattern from `review-loop` Step 5.
- `flow:` semantics deferred to `resolve_flow()` — the skill only emits YAML the
  existing parser accepts; it does not duplicate expansion logic.
- Sub-loop caller/callee shape modeled on `loops/oracles/plan-research-iteration.yaml`
  and `rn-plan.yaml` / `deep-research.yaml`.
- Verdict-laundering guard mirrors `audit-loop-run` Step 8.

## Acceptance Criteria

- [x] `skills/simplify-loop/SKILL.md` + `reference.md` created, matching the
  established skill anatomy (frontmatter, `disable-model-invocation`, `allowed-tools`)
- [x] `ll-verify-skills` passes (SKILL.md ≤ 500 lines — 306)
- [x] `ll-verify-skill-budget` passes (exempt — `disable-model-invocation`)
- [x] Codex integration guard passes (`metadata.short-description` ≤ 80 chars — 67)
- [x] Skill auto-discovered; registered in `/ll:help` and `.claude/CLAUDE.md`
- [x] `ll-loop show --resolved -j` / `ll-loop simulate` interfaces the skill
  drives were smoke-tested and return the expected resolved graph
- [x] Full skill/codex/trigger pytest selection green (1227 passed, 1 skipped)

## Impact

- **Priority**: P2
- **Effort**: Medium — two authored skill files + light registration, grounded in
  three parallel exploration passes over the FSM loop system
- **Risk**: Low — additive (new skill, no behavior change to existing components);
  the skill itself enforces behavior-preservation + backup/restore on the loops
  it edits

## Files Touched

- `skills/simplify-loop/SKILL.md` (new)
- `skills/simplify-loop/reference.md` (new)
- `commands/help.md`
- `.claude/CLAUDE.md`

## Notes

`ll-verify-triggers` reports 0% precision/recall for `simplify-loop`, but this is
consistent with every sibling loop skill (`create-loop`, `rename-loop`,
`review-loop`, `cleanup-loops`) — the `trigger_fixtures` frontmatter block is
opt-in and most skills omit it. No fixtures were added, keeping the new skill
consistent with the family. A possible future follow-up is adding
should-fire/should-not-fire fixtures across the loop-skill family at once.

Out of scope (deliberately): a new engine abstraction for reusable *multi-state*
chain fragments (today only single-state `fragment:` and whole-loop
`flow:`/sub-loops exist) — this skill composes existing primitives without
extending the schema; and natural-language-goal → loop-DAG decomposition (that is
FEAT-1808 `loop-composer`, a separate effort).


## Session Log
- `hook:posttooluse-status-done` - 2026-06-09T21:04:49 - `bace48cb-e8e9-472e-94df-639d1eaeb4fc.jsonl`
