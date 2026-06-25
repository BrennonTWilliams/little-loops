---
id: FEAT-2260
title: Generic host-parameterized skill + command adapter
type: feature
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: planning-assessment
parent: EPIC-2257
decision_ref: ARCHITECTURE-049
labels: [host-compat, portfolio, skills, commands, adapters]
relates_to: [FEAT-2188, FEAT-2189, ENH-2121]
---

# FEAT-2260: Generic host-parameterized skill + command adapter

## Summary

Provide **one** host-parameterized adapter that bridges ll skills and commands
into a target host's discovery surface, selected via `--host`
(`codex|gemini|omp`), instead of a bespoke `ll-adapt-*-for-<host>` per host.

Per ARCHITECTURE-049, this consolidates:
- `ll-adapt-skills-for-codex` + `ll-adapt-agents-for-codex` (existing, Codex-only)
- **FEAT-2188** (Gemini skills adaptation)
- **FEAT-2189** (Gemini commands `.md` → `.toml`)
- **ENH-2121** (rich Codex subagent TOML fields — absorbed as the Codex-host
  agent-emitter requirement; see "Codex-host emitter parity" below)
- the omp skill/command adaptation need (folded here, not re-specified under EPIC-2258)

## Motivation

Skill/command adaptation differs per host only in **output format** (Codex
Skills API frontmatter, Gemini `.toml`, omp's surface). The traversal,
selection, and `disable-model-invocation` filtering logic is identical. One
adapter with per-host output emitters removes N near-duplicate scripts.

## Acceptance Criteria

- A single entry point (`ll-adapt-skills --host <host>` / `ll-adapt-commands
  --host <host>`, or a unified `ll-adapt --host`) emits the correct
  host-specific format.
- Codex output matches today's `ll-adapt-skills/agents-for-codex` behavior
  (those become thin `--host codex` aliases or are retired).
- Gemini `.toml` command output covers FEAT-2189; Gemini skill frontmatter
  covers FEAT-2188 (both closed as superseded once this lands).
- Respects `disable-model-invocation: true` (skips those skills) for every host.
- Adding a host = adding one output emitter, not a new script.

### Codex-host emitter parity (absorbs ENH-2121)

The `--host codex` agent emitter must not regress to today's lossy four-field
output. Since this issue generalizes `ll-adapt-agents-for-codex`, it owns
ENH-2121's scope: the Codex agent emitter maps available source-agent metadata
onto the richer Codex subagent schema rather than dropping it.

- Codex agent TOML emits `sandbox_mode` (vocabulary aligned with ENH-1529:
  `off` / `read-only` / `write-to-cwd` / `network`), `model_reasoning_effort`,
  `mcp_servers`, and `skills.config` **when derivable from the source agent's
  `tools:` frontmatter / model identifier**; fields with no source mapping are
  omitted (Codex inherits from the parent session — omission stays safe).
- `nickname_candidates` remains **out of scope** (no clean source mapping), and
  no new `agents/*.md` frontmatter fields are invented — derive from existing
  `tools:` / model only. (Both boundaries carried over verbatim from ENH-2121.)
- Test parity: the Codex emitter's tests assert each rich field emits for a
  fixture agent that declares it and is omitted otherwise (was
  `test_adapt_agents_for_codex.py`; folds into this adapter's test suite).

## Reference

- `ll-adapt-skills-for-codex`, `ll-adapt-agents-for-codex` — existing Codex emitters.
- FEAT-2188 / FEAT-2189 — the bespoke Gemini specs this generalizes.
- ENH-2121 — rich Codex subagent TOML fields, absorbed here as the Codex-host
  emitter parity requirement (closed as superseded; full source-mapping detail
  and the `developers.openai.com/codex/subagents` schema link live in its body).

## Impact

- **Effort**: Medium.
- **Risk**: Low-Medium — must preserve existing Codex output byte-for-byte to
  avoid regressing the landed Codex adapter.
- **Breaking Change**: No (existing Codex scripts kept as aliases during transition).

## Status

**Open** | Created: 2026-06-24 | Priority: P4
