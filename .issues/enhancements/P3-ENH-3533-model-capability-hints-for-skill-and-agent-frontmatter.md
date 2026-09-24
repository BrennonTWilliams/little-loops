---
id: ENH-3533
type: ENH
title: Model capability hints for skill and agent frontmatter
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T00:20:40Z'
labels:
- multi-host
blocked_by:
- ENH-3527
---

# ENH-3533: Model capability hints for skill and agent frontmatter

## Summary

Extend ENH-3527's `model_hint` vocabulary (`coding`, `reasoning`, `burst`) from loop states to skill and agent frontmatter, so shipped skills/agents stop hard-coding host model IDs. Deferred from ENH-3527 because accepting a frontmatter key does not establish that the host honors it.

## Current Behavior

- Claude Code serves skills and agents natively; there is no little-loops model-resolution step at invocation time.
- Codex agent TOML is generated ahead of execution; `adapters/codex.py` `emit_agent` copies `model` verbatim from frontmatter.
- `ll-verify-skills` checks file sizes, not model selection.

## Expected Behavior

A skill or agent can declare `model_hint` instead of `model`; each supported host receives a host-valid model through a documented, tested mechanism, and unsupported hosts fail or warn explicitly.

## Integration Map

- `scripts/little_loops/adapters/codex.py`, `cli/adapt_agents_for_codex.py`, other adapters; `skills/`, `agents/` frontmatter; `ll-verify-skills`.
- Depends on ENH-3527's resolver and `orchestration.model_hints` config.

## Impact

- **Priority**: P3.
- **Effort**: Medium.
- **Risk**: Medium — generated artifacts can silently go stale.

## Open Questions (resolve before implementation)

- **Resolution timing**: native invocation (Claude Code reads frontmatter — can a hint be honored at all without rewriting the file?) versus generation time (Codex/Gemini/Kimi/Qwen adapters resolve through ENH-3527's resolver when emitting).
- **Staleness**: how generated agent files are detected as stale and regenerated after a mapping or `orchestration.model_hints` change.
- **Claude-native path**: whether hints require an `ll-adapt`-style materialization for Claude Code too, or are limited to generated hosts.

## Acceptance Criteria

- [ ] Every artifact/host combination claimed as supported has an executable test proving the resolved model reaches the host artifact or invocation.
- [ ] Declaring both `model` and `model_hint` in frontmatter is a validation error; unknown hints are errors.
- [ ] Generated-file staleness after a mapping change is detected (gate or regeneration rule).
- [ ] Migration of shipped skills/agents, if any, is done with mirrors regenerated (`ll-adapt --apply`).

## Scope Boundaries

- **In scope**: `model_hint` in skill/agent frontmatter, resolution at native invocation or generation time, staleness detection for generated agent files, tests per claimed artifact/host combination.
- **Prerequisite**: ENH-3527 (resolver and `orchestration` hint mappings).
- **Out of scope**: new hint vocabulary; migrating every shipped skill/agent in the same change unless trivial.

## Program Design

### Types

- `model_hint: str | None` — optional frontmatter key, mutually exclusive with `model`.

### Signatures

- `CodexAdapter.emit_agent(self, agent_meta: dict) -> str` — existing; resolves `model_hint` through `resolve_model_hint` instead of copying `model` verbatim.
- `resolve_model_hint(hint: str, *, backend: str, operation: str, overrides: dict | None = None) -> str` — provided by ENH-3527.

### Call Path

- `emit_agent` → `resolve_model_hint` → generated `.codex/agents/<name>.toml`

## Status

**Open** | Created: 2026-09-24 | Priority: P3
