---
id: ENH-3527
title: Declare a model capability hint in loop, skill, and agent artifacts instead of a hard-coded model id
type: ENH
priority: P0
status: open
discovered_date: '2026-09-23'
labels:
- multi-host
- loops
---

# Declare a model capability hint in loop, skill, and agent artifacts instead of a hard-coded model id

## Summary

Any artifact that names a concrete model id carries a value it cannot keep current: model ids change on a release cadence the artifacts do not track, and the id that is correct on one host is meaningless on another. Both failures show up as a loop that ran fine last month and now errors on a name. Replace the id with a capability-class hint the artifact declares — a small closed vocabulary along the lines of `coding`, `reasoning`, and `burst` — and let the host adapter resolve it to whatever that host currently offers. The artifact then states what kind of model the step needs, which is the part that is actually stable, and the mapping lives in one place per host where a rename is a single edit.

## Current Behavior

Skills (`skills/*/SKILL.md`, e.g. `model: sonnet`, `model: haiku`), agents, and loop YAML states (`model:` on FSM states, default `fsm.schema.DEFAULT_LLM_MODEL`) carry a literal model alias or id. `host_runner.resolve_model_alias` maps those aliases to concrete Anthropic ids via a single Anthropic-specific `MODEL_ALIASES` table, and each `HostRunner.build_streaming` passes the value through as `--model`. An alias valid for one host is meaningless on another, and a model rename requires touching the table plus any artifact that names an id directly.

## Expected Behavior

Artifacts may declare a capability-class hint (`coding` | `reasoning` | `burst`) instead of a model id. The host adapter resolves the hint to that host's current concrete model at run time via a per-host table, so a rename is one edit and an artifact moved between hosts needs no change. Artifacts that still carry a literal model id or alias keep working unchanged.

## Design

One field and one resolution step:

- Loop, skill, and agent artifacts declare a capability-class hint from a closed vocabulary — `coding` | `reasoning` | `burst` — instead of a hard-coded model id.
- The host adapter owns the hint → concrete-id mapping, one table per host, so a model rename is a single edit in one place.
- The hint is what survives: an artifact moved between hosts resolves to whatever the target host currently offers, with no artifact edit.
- Composes with the existing model-tier-by-task guidance by giving that guidance a machine-readable place to live.
- Additive: artifacts that still carry a literal model id keep working.

## Acceptance Criteria

- [ ] Loop, skill, and agent artifacts can declare a model capability hint from a closed vocabulary (`coding`, `reasoning`, `burst`).
- [ ] The host adapter resolves the hint to a concrete model id for the current host at run time.
- [ ] A model id rename requires editing exactly one mapping entry per host.
- [ ] An artifact moved between hosts resolves to the target host's current model without any artifact edit.
- [ ] Existing artifacts carrying hard-coded model ids continue to run unchanged.

## Scope Boundaries

- **In scope**: closed capability vocabulary (`coding`, `reasoning`, `burst`); a `model_hint` declaration on loop states, skills, and agents; per-host hint → id resolution in `host_runner`; back-compat for literal ids/aliases.
- **Out of scope**: rewriting existing artifacts to use hints (migration is separate, incremental); adding new vocabulary values beyond the three; changing how hosts select models internally; cost- or latency-based automatic routing.

## Program Design

### Types

- `ModelHint: Literal["coding", "reasoning", "burst"]`
- `HINT_MODELS: dict[str, dict[ModelHint, str]]` — host id → hint → concrete model id/alias

### Signatures

- `resolve_model_hint(hint: str, host_id: str) -> str | None`
- `resolve_model_alias(model: str) -> str`

### Call Path

`ClaudeCodeRunner.build_streaming` -> `resolve_model_hint` -> `resolve_model_alias`

## Impact

- **Priority**: P0 - Model-id drift breaks loops that previously ran, and blocks multi-host portability of artifacts.
- **Effort**: Medium - one new resolver and per-host tables in `host_runner.py`, plus schema/frontmatter acceptance of the new field across loops, skills, and agents.
- **Risk**: Low - additive; literal ids and aliases keep resolving through the existing path.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-23 | Priority: P0


## Session Log
- `/ll:format-issue` - 2026-09-23T22:58:54 - `67a10285-a4b7-4192-bd9e-23ac30a3ffd0.jsonl`
