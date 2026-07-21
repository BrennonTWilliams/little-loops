---
id: ENH-2713
type: ENH
title: Per-state model pinning in loop YAML (haiku for verdict states)
priority: P3
status: open
captured_at: "2026-07-21T02:03:13Z"
discovered_date: "2026-07-21"
discovered_by: capture-issue
parent: EPIC-2456
labels: [token-cost, fsm, routing]
relates_to: [EPIC-2456, ENH-2490]
---

# ENH-2713: Per-state model pinning in loop YAML (haiku for verdict states)

## Summary

Support a per-state `model:` field in loop YAML so cheap classification states — `check_semantic` verdicts, `llm_structured` extraction — run on haiku while generator states keep the session default. This is the loop-YAML half of the deferred ENH-2490 (agent-frontmatter haiku pin) and a static precursor to Tier 4's F7-lite router: it captures most of routing's win with none of the cascade machinery.

## Motivation

Verdict states are tiny, rigidly-templated tasks currently billed at flagship rates on every iteration of every loop. Unlike ENH-2490 (deferred for lacking a quality gate), this has a built-in one: MR-1 already requires each LLM-judged state to pair with a non-LLM evaluator in its routing chain, so a wrong verdict from a cheaper model is caught by the same external signal that gates the flagship's verdicts.

## Current Behavior

Model selection is per-invocation/host-level; all FSM states within a loop run on the same model. (Verify during refinement whether `fsm/schema.py` already accepts a state-level `model:` that goes unused — the plan docs' precedence rule references "loop YAML `model:`".)

## Expected Behavior

A state may declare `model: haiku`; the runner passes the mapped model id to the host invocation for that state only. Precedence: explicit `--model` flag > state `model:` > loop `model:` > session default (consistent with the `routing.precedence` rule planned for Tier 4 — this issue should not contradict [TBD-17] when it lands).

## Proposed Solution

- `model:` accepted at loop level and state level in `fsm/schema.py`; alias map (`haiku`/`sonnet`/`opus` → concrete ids) resolved through `resolve_host()`, never hard-coded literals (host-CLI abstraction policy).
- `ll-loop validate` advisory: a haiku-pinned state that is a generator (writes artifacts) rather than an evaluator gets a WARN, mirroring the ENH-2490 quality concern.
- Roll out on builtin loops' verdict states only after a before/after quality check on ≥10 runs per loop (evaluator agreement rate vs flagship).

## Acceptance Criteria

- [ ] Per-state `model:` reaches the host invocation for that state only; other states unaffected.
- [ ] Precedence documented and tested (`--model` flag beats YAML).
- [ ] Validation warns on haiku-pinned generator states.
- [ ] At least one builtin loop's verdict states pinned with measured cost delta and no evaluator-agreement regression.

## Impact

- **Priority**: P3 — solid savings, but bounded by verdict-state share of spend; ENH-2712's data should confirm before broad rollout.
- **Effort**: Small (~60–100 LOC + tests).
- **Risk**: Low — opt-in, MR-1 pairing bounds the blast radius.

## Session Log
- `/ll:capture-issue` - 2026-07-21T02:03:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79ab3d38-0b67-42aa-9ad2-b6f2af55d225.jsonl`

---

## Status

**Open** | Created: 2026-07-21 | Priority: P3
