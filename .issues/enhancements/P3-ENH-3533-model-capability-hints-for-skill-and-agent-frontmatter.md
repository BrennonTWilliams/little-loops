---
id: ENH-3533
type: ENH
title: Model capability hints for skill and agent frontmatter
priority: P3
status: open
parent: EPIC-3563
epic: EPIC-3563
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

- `scripts/little_loops/adapters/codex.py`, `cli/adapt_agents_for_codex.py`, and the Gemini/Kimi/Qwen adapters (`ll-adapt --host <gemini|kimi-code|qwen>`) plus their generated mirrors; `skills/`, `agents/` frontmatter; `ll-verify-skills`.
- Depends on ENH-3527's resolver and `orchestration.model_hints` config.

## Impact

- **Priority**: P3.
- **Effort**: Medium.
- **Risk**: Medium — generated artifacts can silently go stale.

## Open Questions (resolve before implementation)

**Not implementation-ready.** Answer these with `/ll:spike` (can Claude Code honor a frontmatter hint at all, and does it tolerate an unknown `model_hint` key in skill/agent frontmatter?) and `/ll:decide-issue` before any implementation. Exclude from the first implementation wave; it must not gate EPIC-3563 closure.

The spike does not depend on ENH-3527: it probes Claude Code's frontmatter handling, not the resolver. It can run now, in parallel with the loop-execution work. Only implementation is blocked by ENH-3527.

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
- `resolve_model_hint(hint: str, *, backend: str, overrides: dict | None = None) -> str` — provided by ENH-3527 (no `operation` parameter).

### Call Path

- `emit_agent` → `resolve_model_hint` → generated `.codex/agents/<name>.toml`

## Verification Notes

Verdict at time of check: **VALID** (no corrections needed; this section is a record of what was checked, not an outstanding action item). Evidence-quote check clean (`ll-verify-evidence`); no required decisions rules; graph provider `codegraph` (fresh) available.

Checked 2026-09-24: `CodexAdapter.emit_agent(self, agent_meta: dict) -> str` exists at `adapters/codex.py` L429 with the stated signature; `main_verify_skills` (`cli/docs.py` L244) exists; `resolve_model_hint` does not exist yet and is provided by blocker ENH-3527 (open) as stated.

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-09-24T00:46:09 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
