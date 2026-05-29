---
id: EPIC-1694
type: EPIC
priority: P2
status: open
captured_at: '2026-05-25T20:53:43Z'
discovered_date: '2026-05-25'
discovered_by: capture-issue
relates_to: [FEAT-1692, FEAT-1695, FEAT-1696, FEAT-1697, FEAT-1287, FEAT-1283, FEAT-1285, FEAT-1286, EPIC-1663, FEAT-1738, FEAT-1739, ENH-1740, ENH-1741, FEAT-1742, FEAT-1743, FEAT-1798]
---

# EPIC-1694: Built-in FSM Loops Powered by the Learning-Test Registry

## Summary

Ship four built-in FSM loops in `scripts/little_loops/loops/` that turn the Learning Test Registry (`.ll/learning-tests/`, `ll-learning-tests` CLI, `/ll:explore-api` skill, `type: learning` FSM state) from "a thing agents *could* check" into "a thing the harness checks for them." The four loops form a coherent stack — a reusable gate primitive, a defensive wrapper, and two integration-oriented consumers:

| Loop | Role |
|---|---|
| `ready-to-implement-gate` (FEAT-1695) | Generic shell-driven gate: takes a list of external-API targets, returns pass/block |
| `assumption-firewall` (FEAT-1696) | Extracts external-dep assumptions from an issue, delegates to the gate |
| `integrate-sdk` (FEAT-1692) | Discover SDK usage → propose proof targets → gate → scaffold integration |
| `adopt-third-party-api` (FEAT-1697) | `/ll:scrape-docs` → enumerate endpoints → gate → produce integration playbook |

## Motivation

The Learning Test Registry and its primitives shipped in FEAT-1287 (`/ll:explore-api`), FEAT-1283 (`type: learning` state), FEAT-1285 (`LearnTestRecord`), and FEAT-1286 (`ll-learning-tests` CLI), but those primitives lack top-level entry points that turn them into developer-visible workflows. Today agents can choose to check the registry; they often don't. This epic adds harness-level loops that enforce the check — converting the registry from optional infrastructure into a structural gate.

**Why a coherent stack rather than four ad-hoc loops:** the gate primitive is the load-bearing piece. The other three are different framings of "things you'd want to do *before* trusting an external API" that all funnel through the same proof contract. Shipping them together exercises the primitive across enough call shapes (issue-driven, SDK-driven, doc-driven) to validate it.

## Architectural Constraint Discovered During Planning

`LearningConfig.targets` is loaded once at YAML parse via `from_dict()` in `scripts/little_loops/fsm/schema.py:271–305` and is **never re-interpolated** — `type: learning` cannot accept dynamic targets from `${context.*}`. This means any loop that builds a target list at runtime cannot use `type: learning` directly; it must shell-drive against `ll-learning-tests check` and invoke `/ll:explore-api` itself.

This constraint is why FEAT-1695 (`ready-to-implement-gate`) is shell-driven rather than a thin wrapper around `type: learning`. The other three loops route their dynamic target lists through the gate.

## Children

- **FEAT-1695** — `ready-to-implement-gate`: shell-driven gate primitive (the building block)
- **FEAT-1696** — `assumption-firewall`: extract assumptions from an issue and gate them
- **FEAT-1692** — `integrate-sdk`: proof-driven SDK integration (already captured; retrofitted as child)
- **FEAT-1697** — `adopt-third-party-api`: scrape docs → enumerate endpoints → gate → playbook
- **FEAT-1742** — discoverability surface (PreToolUse hook or `/ll:confidence-check` probe) that nudges users toward `proof-first-task` when mainstream impl loops touch unfamiliar APIs
- **FEAT-1743** — wire learning-tests as an opt-in feature flag in `/ll:init` and `config-schema.json`; provides the master switch every EPIC-1694 surface checks before activating
- **ENH-1741** — refactor `ready-to-implement-gate` to use `type: learning` states, making it the canonical built-in exemplar of the primitive
- **ENH-1740** — `assumption-firewall` — record untestable claims via `--assume` flag
- **FEAT-1798** — Specialist-role harness template (Plan → Research → Implement → Report)

## Scope

### In Scope

- Four new loop YAMLs at `scripts/little_loops/loops/{ready-to-implement-gate,assumption-firewall,integrate-sdk,adopt-third-party-api}.yaml`
- Updating `scripts/tests/test_builtin_loops.py` to include the four new names in the canonical-set test (`test_expected_loops_exist`)
- Reusing existing primitives (`/ll:explore-api`, `ll-learning-tests check`, `output_json` evaluator, captured-variable interpolation, sub-loop `with:` binding) — no schema, executor, evaluator, CLI, or new command/skill changes

### Out of Scope

- `migrate-sdk-version` loop (deferred until `mark-stale` automation is more obviously needed)
- `from:`/`flow:` template inheritance for the new loops (current built-ins don't use `flow:`; insufficient shared shape)
- Wiring `ready-to-implement-gate` *into* existing implementation loops (`autodev`, `auto-refine-and-implement`, etc.) — separate follow-up; this epic ships the gate as a standalone primitive that those loops can opt into later
- Documentation updates to `LOOPS_GUIDE.md` and `LEARNING_TESTS_GUIDE.md` — follow-up doc pass after the loops have been exercised

## Acceptance Criteria

- All four child FEATs (FEAT-1692, FEAT-1695, FEAT-1696, FEAT-1697) reach `status: done`.
- `ll-loop validate` reports no ERRORs for all four loop YAMLs.
- `python -m pytest scripts/tests/test_builtin_loops.py -v` passes with the four new names added to `test_expected_loops_exist`.
- `ll-loop list` surfaces all four loops.
- End-to-end smoke: `ll-loop run ready-to-implement-gate --context targets="<already-proven-target>"` reaches terminal `done` in one iteration without invoking `/ll:explore-api`.
- End-to-end smoke: `ll-loop run ready-to-implement-gate --context targets="<missing-target>" --context max_retries="1"` invokes `/ll:explore-api` once and routes to `done` or `blocked` based on the resulting `status`.

## Implementation Order

1. **FEAT-1695** (`ready-to-implement-gate`) ships first — it is the dependency for the other three. Validate as a standalone primitive against an already-proven target and against a missing target before moving on.
2. **FEAT-1696** (`assumption-firewall`) ships next — it is the simplest consumer of the gate (single sub-loop call wrapped around issue extraction). Validates that the gate's `done`/`blocked` terminals route cleanly through `on_success`/`on_failure`.
3. **FEAT-1692** (`integrate-sdk`) and **FEAT-1697** (`adopt-third-party-api`) can ship in either order or in parallel — both consume the gate the same way; differences are in upstream (discovery / docs scrape) and downstream (scaffold / playbook) of the gate call.

## Plan Reference

The full design lives at `~/.claude/plans/proceed-with-creating-all-indexed-bumblebee.md` (4-loop plan with per-loop state diagrams, captured-variable patterns, sub-loop binding examples, and verification commands). Each child FEAT links to the relevant section of that plan.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`epic`, `loop`, `learning-tests`, `fsm`, `proof-driven-development`, `captured`

---

**Open** | Created: 2026-05-25 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-05-25T20:53:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/810cf8d1-477c-42da-bb20-b577b2ee3ad9.jsonl`
